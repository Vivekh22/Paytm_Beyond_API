"""
Mode 2 timeline: lines up dated signals month by month and marks turning points.

Everything here is deterministic. Turning points are rule-based ("rating fell 0.6 stars
vs the previous month"), each linked to the evidence behind it. They show what changed
and when; they do not claim to prove why.
"""
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scoring import parse_loose_date


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:400]


def _month_of_point(p: Dict[str, Any]) -> Optional[str]:
    ts = p.get("ts")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m")
        except (TypeError, ValueError, OSError):
            pass
    dt = parse_loose_date(p.get("date"))
    if dt:
        return dt.strftime("%Y-%m")
    # Weekly Trends labels look like "Nov 24 – 30, 2025": use month name + year
    m = re.match(r"([A-Za-z]{3})\D.*?(\d{4})", str(p.get("date") or ""))
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%b %Y").strftime("%Y-%m")
        except ValueError:
            return None
    return None


def build_timeline(
    trend_points: List[Dict[str, Any]],
    newest_reviews: List[Dict[str, Any]],
    one_star_reviews: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
    news_classified: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    text_to_id = {}
    for eid, ev in evidence_map.items():
        if ev.get("source") == "play_store":
            text_to_id.setdefault(ev.get("text"), eid)

    months: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "interest": [], "ratings": [], "complaints": 0, "complaint_ids": [],
        "review_ids": [], "news_pos": [], "news_neg": [], "news_neu": [],
    })

    for p in trend_points or []:
        mk = _month_of_point(p)
        if mk:
            months[mk]["interest"].append(p.get("value", 0) or 0)

    # Ratings come only from the NEWEST reviews: the 1-star and 5-star sets are filtered and would bias averages.
    for r in newest_reviews or []:
        dt = parse_loose_date(r.get("date"))
        if not dt:
            continue
        mk = dt.strftime("%Y-%m")
        try:
            months[mk]["ratings"].append(int(r.get("rating")))
        except (TypeError, ValueError):
            continue
        eid = text_to_id.get(_norm(r.get("snippet", "")))
        if eid:
            months[mk]["review_ids"].append(eid)

    for r in one_star_reviews or []:
        dt = parse_loose_date(r.get("date"))
        if not dt:
            continue
        mk = dt.strftime("%Y-%m")
        months[mk]["complaints"] += 1
        eid = text_to_id.get(_norm(r.get("snippet", "")))
        if eid:
            months[mk]["complaint_ids"].append(eid)

    sentiment = {n.get("evidence_id"): n.get("sentiment") for n in news_classified or []}
    for eid, ev in evidence_map.items():
        if ev.get("source") not in ("google_news", "you_news"):
            continue
        dt = parse_loose_date(ev.get("date"))
        if not dt:
            continue
        mk = dt.strftime("%Y-%m")
        bucket = {"positive": "news_pos", "negative": "news_neg"}.get(sentiment.get(eid), "news_neu")
        months[mk][bucket].append(eid)

    if not months:
        return None

    rows = []
    for mk in sorted(months):
        m = months[mk]
        rows.append({
            "month": mk,
            "search_interest": round(sum(m["interest"]) / len(m["interest"]), 1) if m["interest"] else None,
            "avg_rating": round(sum(m["ratings"]) / len(m["ratings"]), 2) if len(m["ratings"]) >= 3 else None,
            "reviews_count": len(m["ratings"]),
            "complaints": m["complaints"],
            "news_positive": len(m["news_pos"]),
            "news_negative": len(m["news_neg"]),
            "evidence_ids": (m["complaint_ids"][:3] + m["news_neg"][:2] + m["news_pos"][:2] + m["review_ids"][:2]),
            "_m": m,
        })

    turning: List[Dict[str, Any]] = []

    # 1. Search interest vs the average of the previous 3 months with data
    hist: List[float] = []
    for row in rows:
        si = row["search_interest"]
        if si is None:
            continue
        if len(hist) >= 3:
            base = sum(hist[-3:]) / 3
            if base >= 5:
                change = (si - base) / base * 100
                if abs(change) >= 25:
                    turning.append({
                        "month": row["month"], "kind": "search_rise" if change > 0 else "search_drop",
                        "description": f"Search interest {'rose' if change > 0 else 'fell'} {abs(change):.0f}% vs the previous 3 months",
                        "evidence_ids": [],
                    })
        hist.append(si)

    # 2. Rating moves between consecutive months that have >= 3 newest reviews
    prev = None
    for row in rows:
        if row["avg_rating"] is None:
            continue
        if prev is not None and abs(row["avg_rating"] - prev["avg_rating"]) >= 0.5:
            up = row["avg_rating"] > prev["avg_rating"]
            turning.append({
                "month": row["month"], "kind": "rating_rise" if up else "rating_drop",
                "description": f"Average new-review rating {'rose' if up else 'fell'} from {prev['avg_rating']}★ to {row['avg_rating']}★",
                "evidence_ids": row["_m"]["review_ids"][:3],
            })
        prev = row

    # 3. Complaint spikes: >= 2x the median of months with complaints, and at least 3
    counts = [r["complaints"] for r in rows if r["complaints"]]
    if len(counts) >= 3:
        med = statistics.median(counts)
        for row in rows:
            if row["complaints"] >= 3 and row["complaints"] >= 2 * med:
                turning.append({
                    "month": row["month"], "kind": "complaint_spike",
                    "description": f"{row['complaints']} one-star reviews, about {row['complaints'] / med:.1f}x a typical month",
                    "evidence_ids": row["_m"]["complaint_ids"][:3],
                })

    # 4. Dated news
    for row in rows:
        m = row["_m"]
        if m["news_neg"]:
            turning.append({"month": row["month"], "kind": "negative_news",
                            "description": f"{len(m['news_neg'])} negative news item(s)",
                            "evidence_ids": m["news_neg"][:3]})
        if m["news_pos"]:
            turning.append({"month": row["month"], "kind": "positive_news",
                            "description": f"{len(m['news_pos'])} positive news item(s)",
                            "evidence_ids": m["news_pos"][:3]})

    for row in rows:
        row.pop("_m", None)
    valid = set(evidence_map)
    for t in turning:
        t["evidence_ids"] = [e for e in t["evidence_ids"] if e in valid]
    turning.sort(key=lambda t: t["month"])

    return {
        "months": rows,
        "turning_points": turning,
        "note": "Signals that line up in time; they show what changed and when, not proof of cause.",
    }
