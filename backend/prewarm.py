import argparse
import json
import logging
import sys
from typing import Any, Dict, List

from app import DEMO_PRESETS
from config import DEMO_MODE, SERPAPI_KEY, YDC_API_KEY
from pipelines import mode1_validate, mode2_investigate, mode3_discover

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("prewarm")


def estimate_serpapi_calls() -> Dict[str, Any]:
    """
    Calculate dry-run estimate for SerpApi calls across all presets:
    - Mode 1: Trends (1) + Play Search (1) + News (1) + Reddit (1) + Play Reviews (3) = 7 calls
    - Mode 2: Play Search (1) + 1★ Reviews (1) + 5★ Reviews (1) + Newest Reviews (1) + News (1) + Trends (1) + Reddit (1) = 7 calls
    - Mode 3: Play Search (1) + Play Reviews (5) + Reddit (1) + Trends (1) = 8 calls
    """
    estimates = []
    total = 0
    for preset in DEMO_PRESETS:
        mode = preset["mode"]
        calls = 7 if mode in (1, 2) else 8
        estimates.append(
            {
                "mode": mode,
                "label": preset["label"],
                "query": preset["query"],
                "estimated_serpapi_calls": calls,
            }
        )
        total += calls

    return {"total_estimated_serpapi_calls": total, "presets": estimates}


def run_prewarm():
    """Execute all presets sequentially and log cache filling."""
    logger.info("Starting GapScope Prewarm Engine...")
    logger.info(
        "Config status: DEMO_MODE=%s | SERPAPI_KEY=%s | YDC_API_KEY=%s",
        DEMO_MODE,
        "configured" if SERPAPI_KEY else "MISSING",
        "configured" if YDC_API_KEY else "MISSING",
    )

    total_credits = {
        "serpapi_live": 0,
        "serpapi_cached": 0,
        "youcom_live": 0,
        "youcom_cached": 0,
    }

    for idx, preset in enumerate(DEMO_PRESETS, start=1):
        mode = preset["mode"]
        query = preset["query"]
        label = preset["label"]

        logger.info(
            "[%d/%d] Prewarming Mode %d: '%s' (%s)...",
            idx,
            len(DEMO_PRESETS),
            mode,
            query,
            label,
        )

        def log_progress(step, msg, pct):
            logger.info("   -> [%d%%] %s: %s", pct, step, msg)

        try:
            if mode == 1:
                report = mode1_validate(query, progress_callback=log_progress)
            elif mode == 2:
                report = mode2_investigate(query, progress_callback=log_progress)
            elif mode == 3:
                report = mode3_discover(query, progress_callback=log_progress)
            else:
                continue

            credits = report.get("credits", {})
            for k in total_credits:
                total_credits[k] += credits.get(k, 0)

            logger.info(
                "   [DONE] Verdict: %s | Credits used in this run: %s",
                report.get("verdict", {}).get("label")
                or report.get("verdict", {}).get("kind"),
                credits,
            )
        except Exception as e:
            logger.error("   [ERROR] Failed to prewarm '%s': %s", query, e)

    logger.info("==========================================")
    logger.info("Prewarm complete! Total credits recorded:")
    logger.info(json.dumps(total_credits, indent=2))
    logger.info("Cache database is primed for live demo presentation.")


def main():
    parser = argparse.ArgumentParser(description="GapScope Demo Prewarm Tool")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate SerpApi calls without executing network requests",
    )
    args = parser.parse_args()

    if args.dry_run:
        est = estimate_serpapi_calls()
        print("\n=== GapScope Prewarm Dry-Run Estimation ===")
        print(f"Total Presets: {len(est['presets'])}")
        print(f"Total Estimated SerpApi Calls: {est['total_estimated_serpapi_calls']}")
        print("\nBreakdown by Preset:")
        for p in est["presets"]:
            print(
                f"  - Mode {p['mode']} [{p['label']}]: ~{p['estimated_serpapi_calls']} calls"
            )
        print("===========================================\n")
        sys.exit(0)

    run_prewarm()


if __name__ == "__main__":
    main()
