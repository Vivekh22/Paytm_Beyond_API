from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional

from config import ENABLE_APP_STORE, SERPAPI_SCAN_BUDGET, TRENDS_ANCHOR
from evidence import EvidenceCollector
import llm as _llm
from llm import (
    classify_news,
    cluster_evidence,
    extract_keywords,
    generate_opportunities,
    post_validate_and_enrich_clusters,
    post_validate_and_enrich_opportunities,
)
from timeline import build_timeline
from scoring import (
    compute_discovery_verdict,
    compute_trajectory,
    compute_trend_metrics,
    compute_viability_score,
)
from serp_client import (
    news as serp_news,
    play_reviews,
    play_search,
    reddit as serp_reddit,
    trends_timeseries,
    trends_regions,
    maps_search,
    maps_reviews,
    appstore_search,
    appstore_reviews,
)
from youcom_client import you_search

logger = logging.getLogger(__name__)


class CreditTracker:
    """Thread-safe tracker for API consumption across SerpApi and You.com."""

    def __init__(self):
        self._lock = threading.Lock()
        self.serpapi_live = 0
        self.serpapi_cached = 0
        self.youcom_live = 0
        self.youcom_cached = 0

    def record(self, provider: str, cached: bool) -> None:
        with self._lock:
            if provider == "serpapi":
                if cached:
                    self.serpapi_cached += 1
                else:
                    self.serpapi_live += 1
            elif provider == "youcom":
                if cached:
                    self.youcom_cached += 1
                else:
                    self.youcom_live += 1

    def to_dict(self) -> Dict[str, int]:
        with self._lock:
            return {
                "serpapi_live": self.serpapi_live,
                "serpapi_cached": self.serpapi_cached,
                "youcom_live": self.youcom_live,
                "youcom_cached": self.youcom_cached,
            }


def _emit(callback: Optional[Callable[[str, str, int], None]], step: str, message: str, pct: int):
    if callback:
        try:
            callback(step, message, pct)
        except Exception:
            pass


def mode1_validate(
    query: str, progress_callback: Optional[Callable[[str, str, int], None]] = None
) -> Dict[str, Any]:
    """
    Mode 1: Startup Idea Validation Pipeline.
    Evaluates viability against search demand, competitor ratings, and customer pain points.
    """
    scan_id = uuid.uuid4().hex[:8]
    tracker = CreditTracker()
    warnings: List[str] = []

    _emit(progress_callback, "extract_keywords", f"Analyzing concept: '{query}'", 10)
    keywords = extract_keywords(query)
    broad = keywords.get("broad", query)
    specific_list = keywords.get("specific", [query])
    specific = specific_list[0] if specific_list else query
    category = keywords.get("category", "General")

    _emit(progress_callback, "parallel_search", "Querying Trends, Play Store, News, Reddit & You.com", 25)

    trend_points: List[Dict[str, Any]] = []
    play_apps: List[Dict[str, Any]] = []
    news_items: List[Dict[str, Any]] = []
    reddit_items: List[Dict[str, Any]] = []
    you_web_1: List[Dict[str, Any]] = []
    you_web_2: List[Dict[str, Any]] = []

    def fetch_trends(kw):
        pts, warn = trends_timeseries(kw, tracker=tracker, anchor=TRENDS_ANCHOR)
        return pts, warn

    def fetch_play(q):
        apps, warn = play_search(q, tracker=tracker)
        return apps, warn

    def fetch_news(q):
        nws, warn = serp_news(q, tracker=tracker)
        return nws, warn

    def fetch_reddit(q):
        red, warn = serp_reddit(q, tracker=tracker)
        return red, warn

    def fetch_you(q):
        res, warn = you_search(q, count=10, tracker=tracker)
        return res, warn

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_trends = executor.submit(fetch_trends, broad)
        future_play = executor.submit(fetch_play, specific)
        future_news = executor.submit(fetch_news, broad)
        future_reddit = executor.submit(fetch_reddit, specific)
        future_you1 = executor.submit(fetch_you, f"{broad} startups India competitors funding")
        future_you2 = executor.submit(fetch_you, f"{specific} problems complaints")
        future_regions = executor.submit(trends_regions, broad, tracker)

        trend_points, t_warn = future_trends.result()
        play_apps, p_warn = future_play.result()
        news_items, n_warn = future_news.result()
        reddit_items, r_warn = future_reddit.result()
        you_web_1, y1_warn = future_you1.result()
        you_web_2, y2_warn = future_you2.result()
        regions, rg_warn = future_regions.result()

    for w in [t_warn, p_warn, n_warn, r_warn, y1_warn, y2_warn, rg_warn]:
        if w and w not in warnings:
            warnings.append(w)

    # Trends fallback if empty
    if not trend_points:
        fallback_kw = broad.split()[0] if " " in broad else category
        # keep 3 calls in reserve for the competitor review fetches
        if tracker.to_dict()["serpapi_live"] + 1 + 3 > SERPAPI_SCAN_BUDGET:
            warnings.append(f"Skipped Trends fallback: per-scan SerpApi budget ({SERPAPI_SCAN_BUDGET}) reached")
        elif fallback_kw and fallback_kw.lower() != broad.lower():
            fb_pts, fb_warn = trends_timeseries(fallback_kw, tracker=tracker, anchor=TRENDS_ANCHOR)
            if fb_pts:
                trend_points = fb_pts
                warnings.append(f"Google Trends returned no data for '{broad}'; used '{fallback_kw}'")
                broad = fallback_kw

    # Split the anchor series out of the keyword points (kept only for scoring)
    anchor_values = [p.pop("anchor") for p in trend_points if isinstance(p, dict) and "anchor" in p]

    # Top competitors
    top_apps = play_apps[:3]
    total_reviews_scanned = 0
    collector = EvidenceCollector(max_items=150)

    competitor_list: List[Dict[str, Any]] = []

    if top_apps:
        _emit(progress_callback, "play_reviews", f"Fetching 1★ reviews for {len(top_apps)} competitors", 50)

        def fetch_app_reviews(app):
            pid = app["product_id"]
            revs, meta, warn = play_reviews(pid, rating=1, num=100, tracker=tracker)
            return app, revs, meta, warn

        with ThreadPoolExecutor(max_workers=8) as executor:
            review_futures = [executor.submit(fetch_app_reviews, app) for app in top_apps]
            for fut in review_futures:
                app, revs, meta, warn = fut.result()
                if warn and warn not in warnings:
                    warnings.append(warn)
                rev_count = len(revs)
                total_reviews_scanned += rev_count
                collector.add_play_reviews(revs, app_name=app["title"], app_url=app["link"])
                competitor_list.append(
                    {
                        "name": app["title"],
                        "product_id": app["product_id"],
                        "rating": app["rating"],
                        "installs": app["installs"],
                        "icon": app["thumbnail"],
                        "url": app["link"],
                        "source": "play_store",
                        "reviews_scanned": rev_count,
                    }
                )
    else:
        warnings.append("No matching Play Store apps; using Google Maps places and their reviews.")
        places, m_warn = maps_search(specific, tracker=tracker)
        if m_warn and m_warn not in warnings:
            warnings.append(m_warn)
        for place in [pl for pl in places if pl.get("data_id")][:2]:
            revs, mr_warn = maps_reviews(place["data_id"], tracker=tracker)
            if mr_warn and mr_warn not in warnings:
                warnings.append(mr_warn)
            total_reviews_scanned += len(revs)
            collector.add_store_reviews(revs, source="google_maps", entity=place["title"], url=place["link"])
            competitor_list.append(
                {
                    "name": place["title"],
                    "product_id": place.get("place_id", ""),
                    "rating": place.get("rating"),
                    "installs": f"{place.get('reviews')} Maps reviews" if place.get("reviews") else "N/A",
                    "icon": "",
                    "url": place["link"],
                    "source": "google_maps",
                    "reviews_scanned": len(revs),
                }
            )
    if not competitor_list:
        for item in you_web_1[:3]:
            competitor_list.append(
                {
                    "name": item.get("title", "Web Competitor"),
                    "product_id": "",
                    "rating": None,
                    "installs": "N/A",
                    "icon": "",
                    "url": item.get("url", ""),
                    "source": "you_web",
                    "reviews_scanned": 0,
                }
            )

    # Ingest web, news, and reddit
    collector.add_reddit_posts(reddit_items, entity="Reddit Discussion")
    collector.add_news_items(news_items, entity="Google News")
    collector.add_youcom_results(you_web_1 + you_web_2, entity="You.com Search")

    evidence_map, evidence_list = collector.build()

    _emit(progress_callback, "clustering", f"Clustering {len(evidence_list)} evidence items into pain points", 70)
    raw_clusters = cluster_evidence(evidence_list, context=query, group="pain")
    clusters = post_validate_and_enrich_clusters(
        raw_clusters, evidence_map, total_reviews_scanned=total_reviews_scanned, group="pain"
    )

    _emit(progress_callback, "opportunities", "Generating targeted challenger opportunities", 85)
    raw_opps = generate_opportunities(clusters, context=query)
    opportunities = post_validate_and_enrich_opportunities(raw_opps, clusters, evidence_map)

    _emit(progress_callback, "scoring", "Computing deterministic Viability Score", 95)
    verdict = compute_viability_score(
        trend_points=trend_points,
        clusters=clusters,
        competitors=competitor_list,
        evidence_map=evidence_map,
        total_reviews_scanned=total_reviews_scanned,
        anchor_values=anchor_values,
        anchor_name=TRENDS_ANCHOR,
    )

    mean_val, direction, change_pct, _ = compute_trend_metrics(trend_points)
    for comp in competitor_list:
        if comp.get("source") == "play_store":
            comp["investigate"] = {"mode": 2, "query": comp["name"]}

    report = {
        "scan_id": scan_id,
        "mode": 1,
        "regions": regions[:10],
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": {
            "broad": broad,
            "specific": specific_list,
            "category": category,
        },
        "credits": tracker.to_dict(),
        "verdict": verdict,
        "trend": {
            "keyword": broad,
            "geo": "IN",
            "points": trend_points,
            "change_pct": change_pct,
            "direction": direction,
        },
        "competitors": competitor_list,
        "clusters": clusters,
        "opportunities": opportunities,
        "news": [],
        "timeline": None,
        "findings": [],
        "evidence": evidence_map,
        "warnings": warnings,
    }

    if not report["trend"]["points"]:
        report["trend"] = None  # contract: null when Trends has no data
    if not report["clusters"] and _llm.LAST_GEMINI_ERROR:
        report["warnings"].append(f"Gemini unavailable, so no themes were generated: {_llm.LAST_GEMINI_ERROR}")

    _emit(progress_callback, "done", "Market intelligence report generated", 100)
    return report


def mode2_investigate(
    query: str, progress_callback: Optional[Callable[[str, str, int], None]] = None
) -> Dict[str, Any]:
    """
    Mode 2: Competitor Deep Dive & Trajectory Analysis.
    Investigates a specific company/app for strengths, weaknesses, rating drift, and challenger plays.
    """
    scan_id = uuid.uuid4().hex[:8]
    tracker = CreditTracker()
    warnings: List[str] = []

    _emit(progress_callback, "play_search", f"Locating primary app record for '{query}'", 15)
    apps, p_warn = play_search(query, tracker=tracker)
    if p_warn and p_warn not in warnings:
        warnings.append(p_warn)

    best_app = apps[0] if apps else None
    product_id = best_app["product_id"] if best_app else ""
    app_name = best_app["title"] if best_app else query
    app_url = best_app["link"] if best_app else ""
    all_time_rating = best_app["rating"] if best_app else None

    _emit(progress_callback, "parallel_search", f"Fetching reviews, media, news & trends for {app_name}", 40)

    revs_1star: List[Dict[str, Any]] = []
    revs_5star: List[Dict[str, Any]] = []
    revs_newest: List[Dict[str, Any]] = []
    news_items: List[Dict[str, Any]] = []
    trend_points: List[Dict[str, Any]] = []
    reddit_items: List[Dict[str, Any]] = []
    you_items_1: List[Dict[str, Any]] = []
    you_items_2: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_r1 = executor.submit(lambda: play_reviews(product_id, rating=1, num=100, tracker=tracker) if product_id else ([], {}, None))
        f_r5 = executor.submit(lambda: play_reviews(product_id, rating=5, num=100, tracker=tracker) if product_id else ([], {}, None))
        f_rn = executor.submit(lambda: play_reviews(product_id, sort_by=2, num=100, tracker=tracker) if product_id else ([], {}, None))
        f_news = executor.submit(lambda: serp_news(query, tracker=tracker))
        f_trends = executor.submit(lambda: trends_timeseries(query, tracker=tracker))
        f_reddit = executor.submit(lambda: serp_reddit(query, tracker=tracker))
        f_you1 = executor.submit(lambda: you_search(f"{query} funding layoffs revenue 2026", count=10, tracker=tracker))
        f_you2 = executor.submit(lambda: you_search(f"{query} customer complaints", count=10, tracker=tracker))

        revs_1star, _, w1 = f_r1.result()
        revs_5star, _, w5 = f_r5.result()
        revs_newest, meta_newest, wn = f_rn.result()
        news_items, w_news = f_news.result()
        trend_points, w_trends = f_trends.result()
        reddit_items, w_reddit = f_reddit.result()
        you_items_1, w_y1 = f_you1.result()
        you_items_2, w_y2 = f_you2.result()

    for w in [w1, w5, wn, w_news, w_trends, w_reddit, w_y1, w_y2]:
        if w and w not in warnings:
            warnings.append(w)

    ios_reviews: List[Dict[str, Any]] = []
    ios_app = None
    if ENABLE_APP_STORE:
        ios_apps, w_ios = appstore_search(query, tracker=tracker)
        ios_app = ios_apps[0] if ios_apps else None
        if ios_app:
            ios_reviews, w_ios2 = appstore_reviews(ios_app["product_id"], tracker=tracker)
            w_ios = w_ios or w_ios2
        if w_ios and w_ios not in warnings:
            warnings.append(w_ios)

    total_scanned = len(revs_1star) + len(revs_5star) + len(revs_newest) + len(ios_reviews)

    collector = EvidenceCollector(max_items=150)
    collector.add_play_reviews(revs_1star, app_name=app_name, app_url=app_url)
    collector.add_play_reviews(revs_5star, app_name=app_name, app_url=app_url)
    collector.add_play_reviews(revs_newest, app_name=app_name, app_url=app_url)
    if ios_app:
        collector.add_store_reviews(ios_reviews, source="app_store", entity=f"{ios_app['title']} (iOS)", url=ios_app["link"])
    collector.add_reddit_posts(reddit_items, entity=f"{app_name} Reddit")
    collector.add_news_items(news_items, entity=f"{app_name} News")
    collector.add_youcom_results(you_items_1 + you_items_2, entity=f"{app_name} Web")

    evidence_map, evidence_list = collector.build()

    _emit(progress_callback, "clustering", "Synthesizing strengths (5★) and weaknesses (1★)", 65)

    # Separate items by rating for clustering
    items_1star = [it for it in evidence_list if it.get("rating") == 1]
    items_5star = [it for it in evidence_list if it.get("rating") == 5]

    with ThreadPoolExecutor(max_workers=4) as executor:
        f_cl_pain = executor.submit(lambda: cluster_evidence(items_1star, context=f"{app_name} critical reviews", group="pain", max_clusters=3))
        f_cl_strength = executor.submit(lambda: cluster_evidence(items_5star, context=f"{app_name} positive reviews", group="strength", max_clusters=3))

        raw_pain = f_cl_pain.result()
        raw_strength = f_cl_strength.result()

    clusters_pain = post_validate_and_enrich_clusters(
        raw_pain, evidence_map, total_reviews_scanned=max(len(revs_1star), 1), group="pain"
    )
    clusters_strength = post_validate_and_enrich_clusters(
        raw_strength, evidence_map, total_reviews_scanned=max(len(revs_5star), 1), group="strength"
    )
    # Combine clusters
    for idx, c in enumerate(clusters_pain + clusters_strength, start=1):
        c["id"] = f"cl_{idx}"
    combined_clusters = clusters_pain + clusters_strength

    _emit(progress_callback, "news_classification", "Classifying media and news sentiment", 75)
    news_eids = [
        {"evidence_id": eid, "text": it["text"]}
        for eid, it in evidence_map.items()
        if it["source"] in ("google_news", "you_news")
    ]
    news_classified = [n for n in classify_news(news_eids) if n.get("evidence_id") in evidence_map]

    _emit(progress_callback, "trajectory", "Calculating trajectory index & rating drift", 85)
    verdict = compute_trajectory(
        trend_points=trend_points,
        all_time_rating=all_time_rating,
        newest_reviews=revs_newest,
        news_classifications=news_classified,
        evidence_map=evidence_map,
    )

    _emit(progress_callback, "opportunities", "Formulating challenger attack vectors", 92)
    raw_opps = generate_opportunities(clusters_pain, context=f"Challenger to {app_name}")
    opportunities = post_validate_and_enrich_opportunities(raw_opps, combined_clusters, evidence_map)

    mean_val, direction, change_pct, _ = compute_trend_metrics(trend_points)

    competitor_entry = {
        "name": app_name,
        "product_id": product_id,
        "rating": all_time_rating,
        "installs": best_app["installs"] if best_app else "N/A",
        "icon": best_app["thumbnail"] if best_app else "",
        "url": app_url,
        "source": "play_store",
        "reviews_scanned": total_scanned,
    }

    report = {
        "scan_id": scan_id,
        "mode": 2,
        "regions": [],
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": {
            "broad": query,
            "specific": [f"{query} reviews", f"{query} complaints"],
            "category": "Competitor Investigation",
        },
        "credits": tracker.to_dict(),
        "verdict": verdict,
        "trend": {
            "keyword": query,
            "geo": "IN",
            "points": trend_points,
            "change_pct": change_pct,
            "direction": direction,
        },
        "competitors": [competitor_entry],
        "clusters": combined_clusters,
        "opportunities": opportunities,
        "news": news_classified,
        "timeline": build_timeline(trend_points, revs_newest, revs_1star, evidence_map, news_classified),
        "findings": [],
        "evidence": evidence_map,
        "warnings": warnings,
    }

    if not report["trend"]["points"]:
        report["trend"] = None  # contract: null when Trends has no data
    if not report["clusters"] and _llm.LAST_GEMINI_ERROR:
        report["warnings"].append(f"Gemini unavailable, so no themes were generated: {_llm.LAST_GEMINI_ERROR}")

    _emit(progress_callback, "done", "Competitor intelligence report generated", 100)
    return report


def mode3_discover(
    query: str, progress_callback: Optional[Callable[[str, str, int], None]] = None
) -> Dict[str, Any]:
    """
    Mode 3: Category Discovery Pipeline.
    Uncovers systemic cross-app gaps and opportunities across top competitors.
    """
    scan_id = uuid.uuid4().hex[:8]
    tracker = CreditTracker()
    warnings: List[str] = []

    _emit(progress_callback, "play_search", f"Discovering top 5 apps in '{query}'", 20)
    apps, p_warn = play_search(query, tracker=tracker)
    if p_warn and p_warn not in warnings:
        warnings.append(p_warn)

    top_5_apps = apps[:5]
    competitor_list: List[Dict[str, Any]] = []
    collector = EvidenceCollector(max_items=150)
    total_scanned = 0

    _emit(progress_callback, "parallel_search", "Ingesting 1★ reviews across top 5 players + Reddit & Trends", 45)

    def fetch_revs(app):
        pid = app["product_id"]
        revs, _, warn = play_reviews(pid, rating=1, num=100, tracker=tracker)
        return app, revs, warn

    with ThreadPoolExecutor(max_workers=8) as executor:
        rev_futures = [executor.submit(fetch_revs, app) for app in top_5_apps]
        f_reddit = executor.submit(lambda: serp_reddit(query, tracker=tracker))
        f_trends = executor.submit(lambda: trends_timeseries(query, tracker=tracker))
        f_you1 = executor.submit(lambda: you_search(f"{query} India users biggest problems", count=10, tracker=tracker))
        f_you2 = executor.submit(lambda: you_search(f"{query} market report India 2026", count=10, tracker=tracker))

        for fut in rev_futures:
            app, revs, warn = fut.result()
            if warn and warn not in warnings:
                warnings.append(warn)
            total_scanned += len(revs)
            collector.add_play_reviews(revs, app_name=app["title"], app_url=app["link"])
            competitor_list.append(
                {
                    "name": app["title"],
                    "product_id": app["product_id"],
                    "rating": app["rating"],
                    "installs": app["installs"],
                    "icon": app["thumbnail"],
                    "url": app["link"],
                    "source": "play_store",
                    "reviews_scanned": len(revs),
                }
            )

        reddit_items, w_red = f_reddit.result()
        trend_points, w_trend = f_trends.result()
        you_items_1, w_y1 = f_you1.result()
        you_items_2, w_y2 = f_you2.result()

    for w in [w_red, w_trend, w_y1, w_y2]:
        if w and w not in warnings:
            warnings.append(w)

    collector.add_reddit_posts(reddit_items, entity=f"{query} Reddit")
    collector.add_youcom_results(you_items_1 + you_items_2, entity=f"{query} Market Report")

    evidence_map, evidence_list = collector.build()

    _emit(progress_callback, "clustering", f"Clustering category pain points across {len(competitor_list)} apps", 70)
    raw_clusters = cluster_evidence(evidence_list, context=f"{query} category review complaints", group="pain", max_clusters=6)
    clusters = post_validate_and_enrich_clusters(
        raw_clusters, evidence_map, total_reviews_scanned=total_scanned, group="pain"
    )

    # Rank clusters by how many DIFFERENT apps they appear in (cross-competitor pain is the real gap)
    clusters.sort(
        key=lambda c: (len(c.get("apps_affected", [])), c.get("frequency", {}).get("count", 0)),
        reverse=True,
    )
    # Re-index cluster IDs after ranking
    for idx, c in enumerate(clusters, start=1):
        c["id"] = f"cl_{idx}"

    # Underserved need = the same complaint in 2+ apps while category demand is rising or flat
    _m, cat_direction, cat_change, _b = compute_trend_metrics(trend_points)
    for c in clusters:
        n_apps = len(c.get("apps_affected", []))
        if not trend_points:
            c["underserved"] = None
            c["underserved_reason"] = f"Seen in {n_apps} app(s); no Google Trends data to check demand"
        elif n_apps >= 2 and cat_direction in ("rising", "flat"):
            c["underserved"] = True
            c["underserved_reason"] = (f"Seen in {n_apps} of {len(competitor_list)} apps while '{query}' demand is "
                                       f"{cat_direction} ({cat_change:+.1f}%)")
        else:
            c["underserved"] = False
            c["underserved_reason"] = (f"Seen in {n_apps} app(s); demand {cat_direction} ({cat_change:+.1f}%)")

    _emit(progress_callback, "opportunities", "Synthesizing 3 category-wide whitespace concepts", 85)
    raw_opps = generate_opportunities(clusters[:3], context=f"{query} category whitespace")
    opportunities = post_validate_and_enrich_opportunities(raw_opps, clusters, evidence_map)[:3]

    _emit(progress_callback, "scoring", "Compiling Category Discovery verdict", 95)
    verdict = compute_discovery_verdict(clusters, competitor_list, evidence_map)

    mean_val, direction, change_pct, _ = compute_trend_metrics(trend_points)

    report = {
        "scan_id": scan_id,
        "mode": 3,
        "regions": [],
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": {
            "broad": query,
            "specific": [f"{query} apps", f"{query} market India"],
            "category": query,
        },
        "credits": tracker.to_dict(),
        "verdict": verdict,
        "trend": {
            "keyword": query,
            "geo": "IN",
            "points": trend_points,
            "change_pct": change_pct,
            "direction": direction,
        },
        "competitors": competitor_list,
        "clusters": clusters,
        "opportunities": opportunities,
        "news": [],
        "timeline": None,
        "findings": [],
        "evidence": evidence_map,
        "warnings": warnings,
    }

    if not report["trend"]["points"]:
        report["trend"] = None  # contract: null when Trends has no data
    if not report["clusters"] and _llm.LAST_GEMINI_ERROR:
        report["warnings"].append(f"Gemini unavailable, so no themes were generated: {_llm.LAST_GEMINI_ERROR}")

    _emit(progress_callback, "done", "Category discovery report complete", 100)
    return report
