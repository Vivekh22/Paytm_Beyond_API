import json
import logging
import os
from pathlib import Path
import queue
import threading
import uuid
from typing import Dict, Optional

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from cache import get_cache_stats, get_report, save_report
from config import PORT
from pipelines import mode1_validate, mode2_investigate, mode3_discover

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
)
logger = logging.getLogger(__name__)

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
]


class ScanSession:
    """Session tracker for in-flight scan execution and SSE streaming."""

    def __init__(self, scan_id: str, mode: int, query: str):
        self.scan_id = scan_id
        self.mode = mode
        self.query = query
        self.event_queue: queue.Queue = queue.Queue()
        self.report: Optional[dict] = None
        self.error: Optional[str] = None
        self.is_done: bool = False


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
        session.event_queue.put(event)

    try:
        if session.mode == 1:
            report = mode1_validate(session.query, progress_callback=on_progress)
        elif session.mode == 2:
            report = mode2_investigate(session.query, progress_callback=on_progress)
        elif session.mode == 3:
            report = mode3_discover(session.query, progress_callback=on_progress)
        else:
            raise ValueError(f"Invalid mode: {session.mode}")

        report["scan_id"] = session.scan_id
        session.report = report

        # Persist report to SQLite
        save_report(session.scan_id, session.mode, session.query, report)

        session.event_queue.put({"type": "done", "report": report})
    except Exception as exc:
        logger.exception("Error executing pipeline for scan %s", session.scan_id)
        session.error = str(exc)
        session.event_queue.put({"type": "error", "message": str(exc)})
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

    if mode not in (1, 2, 3):
        return jsonify({"error": "Invalid mode. Must be 1, 2, or 3."}), 400
    if not query:
        return jsonify({"error": "Query string is required."}), 400

    scan_id = uuid.uuid4().hex[:8]
    session = ScanSession(scan_id, mode, query)

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
        # Stream events from session queue
        while True:
            try:
                event = session.event_queue.get(timeout=35.0)
                payload = json.dumps(event)
                yield f"data: {payload}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                # Keep-alive heartbeat comment
                yield ": ping\n\n"
                if session.is_done:
                    break

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


@app.route("/api/examples", methods=["GET"])
def get_examples():
    """
    GET /api/examples
    Returns standard demo presets.
    """
    return jsonify(DEMO_PRESETS)


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


if __name__ == "__main__":
    logger.info("Starting GapScope Backend on port %d...", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)
