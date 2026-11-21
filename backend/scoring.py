from typing import Any, Dict, List, Optional, Tuple

from config import VIABILITY_BUILD_THRESHOLD, VIABILITY_PIVOT_THRESHOLD


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

    if len(values) >= 12:
        prev_9 = values[:9]
        last_3 = values[9:]
    elif len(values) >= 4:
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
    mean_trends, direction, change_pct, slope_bonus = compute_trend_metrics(trend_points)
    demand_base = mean_trends * 0.2
    demand_score = min(30, max(0, round(demand_base + slope_bonus)))
    demand_expl = (
        f"Avg interest {mean_trends:.1f}/100, {direction} trajectory ({change_pct:+.1f}%)"
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

    denominator = max(total_reviews_scanned, len(top_3_eids), 1)
    share = min(1.0, len(top_3_eids) / denominator)
    pain_score = min(30, max(0, round(share * 30.0)))
    pain_expl = f"Top 3 pain themes account for {int(share * 100)}% of scanned critical reviews"

    # 3. Competition Gap (Max 20)
    comp_evidence_ids = []
    if competitors:
        ratings = [c.get("rating", 0.0) for c in competitors if c.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 4.0
        gap_raw = ((5.0 - avg_rating) / 2.0) * 20.0
        comp_gap_score = min(20, max(0, round(gap_raw)))
        comp_expl = f"Average incumbent rating {avg_rating:.1f}★ indicates room for disruption"
    else:
        comp_gap_score = 10
        comp_expl = "No dominant mobile incumbents; open blue-ocean / web opportunity"

    # 4. Momentum (Max 10)
    recent_news_and_web = [
        eid
        for eid, item in evidence_map.items()
        if item.get("source") in ("google_news", "you_news", "you_web")
    ]
    momentum_count = len(recent_news_and_web)
    momentum_score = min(10, momentum_count)
    momentum_expl = f"{momentum_count} external signals & news items found in recent coverage"

    # 5. Evidence Confidence (Max 10)
    total_ev = len(evidence_map)
    conf_score = round(min(total_ev / 100.0, 1.0) * 10.0)
    conf_expl = f"{total_ev} cross-referenced evidence points verified across all sources"

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
    if newest_reviews:
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
