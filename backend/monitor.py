"""
Scheduled Protect scans.

Brands are added to the watchlist through POST /api/protect/watch (or the setup call).
Run this next to the server:  python monitor.py          (loops, checks every 10 minutes)
                              python monitor.py --once   (one pass, e.g. from Windows Task Scheduler)
Each due brand is re-scanned; Telegram alerts go out only for NEW suspected items.
"""
import argparse
import logging
import time

from cache import list_watched, mark_watch_run, save_report
from notify import send_protect_alert
from protect import mode4_protect

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("monitor")


def run_once() -> int:
    ran = 0
    now = time.time()
    for w in list_watched():
        if now - (w["last_run"] or 0) < w["interval_hours"] * 3600:
            continue
        log.info("Scanning %s ...", w["brand"])
        try:
            report = mode4_protect(w["brand"], w["official"])
            save_report(report["scan_id"], 4, w["brand"], report)
            sent = send_protect_alert(report)
            log.info("  %d finding(s), %d new, alert sent: %s", len(report["findings"]), report.get("new_count", 0), sent)
        except Exception as exc:
            log.error("  scan failed: %s", exc)
        mark_watch_run(w["brand"])
        ran += 1
    return ran


def main():
    ap = argparse.ArgumentParser(description="GapScope Protect scheduler")
    ap.add_argument("--once", action="store_true", help="run one pass and exit")
    ap.add_argument("--every", type=int, default=600, help="seconds between passes (default 600)")
    args = ap.parse_args()
    if args.once:
        log.info("Ran %d scan(s).", run_once())
        return
    while True:
        run_once()
        time.sleep(args.every)


if __name__ == "__main__":
    main()
