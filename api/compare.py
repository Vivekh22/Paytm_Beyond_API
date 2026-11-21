"""Compare mode: two finished Investigate (Mode 2) reports side by side."""
from typing import Any, Dict, Optional


def summarize(report: Dict[str, Any]) -> Dict[str, Any]:
    comp = (report.get("competitors") or [{}])[0]
    clusters = report.get("clusters") or []
    trend = report.get("trend") or {}
    timeline = report.get("timeline") or {}
    months = [m for m in timeline.get("months", []) if m.get("avg_rating") is not None]
    verdict = report.get("verdict") or {}
    return {
        "scan_id": report.get("scan_id"),
        "name": comp.get("name") or report.get("query"),
        "rating": comp.get("rating"),
        "installs": comp.get("installs"),
        "trajectory": verdict.get("label"),
        "headline": verdict.get("headline"),
        "search_change_pct": trend.get("change_pct"),
        "search_direction": trend.get("direction"),
        "latest_new_review_rating": months[-1]["avg_rating"] if months else None,
        "top_pains": [{"id": c["id"], "title": c["title"], "count": c["frequency"]["count"]}
                      for c in clusters if c.get("group") == "pain"][:3],
        "top_strengths": [{"id": c["id"], "title": c["title"], "count": c["frequency"]["count"]}
                          for c in clusters if c.get("group") == "strength"][:3],
        "turning_points": len(timeline.get("turning_points", [])),
        "negative_news": sum(1 for n in report.get("news", []) if n.get("sentiment") == "negative"),
        "positive_news": sum(1 for n in report.get("news", []) if n.get("sentiment") == "positive"),
    }


def compare_reports(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    sa, sb = summarize(a), summarize(b)

    def better(key: str, higher_is_better: bool = True) -> Optional[str]:
        va, vb = sa.get(key), sb.get(key)
        if va is None or vb is None or va == vb:
            return None
        return sa["name"] if (va > vb) == higher_is_better else sb["name"]

    pains_a = {p["title"].lower() for p in sa["top_pains"]}
    pains_b = {p["title"].lower() for p in sb["top_pains"]}
    return {
        "a": sa,
        "b": sb,
        "leader": {
            "rating": better("rating"),
            "search_change": better("search_change_pct"),
            "latest_new_review_rating": better("latest_new_review_rating"),
            "fewer_negative_news": better("negative_news", higher_is_better=False),
        },
        "shared_pains": sorted(pains_a & pains_b),
        "note": "Both sides come from their own cited reports; open either report for the evidence.",
    }
