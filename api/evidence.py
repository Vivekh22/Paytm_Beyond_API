import re
from typing import Any, Dict, List, Optional, Tuple


class EvidenceCollector:
    """
    Normalizes multi-source raw records into standardized, deduplicated Evidence items.
    Enforces stable IDs ('ev_0001', ...), 20-char minimum, 400-char clipping,
    and a maximum capacity of ~150 highest-signal items.
    """

    def __init__(self, max_items: int = 150):
        self.max_items = max_items
        self._raw_candidates: List[Dict[str, Any]] = []
        self._seen_signatures = set()

    def _normalize_text(self, text: str) -> str:
        """Clean whitespace and strip to max 400 characters."""
        collapsed = re.sub(r"\s+", " ", text or "").strip()
        return collapsed[:400]

    def _make_signature(self, text: str) -> str:
        """Create signature for deduplication based on alphanumeric prefix."""
        alnum = re.sub(r"[^a-zA-Z0-9]", "", text.lower())
        return alnum[:120]

    def add_play_reviews(
        self,
        reviews: List[Dict[str, Any]],
        app_name: str,
        app_url: str,
    ) -> None:
        """Ingest Google Play Store reviews."""
        # Sort reviews by likes descending to ensure high-engagement reviews take priority
        sorted_revs = sorted(reviews, key=lambda r: int(r.get("likes", 0) or 0), reverse=True)
        for r in sorted_revs:
            raw_text = r.get("snippet", "")
            norm_text = self._normalize_text(raw_text)
            if len(norm_text) < 20:
                continue

            sig = self._make_signature(norm_text)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)

            self._raw_candidates.append(
                {
                    "source": "play_store",
                    "text": norm_text,
                    "title": None,
                    "author": r.get("user") or r.get("title") or "Play Store User",
                    "rating": r.get("rating", 1),
                    "date": r.get("date") or None,
                    "url": app_url,
                    "entity": app_name,
                    "likes": int(r.get("likes", 0) or 0),
                    "_priority": 100 + int(r.get("likes", 0) or 0),
                }
            )

    def add_reddit_posts(
        self,
        posts: List[Dict[str, Any]],
        entity: str = "Reddit Discussion",
    ) -> None:
        """Ingest Reddit discussions."""
        for p in posts:
            title = p.get("title", "")
            snippet = p.get("snippet", "")
            combined = f"{title}. {snippet}" if snippet else title
            norm_text = self._normalize_text(combined)
            if len(norm_text) < 20:
                continue

            sig = self._make_signature(norm_text)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)

            self._raw_candidates.append(
                {
                    "source": "reddit",
                    "text": norm_text,
                    "title": title or None,
                    "author": None,
                    "rating": None,
                    "date": None,
                    "url": p.get("link") or "",
                    "entity": entity,
                    "likes": 0,
                    "_priority": 80,
                }
            )

    def add_news_items(
        self,
        news_items: List[Dict[str, Any]],
        entity: str = "News",
    ) -> None:
        """Ingest Google News articles."""
        for n in news_items:
            title = n.get("title", "")
            snippet = n.get("snippet", "")
            combined = f"{title}. {snippet}" if snippet else title
            norm_text = self._normalize_text(combined)
            if len(norm_text) < 20:
                continue

            sig = self._make_signature(norm_text)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)

            self._raw_candidates.append(
                {
                    "source": "google_news",
                    "text": norm_text,
                    "title": title or None,
                    "author": n.get("source") or None,
                    "rating": None,
                    "date": n.get("date") or None,
                    "url": n.get("link") or "",
                    "entity": entity,
                    "likes": 0,
                    "_priority": 70,
                }
            )

    def add_youcom_results(
        self,
        youcom_items: List[Dict[str, Any]],
        entity: str = "Web Source",
    ) -> None:
        """Ingest You.com search and news results."""
        for y in youcom_items:
            title = y.get("title", "")
            snippet = y.get("snippet", "")
            combined = f"{title}. {snippet}" if snippet else title
            norm_text = self._normalize_text(combined)
            if len(norm_text) < 20:
                continue

            sig = self._make_signature(norm_text)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)

            source_type = "you_news" if y.get("kind") == "news" else "you_web"
            self._raw_candidates.append(
                {
                    "source": source_type,
                    "text": norm_text,
                    "title": title or None,
                    "author": None,
                    "rating": None,
                    "date": y.get("page_age") or None,
                    "url": y.get("url") or "",
                    "entity": entity,
                    "likes": 0,
                    "_priority": 75,
                }
            )

    def add_store_reviews(
        self,
        reviews: List[Dict[str, Any]],
        source: str,
        entity: str,
        url: str,
    ) -> None:
        """Ingest Maps or App Store reviews ({user, rating, snippet, date, likes})."""
        for r in sorted(reviews, key=lambda x: int(x.get("likes", 0) or 0), reverse=True):
            norm_text = self._normalize_text(r.get("snippet", ""))
            if len(norm_text) < 20:
                continue
            sig = self._make_signature(norm_text)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)
            self._raw_candidates.append(
                {
                    "source": source,
                    "text": norm_text,
                    "title": None,
                    "author": r.get("user"),
                    "rating": r.get("rating") or None,
                    "date": r.get("date") or None,
                    "url": url,
                    "entity": entity,
                    "likes": int(r.get("likes", 0) or 0),
                    "_priority": 95 + int(r.get("likes", 0) or 0),
                }
            )

    def add_generic(
        self,
        items: List[Dict[str, Any]],
        source: str,
        entity: str,
        priority: int = 60,
    ) -> None:
        """Ingest results that have title / snippet / link (Google Search, Maps, Jobs)."""
        for it in items:
            title = it.get("title", "") or ""
            snippet = it.get("snippet", "") or ""
            norm_text = self._normalize_text(f"{title}. {snippet}" if snippet and title not in snippet else (snippet or title))
            if len(norm_text) < 20:
                continue
            sig = self._make_signature(norm_text + (it.get("link") or ""))
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)
            self._raw_candidates.append(
                {
                    "source": source,
                    "text": norm_text,
                    "title": title or None,
                    "author": None,
                    "rating": None,
                    "date": it.get("date") or None,
                    "url": it.get("link") or "",
                    "entity": entity,
                    "likes": 0,
                    "_priority": priority,
                }
            )

    def build(self) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Finalize evidence map and list with sequentially stable IDs.
        Returns:
            evidence_map: {"ev_0001": {...}, ...}
            evidence_list: [{...}, ...]
        """
        # Sort candidates by priority descending
        sorted_candidates = sorted(
            self._raw_candidates, key=lambda c: c.get("_priority", 0), reverse=True
        )
        selected = sorted_candidates[: self.max_items]

        evidence_map: Dict[str, Dict[str, Any]] = {}
        evidence_list: List[Dict[str, Any]] = []

        for idx, item in enumerate(selected, start=1):
            ev_id = f"ev_{idx:04d}"
            ev_obj = {
                "id": ev_id,
                "source": item["source"],
                "text": item["text"],
                "title": item["title"],
                "author": item["author"],
                "rating": item["rating"],
                "date": item["date"],
                "url": item["url"],
                "entity": item["entity"],
                "likes": item["likes"],
            }
            evidence_map[ev_id] = ev_obj
            evidence_list.append(ev_obj)

        return evidence_map, evidence_list
