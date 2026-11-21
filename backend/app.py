import json
import logging
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from typing import Dict, Optional

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

import html

from cache import (
    allow_item,
    find_latest_report,
    get_cache_stats,
    get_official,
    get_report,
    list_allowed,
    save_official,
    save_report,
)
from compare import compare_reports
from config import DEMO_MODE, PORT
from notify import send_protect_alert
from pipelines import mode1_validate, mode2_investigate, mode3_discover
from protect import mode4_protect

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
)
logger = logging.getLogger(__name__)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DEMO_PRESETS = [
    {
        "mode": 1,
        "query": "UPI expense tracker for college students",
        "label": "UPI Expense Tracker",
    },
    {
        "mode": 1,
        "query": "AI tutor for JEE aspirants",
        "label": "AI Tutor for JEE",
    },
    {
        "mode": 1,
        "query": "Pet care booking app in Bengaluru",
        "label": "Pet Care Booking",
    },
    {"mode": 2, "query": "Dunzo", "label": "Dunzo"},
    {"mode": 2, "query": "Swiggy Instamart", "label": "Swiggy Instamart"},
    {"mode": 2, "query": "Cult.fit", "label": "Cult.fit"},
    {"mode": 3, "query": "Personal Finance", "label": "Personal Finance"},
    {"mode": 3, "query": "EdTech", "label": "EdTech"},
    {"mode": 3, "query": "Healthcare", "label": "Healthcare"},
    # Mode 4 presets: add official phone numbers and app IDs here before prewarming
    {"mode": 4, "query": "Blue Dart", "label": "Blue Dart", "official": {"domains": ["bluedart.com"], "phones": [], "app_ids": []}},
    {"mode": 4, "query": "IRCTC", "label": "IRCTC", "official": {"domains": ["irctc.co.in"], "phones": [], "app_ids": []}},
]


class ScanSession:
    """Session tracker for in-flight scan execution and SSE streaming."""

    def __init__(self, scan_id: str, mode: int, query: str, official: Optional[dict] = None):
        self.scan_id = scan_id
        self.mode = mode
        self.query = query
        self.official = official or {}
        self.event_queue: queue.Queue = queue.Queue()
        self.events: list = []  # full history so a (re)connecting client can replay
        self.cond = threading.Condition()
        self.report: Optional[dict] = None
        self.error: Optional[str] = None
        self.is_done: bool = False

    def push(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()


# In-memory registry of active scan sessions
active_scans: Dict[str, ScanSession] = {}
scans_lock = threading.Lock()


def run_pipeline_task(session: ScanSession) -> None:
    """Worker function running in a background thread."""

    def on_progress(step: str, message: str, pct: int) -> None:
        event = {
            "type": "progress",
            "step": step,
            "message": message,
            "pct": pct,
        }
        session.push(event)

    try:
        # DEMO_MODE: replay the latest saved report for this preset (no network, no LLM)
        if DEMO_MODE:
            saved = find_latest_report(session.mode, session.query)
            if saved:
                for step, msg, pct in [
                    ("cache", "Loading cached evidence (demo mode)", 30),
                    ("clustering", "Restoring clustered evidence", 70),
                    ("scoring", "Restoring scores", 95),
                ]:
                    on_progress(step, msg, pct)
                    time.sleep(0.4)
                report = dict(saved)
                report["scan_id"] = session.scan_id
                if session.mode == 4:
                    send_protect_alert(report)  # best effort; skipped when Telegram isn't configured
                session.report = report
                session.push({"type": "done", "report": report})
                return

        if session.mode == 1:
            report = mode1_validate(session.query, progress_callback=on_progress)
        elif session.mode == 2:
            report = mode2_investigate(session.query, progress_callback=on_progress)
        elif session.mode == 3:
            report = mode3_discover(session.query, progress_callback=on_progress)
        elif session.mode == 4:
            report = mode4_protect(session.query, session.official, progress_callback=on_progress)
            if send_protect_alert(report):
                report.setdefault("warnings", []).append("Telegram alert sent.")
        else:
            raise ValueError(f"Invalid mode: {session.mode}")

        report["scan_id"] = session.scan_id
        session.report = report

        # Persist report to SQLite
        save_report(session.scan_id, session.mode, session.query, report)

        session.push({"type": "done", "report": report})
    except Exception as exc:
        logger.exception("Error executing pipeline for scan %s", session.scan_id)
        session.error = str(exc)
        session.push({"type": "error", "message": str(exc)})
    finally:
        session.is_done = True


@app.route("/api/scan", methods=["POST"])
def start_scan():
    """
    POST /api/scan
    Payload: {"mode": 1|2|3, "query": "..."}
    Returns: {"scan_id": "..."}
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    query = (data.get("query") or "").strip()

    if mode not in (1, 2, 3, 4):
        return jsonify({"error": "Invalid mode. Must be 1, 2, 3 or 4."}), 400
    if not query:
        return jsonify({"error": "Query string is required."}), 400

    official = data.get("official") if isinstance(data.get("official"), dict) else None
    if mode == 4 and not official:
        preset = next((p for p in DEMO_PRESETS if p["mode"] == 4 and p["query"].lower() == query.lower()), None)
        official = (preset or {}).get("official")

    scan_id = uuid.uuid4().hex[:8]
    session = ScanSession(scan_id, mode, query, official)

    with scans_lock:
        active_scans[scan_id] = session

    thread = threading.Thread(target=run_pipeline_task, args=(session,), daemon=True)
    thread.start()

    return jsonify({"scan_id": scan_id}), 202


@app.route("/api/scan/<scan_id>/stream", methods=["GET"])
def stream_scan(scan_id: str):
    """
    GET /api/scan/<id>/stream
    Server-Sent Events delivering progress and terminal 'done' or 'error' events.
    """
    with scans_lock:
        session = active_scans.get(scan_id)

    # Check if report already completed or stored in DB
    if not session:
        saved = get_report(scan_id)
        if saved:

            def immediate_generator():
                payload = json.dumps({"type": "done", "report": saved})
                yield f"data: {payload}\n\n"

            return Response(
                immediate_generator(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )
        return jsonify({"error": f"Scan ID '{scan_id}' not found."}), 404

    def sse_event_stream():
        # Replay history first, then follow new events; ping every 15 s while idle.
        idx = 0
        while True:
            with session.cond:
                if idx >= len(session.events):
                    session.cond.wait(timeout=15.0)
                pending = session.events[idx:]
            if not pending:
                yield ": ping\n\n"
                if session.is_done:
                    break
                continue
            for event in pending:
                idx += 1
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    return

    return Response(
        sse_event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/report/<scan_id>", methods=["GET"])
def get_report_endpoint(scan_id: str):
    """
    GET /api/report/<id>
    Retrieve full completed report.
    """
    with scans_lock:
        session = active_scans.get(scan_id)
        if session and session.report:
            return jsonify(session.report)

    saved = get_report(scan_id)
    if saved:
        return jsonify(saved)

    return jsonify({"error": f"Report '{scan_id}' not found."}), 404


def _load_report(scan_id: str):
    with scans_lock:
        session = active_scans.get(scan_id)
    if session and session.report:
        return session.report
    return get_report(scan_id)


@app.route("/api/compare", methods=["GET"])
def compare_endpoint():
    """
    GET /api/compare?a=<scan_id>&b=<scan_id>
    Side-by-side summary of two finished Mode 2 (Investigate) reports.
    """
    a, b = _load_report(request.args.get("a", "")), _load_report(request.args.get("b", ""))
    if not a or not b:
        return jsonify({"error": "Both reports must exist (run two Mode 2 scans first)."}), 404
    if a.get("mode") != 2 or b.get("mode") != 2:
        return jsonify({"error": "Compare works on two Mode 2 (Investigate) reports."}), 400
    return jsonify(compare_reports(a, b))


@app.route("/api/protect/official", methods=["GET", "POST"])
def protect_official():
    """
    POST {"brand": "...", "official": {"domains": [], "phones": [], "app_ids": []}, "watch": true, "interval_hours": 24}
    GET ?brand=...
    Saves the brand's official records (used by scans, the scheduler and the public page).
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        brand = (data.get("brand") or "").strip()
        if not brand or not isinstance(data.get("official"), dict):
            return jsonify({"error": "brand and official are required"}), 400
        save_official(brand, data["official"], watch=data.get("watch"), interval_hours=data.get("interval_hours"))
        return jsonify(get_official(brand))
    rec = get_official(request.args.get("brand", ""))
    return (jsonify(rec), 200) if rec else (jsonify({"error": "brand not set up"}), 404)


@app.route("/api/protect/watch", methods=["POST"])
def protect_watch():
    """POST {"brand": "...", "watch": true, "interval_hours": 24}: turn scheduled scans on/off (run monitor.py)."""
    data = request.get_json(silent=True) or {}
    brand = (data.get("brand") or "").strip()
    rec = get_official(brand)
    if not rec:
        return jsonify({"error": "Set up the brand first via /api/protect/official"}), 404
    save_official(brand, rec["official"], watch=bool(data.get("watch", True)), interval_hours=data.get("interval_hours"))
    return jsonify(get_official(brand))


@app.route("/api/protect/allow", methods=["GET", "POST", "DELETE"])
def protect_allow():
    """
    POST/DELETE {"brand": "...", "type": "helpline", "value": "98765 43210"}: mark a finding as genuine, or undo.
    GET ?brand=...: list allowed items. Allowed items are hidden from later scans.
    """
    if request.method == "GET":
        return jsonify(list_allowed(request.args.get("brand", "")))
    data = request.get_json(silent=True) or {}
    if not all(data.get(k) for k in ("brand", "type", "value")):
        return jsonify({"error": "brand, type and value are required"}), 400
    allow_item(data["brand"], data["type"], data["value"], allowed=request.method == "POST")
    return jsonify(list_allowed(data["brand"]))


@app.route("/verified/<path:brand>", methods=["GET"])
def verified_page(brand: str):
    """Public page listing a brand's verified official channels (shareable)."""
    rec = get_official(brand)
    if not rec:
        return Response("<h1>Not found</h1><p>This brand hasn't published its official channels.</p>", status=404,
                        mimetype="text/html")
    off = rec["official"]
    esc = html.escape
    def items(xs, fmt):
        return "".join(f"<li>{fmt(x)}</li>" for x in xs) or "<li><em>None listed</em></li>"
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Official channels: {esc(brand)}</title>
<style>body{{font-family:Inter,system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#0A0A0A}}
h1{{font-size:24px}}h2{{font-size:16px;margin-top:28px;color:#525252}}li{{margin:6px 0}}
.note{{background:#FEF3C7;border:1px solid #F59E0B;padding:12px;border-radius:8px;font-size:14px}}</style></head>
<body><h1>Official channels of {esc(brand)}</h1>
<p class="note">Anything not listed here is not ours. We never ask for fees to apply for jobs or internships.</p>
<h2>Websites</h2><ul>{items(off.get("domains", []), lambda d: f'<a href="https://{esc(d)}" rel="noopener">{esc(d)}</a>')}</ul>
<h2>Helpline numbers</h2><ul>{items(off.get("phones", []), esc)}</ul>
<h2>Apps</h2><ul>{items(off.get("app_ids", []), lambda a: f'<a href="https://play.google.com/store/apps/details?id={esc(a)}" rel="noopener">{esc(a)}</a>')}</ul>
<p style="color:#A3A3A3;font-size:12px">Published with GapScope Protect.</p></body></html>"""
    return Response(body, mimetype="text/html")


@app.route("/api/examples", methods=["GET"])
def get_examples():
    """
    GET /api/examples
    Returns standard demo presets, with cached=true when a saved report exists (loads instantly).
    """
    out = []
    for p in DEMO_PRESETS:
        item = {k: v for k, v in p.items() if k != "official"}
        item["cached"] = find_latest_report(p["mode"], p["query"]) is not None
        out.append(item)
    return jsonify(out)


@app.route("/api/health", methods=["GET"])
def get_health():
    """
    GET /api/health
    Returns cache and quota telemetry.
    """
    stats = get_cache_stats()
    return jsonify(stats)


@app.route("/api/mock/<int:mode>", methods=["GET"])
def get_mock_report(mode: int):
    """
    GET /api/mock/<mode>
    Returns valid mock report for frontend development.
    """
    if mode not in (1, 2, 3):
        return jsonify({"error": "Mock mode must be 1, 2, or 3."}), 400

    mock_path = Path(__file__).resolve().parent / "mock" / f"report_mode{mode}.json"
    if not mock_path.exists():
        return jsonify({"error": f"Mock file for mode {mode} not found."}), 404

    with open(mock_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data)


@app.route("/")
def serve_index():
    """Serve frontend index.html."""
    if frontend_dir.exists():
        return send_from_directory(frontend_dir, "index.html")
    return jsonify({"status": "GapScope Backend Active"})


@app.route("/<path:filename>")
def serve_static(filename: str):
    """Serve frontend static assets."""
    if filename.startswith("api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    if frontend_dir.exists() and (frontend_dir / filename).exists():
        return send_from_directory(frontend_dir, filename)
    return jsonify({"error": f"File '{filename}' not found."}), 404


if __name__ == "__main__":
    logger.info("Starting GapScope Backend on port %d...", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)
