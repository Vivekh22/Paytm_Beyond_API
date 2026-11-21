import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

from cache import cached_call
from config import (
    SERPAPI_BASE_URL,
    SERPAPI_DEFAULT_GEO,
    SERPAPI_DEFAULT_GL,
    SERPAPI_DEFAULT_HL,
    SERPAPI_KEY,
)

logger = logging.getLogger(__name__)


def _serp_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute live request against SerpApi."""
    request_params = dict(params)
    request_params["api_key"] = SERPAPI_KEY
    resp = requests.get(SERPAPI_BASE_URL, params=request_params, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def trends_timeseries(
    keyword: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch Google Trends timeseries data for India over the past 12 months.
    Returns: (points: [{date, value}], warning)
    """
    if not keyword:
        return [], "No keyword provided for Google Trends."

    params = {
        "engine": "google_trends",
        "q": keyword,
        "geo": SERPAPI_DEFAULT_GEO,
        "data_type": "TIMESERIES",
        "date": "today 12-m",
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_trends",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn or f"Google Trends returned no data for '{keyword}'"

    # Defensive parsing of timeline data
    points: List[Dict[str, Any]] = []
    interest_over_time = data.get("interest_over_time", {})
    timeline = interest_over_time.get("timeline_data", [])

    for item in timeline:
        d = item.get("date") or item.get("time") or ""
        values = item.get("values", [])
        val = 0
        if values and isinstance(values, list):
            first = values[0]
            if isinstance(first, dict):
                val = int(first.get("extracted_value", first.get("value", 0)) or 0)
            elif isinstance(first, (int, float, str)):
                try:
                    val = int(first)
                except ValueError:
                    val = 0
        points.append({"date": d, "value": val})

    return points, warn


def trends_related(
    keyword: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch Google Trends rising and top related queries for India.
    Returns: (queries: [{query, value}], warning)
    """
    if not keyword:
        return [], "No keyword provided for Trends related queries."

    params = {
        "engine": "google_trends",
        "data_type": "RELATED_QUERIES",
        "q": keyword,
        "geo": SERPAPI_DEFAULT_GEO,
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_trends_related",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn

    results: List[Dict[str, Any]] = []
    related = data.get("related_queries", {})
    rising = related.get("rising", [])
    for item in rising:
        q = item.get("query")
        v = item.get("value")
        if q:
            results.append({"query": q, "value": v})

    return results, warn


def play_search(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Search Google Play Store apps in India.
    Returns: (apps: [{title, product_id, rating, installs, thumbnail, link}], warning)
    """
    if not query:
        return [], "Empty search query for Play Store."

    params = {
        "engine": "google_play",
        "store": "apps",
        "q": query,
        "gl": SERPAPI_DEFAULT_GL,
        "hl": SERPAPI_DEFAULT_HL,
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_play",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn

    apps: List[Dict[str, Any]] = []
    seen_ids = set()

    # Defensive parsing across multiple potential structures
    def extract_app_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pid = it.get("product_id") or it.get("app_id")
        title = it.get("title")
        if not pid or not title:
            return None
        if pid in seen_ids:
            return None
        seen_ids.add(pid)

        rating_val = it.get("rating", 0.0)
        try:
            rating_flt = float(rating_val) if rating_val is not None else 0.0
        except (ValueError, TypeError):
            rating_flt = 0.0

        installs = it.get("downloads") or it.get("installs") or "N/A"
        thumbnail = it.get("thumbnail") or it.get("icon") or ""
        link = it.get("link") or f"https://play.google.com/store/apps/details?id={pid}"

        return {
            "title": title,
            "product_id": pid,
            "rating": rating_flt,
            "installs": installs,
            "thumbnail": thumbnail,
            "link": link,
        }

    # 1. app_highlight
    highlight = data.get("app_highlight")
    if isinstance(highlight, dict):
        app = extract_app_item(highlight)
        if app:
            apps.append(app)

    # 2. organic_results (list of app cards or groups containing items[])
    organic = data.get("organic_results", [])
    if isinstance(organic, list):
        for entry in organic:
            if not isinstance(entry, dict):
                continue
            if "items" in entry and isinstance(entry["items"], list):
                for sub in entry["items"]:
                    if isinstance(sub, dict):
                        app = extract_app_item(sub)
                        if app:
                            apps.append(app)
            else:
                app = extract_app_item(entry)
                if app:
                    apps.append(app)

    return apps, warn


def play_reviews(
    product_id: str,
    rating: Optional[int] = None,
    sort_by: Optional[int] = None,
    num: int = 100,
    tracker: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    """
    Fetch reviews for a specific Google Play app.
    Returns: (reviews: [{id, title, user, rating, snippet, date, likes}], product_meta: {rating, reviews}, warning)
    """
    if not product_id:
        return [], {"rating": 0.0, "reviews": 0}, "Empty product_id for Play Reviews."

    params = {
        "engine": "google_play_product",
        "store": "apps",
        "product_id": product_id,
        "all_reviews": "true",
        "gl": SERPAPI_DEFAULT_GL,
        "hl": SERPAPI_DEFAULT_HL,
        "num": num,
    }
    if rating is not None:
        params["rating"] = str(rating)
    if sort_by is not None:
        params["sort_by"] = str(sort_by)

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_play_product",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    product_meta = {"rating": 0.0, "reviews": 0}
    if not data or not isinstance(data, dict):
        return [], product_meta, warn

    product_info = data.get("product_info") or {}
    if isinstance(product_info, dict):
        try:
            r = float(product_info.get("rating") or data.get("rating", 0.0) or 0.0)
            product_meta["rating"] = r
        except (ValueError, TypeError):
            product_meta["rating"] = 0.0
        try:
            rev_cnt = int(product_info.get("reviews") or data.get("reviews", 0) or 0)
            product_meta["reviews"] = rev_cnt
        except (ValueError, TypeError):
            product_meta["reviews"] = 0

    raw_reviews = data.get("reviews", [])
    reviews: List[Dict[str, Any]] = []

    if isinstance(raw_reviews, list):
        for idx, rev in enumerate(raw_reviews):
            if not isinstance(rev, dict):
                continue
            user_data = rev.get("user")
            author = "User"
            if isinstance(user_data, dict):
                author = user_data.get("name") or "User"
            elif isinstance(user_data, str):
                author = user_data

            snippet = rev.get("snippet") or rev.get("content") or rev.get("body") or ""
            r_val = rev.get("rating", rating or 1)
            try:
                r_num = int(r_val)
            except (ValueError, TypeError):
                r_num = rating or 1

            likes = 0
            try:
                likes = int(rev.get("likes", 0) or 0)
            except (ValueError, TypeError):
                likes = 0

            reviews.append(
                {
                    "id": rev.get("id") or f"{product_id}_{idx}",
                    "title": rev.get("title") or author,
                    "user": author,
                    "rating": r_num,
                    "snippet": snippet.strip(),
                    "date": rev.get("date") or "",
                    "likes": likes,
                }
            )

    return reviews, product_meta, warn


def news(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Search Google News for India.
    Returns: (news: [{title, source, date, link, snippet}], warning)
    """
    if not query:
        return [], "Empty search query for Google News."

    params = {
        "engine": "google_news",
        "q": query,
        "gl": SERPAPI_DEFAULT_GL,
        "hl": SERPAPI_DEFAULT_HL,
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_news",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn

    raw_news = data.get("news_results", [])
    news_list: List[Dict[str, Any]] = []

    if isinstance(raw_news, list):
        for item in raw_news:
            if not isinstance(item, dict):
                continue
            src_val = item.get("source")
            src_name = "News"
            if isinstance(src_val, dict):
                src_name = src_val.get("name") or "News"
            elif isinstance(src_val, str):
                src_name = src_val

            news_list.append(
                {
                    "title": item.get("title") or "",
                    "source": src_name,
                    "date": item.get("date") or "",
                    "link": item.get("link") or "",
                    "snippet": item.get("snippet") or item.get("title") or "",
                }
            )

    return news_list, warn


def reddit(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Search Reddit discussions via Google Organic Search for India.
    Returns: (reddit_posts: [{title, snippet, link}], warning)
    """
    if not query:
        return [], "Empty search query for Reddit."

    params = {
        "engine": "google",
        "q": f"{query} site:reddit.com",
        "gl": SERPAPI_DEFAULT_GL,
        "num": 10,
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_reddit",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn

    organic = data.get("organic_results", [])
    reddit_list: List[Dict[str, Any]] = []

    if isinstance(organic, list):
        for item in organic:
            if not isinstance(item, dict):
                continue
            reddit_list.append(
                {
                    "title": item.get("title") or "",
                    "snippet": item.get("snippet") or "",
                    "link": item.get("link") or "",
                }
            )

    return reddit_list, warn


def autocomplete(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[str], Optional[str]]:
    """
    Fetch Google autocomplete suggestions.
    Returns: (suggestions: [str], warning)
    """
    if not query:
        return [], "Empty search query for autocomplete."

    params = {
        "engine": "google_autocomplete",
        "q": query,
        "gl": SERPAPI_DEFAULT_GL,
        "hl": SERPAPI_DEFAULT_HL,
    }

    data, was_cached, warn = cached_call(
        provider="serpapi",
        engine="google_autocomplete",
        params=params,
        fetch_fn=lambda: _serp_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn

    suggestions_raw = data.get("suggestions", [])
    results: List[str] = []
    if isinstance(suggestions_raw, list):
        for s in suggestions_raw:
            if isinstance(s, dict) and "value" in s:
                results.append(str(s["value"]))
            elif isinstance(s, str):
                results.append(s)

    return results, warn
