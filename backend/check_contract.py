"""
Contract check for GapScope reports.

Usage:
  python check_contract.py                 # checks mock/*.json and every report saved in cache.db
  python check_contract.py path/to/x.json  # checks specific files
Exits 1 if any report breaks the shared JSON contract.
"""
import json
import sqlite3
import sys
from pathlib import Path

from config import DB_PATH

ROOT_KEYS = {"scan_id", "mode", "query", "generated_at", "keywords", "credits", "verdict",
             "trend", "competitors", "clusters", "opportunities", "news", "evidence", "warnings"}
SOURCES = {"play_store", "reddit", "google_news", "you_web", "you_news",
           "google_search", "google_maps", "google_jobs", "app_store"}
LABELS = {"BUILD", "PIVOT", "KILL", "GROWING", "STAGNATING", "DECLINING", None}


def check(report: dict) -> list:
    errs = []
    missing = ROOT_KEYS - set(report)
    if missing:
        errs.append(f"missing keys: {sorted(missing)}")
    ev = report.get("evidence") or {}
    for eid, item in ev.items():
        if item.get("id") != eid:
            errs.append(f"evidence key/id mismatch: {eid}")
        if item.get("source") not in SOURCES:
            errs.append(f"{eid}: bad source {item.get('source')!r}")

    def refs(where, ids):
        for i in ids or []:
            if i not in ev:
                errs.append(f"{where}: evidence id {i} not in evidence map")

    v = report.get("verdict") or {}
    if v.get("label") not in LABELS:
        errs.append(f"verdict.label invalid: {v.get('label')!r}")
    if report.get("mode") in (2, 3) and v.get("kind") == "viability":
        errs.append("modes 2/3 must not use a viability verdict")
    for b in v.get("breakdown", []):
        refs(f"breakdown[{b.get('factor')}]", b.get("evidence_ids"))
    cluster_ids = set()
    for c in report.get("clusters", []):
        cluster_ids.add(c.get("id"))
        refs(f"cluster {c.get('id')}", c.get("evidence_ids"))
        if c.get("group") not in ("pain", "strength"):
            errs.append(f"cluster {c.get('id')}: bad group")
        if not c.get("evidence_ids") and not c.get("ai_suggested"):
            errs.append(f"cluster {c.get('id')}: no evidence but ai_suggested is false")
    for o in report.get("opportunities", []):
        refs(f"opportunity {o.get('id')}", o.get("evidence_ids"))
        for cid in o.get("addresses_cluster_ids", []):
            if cid not in cluster_ids:
                errs.append(f"opportunity {o.get('id')}: unknown cluster {cid}")
    for n in report.get("news", []):
        refs("news", [n.get("evidence_id")])
    for f in report.get("findings", []) or []:
        refs(f"finding {f.get('id')}", f.get("evidence_ids"))
        if f.get("severity") not in ("high", "medium", "info"):
            errs.append(f"finding {f.get('id')}: bad severity")
    tl = report.get("timeline")
    if tl:
        for m in tl.get("months", []):
            refs(f"timeline {m.get('month')}", m.get("evidence_ids"))
        for tp in tl.get("turning_points", []):
            refs(f"turning point {tp.get('month')}", tp.get("evidence_ids"))
    if report.get("mode") not in (1, 2, 3, 4):
        errs.append(f"bad mode {report.get('mode')!r}")
    t = report.get("trend")
    if t is not None and not t.get("points"):
        errs.append("trend must be null when it has no points")
    return errs


def main() -> int:
    reports = []
    args = sys.argv[1:]
    if args:
        for a in args:
            reports.append((a, json.loads(Path(a).read_text(encoding="utf-8"))))
    else:
        for f in sorted((Path(__file__).parent / "mock").glob("*.json")):
            reports.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
        try:
            conn = sqlite3.connect(DB_PATH)
            for sid, mode, q, rep in conn.execute("SELECT scan_id, mode, query, report FROM reports"):
                reports.append((f"db:{sid} (mode {mode}, {q})", json.loads(rep)))
            conn.close()
        except Exception as exc:
            print(f"(could not read reports from {DB_PATH}: {exc})")
    failed = 0
    for name, rep in reports:
        errs = check(rep)
        print(("OK   " if not errs else "FAIL ") + name)
        for e in errs[:15]:
            print("     - " + e)
        failed += bool(errs)
    print(f"\n{len(reports) - failed}/{len(reports)} reports pass the contract")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
