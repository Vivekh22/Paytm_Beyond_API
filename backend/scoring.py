import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import MOMENTUM_WINDOW_DAYS, VIABILITY_BUILD_THRESHOLD, VIABILITY_PIVOT_THRESHOLD


def parse_loose_date(raw: Any) -> Optional[datetime]:
    """Parse the date formats SerpApi / You.com return. Unparseable -> None (never guessed)."""
    if not raw or not isinstance(raw, str):
        return None
    txt = raw.strip()
    now = datetime.now(timezone.utc)
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", txt, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        return now - timedelta(days=days)
    if txt.lower() in ("today", "yesterday"):
        return now - timedelta(days=0 if txt.lower() == "today" else 1)
    head = txt.split(",")[0].strip() if re.match(r"\d{1,2}/\d{1,2}/\d{4},", txt) else txt
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            dt = datetime.strptime(head if fmt == "%m/%d/%Y" else txt[: len(txt)], fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", txt)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


def compute_trend_metrics(points: List[Dict[str, Any]]) -> Tuple[float, str, float, float]:
    """
    Compute mean interest, direction, change percentage, and slope bonus.
    Compares last 3 months to previous 9 months.
    Returns: (mean_val, direction, change_pct, slope_bonus)
    """
    if not points:
        return 0.0, "flat", 0.0, 5.0

    values = [p.get("value", 0) for p in points]
    mean_val = sum(values) / len(values)

    # Trends returns weekly points for "today 12-m" (about 53), so split by share of the
    # series, not by count: the last quarter of the period vs the first three quarters.
    if len(values) >= 4:
        split_idx = int(len(values) * 0.75)
        prev_9 = values[:split_idx]
        last_3 = values[split_idx:]
    else:
        return mean_val, "flat", 0.0, 5.0

    prev_avg = sum(prev_9) / max(len(prev_9), 1)
    last_avg = sum(last_3) / max(len(last_3), 1)

    change_pct = ((last_avg - prev_avg) / max(prev_avg, 1.0)) * 100.0

    if last_avg > prev_avg * 1.05:
        direction = "rising"
        slope_bonus = 10.0
    elif last_avg < prev_avg * 0.95:
        direction = "falling"
        slope_bonus = 0.0
    else:
        direction = "flat"
        slope_bonus = 5.0

    return mean_val, direction, round(change_pct, 1), slope_bonus


def compute_viability_score(
    trend_points: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    competitors: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
    total_reviews_scanned: int,
    anchor_values: Optional[List[int]] = None,
    anchor_name: str = "",
) -> Dict[str, Any]:
    """
    Compute deterministic Viability Score (0-100) for Mode 1.
    Factors:
      1. Demand (Max 30)
      2. Pain Intensity (Max 30)
      3. Competition Gap (Max 20)
      4. Momentum (Max 10)
      5. Evidence Confidence (Max 10)
    """
    # 1. Demand (Max 30)
    # Trends values are relative (each request peaks at 100), so a series' own mean says
    # little about volume. When an anchor term was fetched in the same request, demand is
    # the keyword's mean relative to the anchor's mean (capped at 1x).
    mean_trends, direction, change_pct, slope_bonus = compute_trend_metrics(trend_points)
    if not trend_points:
        demand_score = 0
        demand_expl = "No Google Trends data for this keyword in India"
    elif anchor_values:
        anchor_mean = sum(anchor_values) / max(len(anchor_values), 1)
        ratio = mean_trends / max(anchor_mean, 1.0)
        demand_score = min(30, max(0, round(min(ratio, 1.0) * 20.0 + slope_bonus)))
        demand_expl = (
            f"Searched {ratio:.2f}x as often as '{anchor_name}' in India; "
            f"{direction} ({change_pct:+.1f}% last 3 months vs prior 9)"
        )
    else:
        demand_score = min(30, max(0, round(mean_trends * 0.2 + slope_bonus)))
        demand_expl = (
            f"Relative interest {mean_trends:.1f}/100 (no anchor comparison available), "
            f"{direction} ({change_pct:+.1f}%)"
        )

    # 2. Pain Intensity (Max 30)
    # Share of scanned 1★ reviews that land in top 3 clusters
    pain_clusters = [c for c in clusters if c.get("group", "pain") == "pain"]
    top_3_clusters = sorted(
        pain_clusters, key=lambda c: c.get("frequency", {}).get("count", 0), reverse=True
    )[:3]

    top_3_eids = set()
    for c in top_3_clusters:
        for eid in c.get("evidence_ids", []):
            if eid in evidence_map:
                top_3_eids.add(eid)

    # Denominator = the items the model actually saw (frequency.total), not every review fetched.
    pool = max([c.get("frequency", {}).get("total", 0) for c in pain_clusters] + [0])
    denominator = max(pool or total_reviews_scanned, len(top_3_eids), 1)
    share = min(1.0, len(top_3_eids) / denominator)
    pain_score = min(30, max(0, round(share * 30.0)))
    pain_expl = (
        f"{len(top_3_eids)} of {denominator} analysed items fall into the top 3 recurring "
        f"complaint themes ({int(share * 100)}%)"
    )

    # 3. Competition Gap (Max 20)
    comp_evidence_ids = []
    ratings = []
    for c in competitors or []:
        try:
            if c.get("rating"):
                ratings.append(float(c["rating"]))
        except (TypeError, ValueError):
            pass
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        gap_raw = ((5.0 - avg_rating) / 2.0) * 20.0
        comp_gap_score = min(20, max(0, round(gap_raw)))
        comp_expl = f"Average rating of {len(ratings)} incumbent app(s): {avg_rating:.1f}★"
    else:
        comp_gap_score = 10
        comp_expl = "No rated app competitors found; neutral score (not evidence of an open market)"

    # 4. Momentum (Max 10)
    # Only DATED news items inside the window count; undated items are ignored, not guessed.
    cutoff = datetime.now(timezone.utc) - timedelta(days=MOMENTUM_WINDOW_DAYS)
    recent_news_and_web = []
    undated = 0
    for eid, item in evidence_map.items():
        if item.get("source") not in ("google_news", "you_news"):
            continue
        dt = parse_loose_date(item.get("date"))
        if dt is None:
            undated += 1
        elif dt >= cutoff:
            recent_news_and_web.append(eid)
    momentum_count = len(recent_news_and_web)
    momentum_score = min(10, round(momentum_count * 10 / 8))
    momentum_expl = (
        f"{momentum_count} news items dated within the last {MOMENTUM_WINDOW_DAYS} days"
        + (f" ({undated} undated items not counted)" if undated else "")
    )

    # 5. Evidence Confidence (Max 10)
    # Confidence = depth of first-hand reviews + breadth of independent source families.
    families = {"play_store": "Play Store", "reddit": "Reddit", "google_news": "News",
                "you_news": "News", "you_web": "Web"}
    present = sorted({families[i.get("source")] for i in evidence_map.values() if i.get("source") in families})
    play_count = sum(1 for i in evidence_map.values() if i.get("source") == "play_store")
    review_pts = min(4, play_count // 30)
    source_pts = min(6, round(len(present) * 1.5))
    conf_score = review_pts + source_pts
    total_ev = len(evidence_map)
    conf_expl = (
        f"{play_count} app reviews + {len(present)} source families ({', '.join(present) or 'none'})"
    )

    # Total & Verdict
    total_score = min(
        100,
        max(
            0,
            demand_score + pain_score + comp_gap_score + momentum_score + conf_score,
        ),
    )

    if total_score >= VIABILITY_BUILD_THRESHOLD:
        label = "BUILD"
        headline = "Strong demand and acute user pain indicate a prime market opportunity"
    elif total_score >= VIABILITY_PIVOT_THRESHOLD:
        label = "PIVOT"
        headline = "Real pain exists, but crowded market requires differentiated positioning"
    else:
        label = "KILL"
        headline = "Weak search demand and satisfied incumbents suggest poor market timing"

    breakdown = [
        {
            "factor": "Demand",
            "score": demand_score,
            "max": 30,
            "explanation": demand_expl,
            "evidence_ids": [],
        },
        {
            "factor": "Pain intensity",
            "score": pain_score,
            "max": 30,
            "explanation": pain_expl,
            "evidence_ids": list(top_3_eids)[:5],
        },
        {
            "factor": "Competition gap",
            "score": comp_gap_score,
            "max": 20,
            "explanation": comp_expl,
            "evidence_ids": list(top_3_eids)[5:10],
        },
        {
            "factor": "Momentum",
            "score": momentum_score,
            "max": 10,
            "explanation": momentum_expl,
            "evidence_ids": recent_news_and_web[:5],
        },
        {
            "factor": "Evidence confidence",
            "score": conf_score,
            "max": 10,
            "explanation": conf_expl,
            "evidence_ids": [],
        },
    ]

    return {
        "kind": "viability",
        "label": label,
        "score": total_score,
        "headline": headline,
        "breakdown": breakdown,
    }


def compute_trajectory(
    trend_points: List[Dict[str, Any]],
    all_time_rating: float,
    newest_reviews: List[Dict[str, Any]],
    news_classifications: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute Mode 2 Trajectory combining:
      (a) Trends change % (last 3m vs prev 9m)
      (b) Recent review ratings vs all-time rating
      (c) News sentiment ratio
    Each votes +1 / 0 / -1.
    Sum >= +2: GROWING, <= -2: DECLINING, else STAGNATING.
    """
    breakdown = []
    votes = 0

    # Signal 1: Trends Change
    mean_val, direction, change_pct, _ = compute_trend_metrics(trend_points)
    if change_pct > 5.0:
        trend_vote = 1
        trend_expl = f"Search interest rising ({change_pct:+.1f}% vs prior period)"
    elif change_pct < -5.0:
        trend_vote = -1
        trend_expl = f"Search interest falling ({change_pct:+.1f}% vs prior period)"
    else:
        trend_vote = 0
        trend_expl = f"Search interest flat ({change_pct:+.1f}%)"
    votes += trend_vote
    breakdown.append(
        {
            "factor": "Search Interest Trajectory",
            "score": trend_vote,
            "max": 1,
            "explanation": trend_expl,
            "evidence_ids": [],
        }
    )

    # Signal 2: Recent Reviews Trend
    if newest_reviews and all_time_rating:
        new_ratings = [r.get("rating", 0) for r in newest_reviews if r.get("rating")]
        new_avg = sum(new_ratings) / len(new_ratings) if new_ratings else all_time_rating
        diff = new_avg - all_time_rating
        if diff > 0.1:
            rev_vote = 1
            rev_expl = f"Recent reviews ({new_avg:.2f}★) improving vs all-time ({all_time_rating:.2f}★)"
        elif diff < -0.1:
            rev_vote = -1
            rev_expl = f"Recent reviews ({new_avg:.2f}★) degrading vs all-time ({all_time_rating:.2f}★)"
        else:
            rev_vote = 0
            rev_expl = f"Recent reviews ({new_avg:.2f}★) aligned with all-time ({all_time_rating:.2f}★)"
    else:
        rev_vote = 0
        diff = 0.0
        rev_expl = "Insufficient recent reviews to detect rating drift"

    votes += rev_vote
    recent_eids = [
        r.get("id")
        for r in newest_reviews[:5]
        if r.get("id") and r.get("id") in evidence_map
    ]
    breakdown.append(
        {
            "factor": "Review Sentiment Drift",
            "score": rev_vote,
            "max": 1,
            "explanation": rev_expl,
            "evidence_ids": recent_eids,
        }
    )

    # Signal 3: News Sentiment Ratio
    pos_items = [n["evidence_id"] for n in news_classifications if n.get("sentiment") == "positive"]
    neg_items = [n["evidence_id"] for n in news_classifications if n.get("sentiment") == "negative"]
    pos_cnt = len(pos_items)
    neg_cnt = len(neg_items)
    total_classified = pos_cnt + neg_cnt

    if total_classified > 0:
        sentiment_ratio = (pos_cnt - neg_cnt) / total_classified
        if sentiment_ratio > 0.2:
            news_vote = 1
            news_expl = f"Positive news coverage dominates ({pos_cnt} positive vs {neg_cnt} negative)"
        elif sentiment_ratio < -0.2:
            news_vote = -1
            news_expl = f"Negative media headwinds detected ({neg_cnt} negative vs {pos_cnt} positive)"
        else:
            news_vote = 0
            news_expl = f"Balanced media coverage ({pos_cnt} positive, {neg_cnt} negative)"
    else:
        news_vote = 0
        news_expl = "No recent press coverage found to evaluate"

    votes += news_vote
    news_eids = (pos_items + neg_items)[:5]
    breakdown.append(
        {
            "factor": "Media Sentiment",
            "score": news_vote,
            "max": 1,
            "explanation": news_expl,
            "evidence_ids": [eid for eid in news_eids if eid in evidence_map],
        }
    )

    # Verdict Label
    if votes >= 2:
        label = "GROWING"
        headline = "Accelerating momentum across search volume, customer sentiment, and media"
    elif votes <= -2:
        label = "DECLINING"
        headline = "Operational strain and deteriorating user satisfaction signaling decline"
    else:
        label = "STAGNATING"
        headline = "Steady performance with visible churn risks and mixed market signals"

    return {
        "kind": "trajectory",
        "label": label,
        "score": votes,
        "headline": headline,
        "breakdown": breakdown,
    }


def compute_discovery_verdict(
    clusters: List[Dict[str, Any]],
    competitors: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute Mode 3 Discovery verdict summarizing cross-competitor opportunities.
    """
    cross_app_clusters = [
        c for c in clusters if len(c.get("apps_affected", [])) >= 2
    ]
    num_cross = len(cross_app_clusters)
    total_apps = len(competitors)

    headline = (
        f"Identified {num_cross} cross-competitor systemic gaps across {total_apps} market leaders"
        if num_cross > 0
        else f"Analyzed {total_apps} top applications for category-wide pain patterns"
    )

    top_evidence_ids = []
    for c in clusters[:3]:
        for eid in c.get("evidence_ids", [])[:3]:
            if eid in evidence_map and eid not in top_evidence_ids:
                top_evidence_ids.append(eid)

    breakdown = [
        {
            "factor": "Cross-App Systemic Gaps",
            "score": min(num_cross * 10, 30),
            "max": 30,
            "explanation": f"{num_cross} complaint clusters span multiple leading competitors",
            "evidence_ids": top_evidence_ids,
        },
        {
            "factor": "Incumbent Saturation",
            "score": min(total_apps * 5, 20),
            "max": 20,
            "explanation": f"Evaluated top {total_apps} benchmark apps in the category",
            "evidence_ids": [],
        },
    ]

    return {
        "kind": "discovery",
        "label": None,
        "score": None,
        "headline": headline,
        "breakdown": breakdown,
    }
