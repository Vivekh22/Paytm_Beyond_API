import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

from cache import cached_call
from config import (
    YDC_API_KEY,
    YOUCOM_BASE_URL,
    YOUCOM_COUNTRY,
    YOUCOM_NEWS_FIELD,
    YOUCOM_WEB_FIELD,
)

logger = logging.getLogger(__name__)


def _youcom_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute live request against You.com Search API."""
    if not YDC_API_KEY:
        raise ValueError("YDC_API_KEY is not configured.")

    headers = {"X-API-Key": YDC_API_KEY}
    resp = requests.get(YOUCOM_BASE_URL, headers=headers, params=params, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def you_search(
    query: str, count: int = 10, tracker: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Search You.com for web and news results.
    Returns normalized list:
      [{title, url, snippet, page_age, kind: "web" | "news"}]
    """
    if not query:
        return [], "Empty query for You.com search."

    if not YDC_API_KEY:
        return [], "YDC_API_KEY is not set. You.com search skipped."

    params = {
        "query": query,
        "count": count,
        "country": YOUCOM_COUNTRY,
    }

    data, was_cached, warn = cached_call(
        provider="youcom",
        engine="search",
        params=params,
        fetch_fn=lambda: _youcom_request(params),
        tracker=tracker,
    )

    if not data or not isinstance(data, dict):
        return [], warn or f"You.com returned no results for '{query}'"

    normalized: List[Dict[str, Any]] = []

    # Defensive parsing of You.com payload shape
    # Commonly results are under data['results']['web'] or data['web']['results'] or top-level 'hits'
    web_items = []
    news_items = []

    if "results" in data and isinstance(data["results"], dict):
        res_dict = data["results"]
        web_items = res_dict.get(YOUCOM_WEB_FIELD, [])
        news_items = res_dict.get(YOUCOM_NEWS_FIELD, [])
    elif YOUCOM_WEB_FIELD in data and isinstance(data[YOUCOM_WEB_FIELD], list):
        web_items = data[YOUCOM_WEB_FIELD]
        news_items = data.get(YOUCOM_NEWS_FIELD, [])
    elif "hits" in data and isinstance(data["hits"], list):
        web_items = data["hits"]
    else:
        logger.warning(
            "You.com response shape unrecognized. Root keys: %s", list(data.keys())
        )

    # Parse Web results
    if isinstance(web_items, list):
        for item in web_items:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            url = item.get("url") or item.get("link") or ""

            # snippets can be a list or a string description
            snippets_val = item.get("snippets")
            snippet = ""
            if isinstance(snippets_val, list) and snippets_val:
                snippet = str(snippets_val[0])
            else:
                snippet = item.get("description") or item.get("snippet") or ""

            page_age = item.get("page_age") or item.get("age") or ""

            if title or snippet:
                normalized.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet.strip(),
                        "page_age": page_age,
                        "kind": "web",
                    }
                )

    # Parse News results
    if isinstance(news_items, list):
        for item in news_items:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            url = item.get("url") or item.get("link") or ""
            snippet = item.get("description") or item.get("snippet") or ""
            page_age = item.get("age") or item.get("page_age") or ""

            if title or snippet:
                normalized.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet.strip(),
                        "page_age": page_age,
                        "kind": "news",
                    }
                )

    return normalized, warn
