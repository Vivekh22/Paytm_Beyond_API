import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

from cache import cached_call
from config import (
    APP_STORE_COUNTRY,
    EXTRACT_ENGINE,
    EXTRACT_URL_PARAM,
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
    keyword: str, tracker: Optional[Any] = None, anchor: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch Google Trends timeseries data for India over the past 12 months.
    Returns: (points: [{date, value}], warning)
    """
    if not keyword:
        return [], "No keyword provided for Google Trends."

    params = {
        "engine": "google_trends",
        "q": f"{keyword},{anchor}" if anchor else keyword,
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
        point: Dict[str, Any] = {"date": d, "value": val}
        if item.get("timestamp"):
            point["ts"] = item.get("timestamp")
        # With an anchor, SerpApi returns one value per comma-separated term, in order.
        if anchor and isinstance(values, list) and len(values) > 1 and isinstance(values[1], dict):
            try:
                point["anchor"] = int(values[1].get("extracted_value", values[1].get("value", 0)) or 0)
            except (ValueError, TypeError):
                point["anchor"] = 0
        points.append(point)

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
            "developer": it.get("author") or it.get("developer") or it.get("author_name") or "",
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


def google_search(
    query: str, tracker: Optional[Any] = None, engine_tag: str = "google_search"
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Google organic results (India). Returns: ([{title, snippet, link}], warning)"""
    if not query:
        return [], "Empty Google query."
    params = {"engine": "google", "q": query, "gl": SERPAPI_DEFAULT_GL, "hl": SERPAPI_DEFAULT_HL, "num": 10}
    data, _, warn = cached_call(provider="serpapi", engine=engine_tag, params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    for item in data.get("organic_results", []) or []:
        if isinstance(item, dict):
            out.append({"title": item.get("title") or "", "snippet": item.get("snippet") or "",
                        "link": item.get("link") or ""})
    # Local pack results often carry phone numbers too
    local = data.get("local_results")
    places = local.get("places", []) if isinstance(local, dict) else (local if isinstance(local, list) else [])
    for pl in places or []:
        if isinstance(pl, dict):
            out.append({"title": pl.get("title") or "", "snippet": f"{pl.get('title', '')} {pl.get('phone', '')} {pl.get('address', '')}",
                        "link": pl.get("links", {}).get("website", "") if isinstance(pl.get("links"), dict) else ""})
    return out, warn


def maps_search(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Google Maps local results (India). Returns: ([{title, phone, address, website, link}], warning)"""
    if not query:
        return [], "Empty Maps query."
    params = {"engine": "google_maps", "q": query, "type": "search", "hl": SERPAPI_DEFAULT_HL,
              "ll": "@20.5937,78.9629,5z"}
    data, _, warn = cached_call(provider="serpapi", engine="google_maps", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    results = data.get("local_results") or ([data["place_results"]] if isinstance(data.get("place_results"), dict) else [])
    for r in results or []:
        if not isinstance(r, dict):
            continue
        link = r.get("website") or ""
        if not link and r.get("place_id"):
            link = f"https://www.google.com/maps/place/?q=place_id:{r.get('place_id')}"
        out.append({"title": r.get("title") or "", "phone": r.get("phone") or "", "address": r.get("address") or "",
                    "website": r.get("website") or "", "link": link, "data_id": r.get("data_id") or "",
                    "place_id": r.get("place_id") or "", "rating": r.get("rating"), "reviews": r.get("reviews")})
    return out, warn


def jobs_search(
    query: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Google Jobs results (India). Returns: ([{title, company_name, via, description, apply_link, share_link}], warning)"""
    if not query:
        return [], "Empty Jobs query."
    params = {"engine": "google_jobs", "q": query, "gl": SERPAPI_DEFAULT_GL, "hl": SERPAPI_DEFAULT_HL,
              "location": "India"}
    data, _, warn = cached_call(provider="serpapi", engine="google_jobs", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    for j in data.get("jobs_results", []) or []:
        if not isinstance(j, dict):
            continue
        apply = j.get("apply_options") or []
        apply_link = apply[0].get("link", "") if apply and isinstance(apply[0], dict) else ""
        out.append({"title": j.get("title") or "", "company_name": j.get("company_name") or "",
                    "via": j.get("via") or "", "description": (j.get("description") or "")[:2000],
                    "apply_link": apply_link, "share_link": j.get("share_link") or ""})
    return out, warn


def trends_regions(
    keyword: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Interest by Indian state over 12 months. Returns: ([{name, value}], warning), highest first."""
    if not keyword:
        return [], "No keyword for Trends regions."
    params = {"engine": "google_trends", "q": keyword, "geo": SERPAPI_DEFAULT_GEO,
              "data_type": "GEO_MAP_0", "date": "today 12-m"}
    data, _, warn = cached_call(provider="serpapi", engine="google_trends_regions", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    rows = data.get("interest_by_region") or data.get("compared_breakdown_by_region") or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        val = r.get("extracted_value", r.get("value"))
        if isinstance(r.get("values"), list) and r["values"]:
            val = r["values"][0].get("extracted_value", r["values"][0].get("value"))
        try:
            val = int(val)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out.append({"name": r.get("location") or r.get("geo") or "", "value": val})
    out.sort(key=lambda x: x["value"], reverse=True)
    return out, warn


def maps_reviews(
    data_id: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Newest Google Maps reviews for a place. Returns: ([{user, rating, snippet, date, likes}], warning)"""
    if not data_id:
        return [], "No Maps data_id for reviews."
    params = {"engine": "google_maps_reviews", "data_id": data_id, "hl": SERPAPI_DEFAULT_HL, "sort_by": "newestFirst"}
    data, _, warn = cached_call(provider="serpapi", engine="google_maps_reviews", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    for r in data.get("reviews", []) or []:
        if not isinstance(r, dict):
            continue
        user = r.get("user") if isinstance(r.get("user"), dict) else {}
        try:
            rating = int(float(r.get("rating") or 0))
        except (TypeError, ValueError):
            rating = 0
        out.append({"user": user.get("name") or "Maps user", "rating": rating,
                    "snippet": r.get("snippet") or (r.get("extracted_snippet") or {}).get("original", "") if isinstance(r.get("extracted_snippet"), dict) else (r.get("snippet") or ""),
                    "date": r.get("iso_date") or r.get("date") or "", "likes": int(r.get("likes") or 0)})
    return out, warn


def appstore_search(
    term: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Apple App Store search. Returns: ([{title, product_id, rating, link}], warning)"""
    if not term:
        return [], "Empty App Store query."
    params = {"engine": "apple_app_store", "term": term, "country": APP_STORE_COUNTRY, "num": 5}
    data, _, warn = cached_call(provider="serpapi", engine="apple_app_store", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    for a in data.get("organic_results", []) or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        rating = a.get("rating")
        if isinstance(rating, list) and rating:
            rating = rating[0].get("rating") if isinstance(rating[0], dict) else None
        try:
            rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None
        out.append({"title": a.get("title") or "", "product_id": str(a.get("id")), "rating": rating,
                    "link": a.get("link") or ""})
    return out, warn


def appstore_reviews(
    product_id: str, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Most recent App Store reviews. Returns: ([{user, rating, snippet, date}], warning)"""
    if not product_id:
        return [], "No App Store product id."
    params = {"engine": "apple_reviews", "product_id": product_id, "country": APP_STORE_COUNTRY, "sort": "mostrecent"}
    data, _, warn = cached_call(provider="serpapi", engine="apple_reviews", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return [], warn
    out = []
    for r in data.get("reviews", []) or []:
        if not isinstance(r, dict):
            continue
        author = r.get("author") if isinstance(r.get("author"), dict) else {}
        try:
            rating = int(r.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0
        text = " ".join(x for x in [r.get("title") or "", r.get("text") or ""] if x)
        out.append({"user": author.get("name") or "App Store user", "rating": rating, "snippet": text,
                    "date": r.get("review_date") or r.get("date") or ""})
    return out, warn


def extract_page(
    url: str, tracker: Optional[Any] = None
) -> Tuple[str, Optional[str]]:
    """Read a web page's text through SerpApi Extract. Returns: (text, warning). Param names come from config."""
    if not url:
        return "", "No URL to extract."
    params = {"engine": EXTRACT_ENGINE, EXTRACT_URL_PARAM: url}
    data, _, warn = cached_call(provider="serpapi", engine="extract", params=params,
                                fetch_fn=lambda: _serp_request(params), tracker=tracker)
    if not data or not isinstance(data, dict):
        return "", warn
    for key in ("markdown", "content", "text", "html"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val[:20000], warn
    pages = data.get("pages") or data.get("results")
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        for key in ("markdown", "content", "text"):
            if isinstance(pages[0].get(key), str):
                return pages[0][key][:20000], warn
    return "", warn or "Extract returned no readable text (check EXTRACT_* settings)."
