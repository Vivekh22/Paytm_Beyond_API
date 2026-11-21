import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from config import DB_PATH, DEMO_MODE, SERPAPI_HOURLY_LIMIT


class SerpApiRateLimiter:
    """Thread-safe hourly sliding window limiter for live SerpApi calls."""

    def __init__(self, limit: int = SERPAPI_HOURLY_LIMIT):
        self.limit = limit
        self.timestamps: list[float] = []
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        one_hour_ago = now - 3600.0
        self.timestamps = [t for t in self.timestamps if t > one_hour_ago]

    def can_call(self) -> bool:
        with self._lock:
            now = time.time()
            self._prune(now)
            return len(self.timestamps) < self.limit

    def record_call(self) -> bool:
        with self._lock:
            now = time.time()
            self._prune(now)
            if len(self.timestamps) < self.limit:
                self.timestamps.append(now)
                return True
            return False

    def calls_this_hour(self) -> int:
        with self._lock:
            now = time.time()
            self._prune(now)
            return len(self.timestamps)


_rate_limiter = SerpApiRateLimiter(limit=SERPAPI_HOURLY_LIMIT)


def get_db_connection() -> sqlite3.Connection:
    """Open a thread-safe connection to cache.db in WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    """Initialize cache and reports tables."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    provider TEXT,
                    engine TEXT,
                    params TEXT,
                    response TEXT,
                    created_at INTEGER
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    scan_id TEXT PRIMARY KEY,
                    mode INTEGER,
                    query TEXT,
                    report TEXT,
                    created_at INTEGER
                );
                """
            )
    finally:
        conn.close()


def clean_params_dict(params: Dict[str, Any]) -> Dict[str, Any]:
    """Strip sensitive auth keys and return a sanitized dictionary for hashing."""
    sensitive_keys = {"api_key", "apikey", "key", "X-API-Key", "token", "auth"}
    return {k: v for k, v in params.items() if k not in sensitive_keys}


def make_cache_key(provider: str, engine: str, params: Dict[str, Any]) -> str:
    """Compute sha256(provider + engine + json.dumps(params_without_api_key, sort_keys=True))."""
    sanitized = clean_params_dict(params)
    serialized = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    raw = f"{provider}:{engine}:{serialized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached_call(
    provider: str,
    engine: str,
    params: Dict[str, Any],
    fetch_fn: Callable[[], Any],
    ttl_hours: int = 72,
    tracker: Optional[Any] = None,
) -> Tuple[Optional[Any], bool, Optional[str]]:
    """
    Cached call handler.
    Returns (data, was_cached, warning_str).
    """
    key = make_cache_key(provider, engine, params)
    now = int(time.time())
    ttl_seconds = ttl_hours * 3600

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT response, created_at FROM cache WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row is not None:
            raw_response, created_at = row
            if now - created_at < ttl_seconds:
                try:
                    data = json.loads(raw_response)
                    if tracker:
                        tracker.record(provider, cached=True)
                    return data, True, None
                except Exception:
                    pass  # corrupted cache entry, fall through to fetch
    finally:
        conn.close()

    # Cache miss
    if DEMO_MODE:
        msg = f"DEMO_MODE=1: Cache miss for {provider}/{engine}. Network calls disabled."
        return None, False, msg

    # Hourly limit check for SerpApi
    if provider == "serpapi":
        if not _rate_limiter.can_call():
            msg = f"SerpApi hourly limit ({SERPAPI_HOURLY_LIMIT}) reached. Request refused to preserve quota."
            return None, False, msg

    # Execute fetch
    try:
        data = fetch_fn()
        if data is None:
            return None, False, f"Null response received from {provider}/{engine}."
    except Exception as exc:
        return None, False, f"Fetch failed for {provider}/{engine}: {str(exc)}"

    # Record live call count
    if provider == "serpapi":
        _rate_limiter.record_call()

    if tracker:
        tracker.record(provider, cached=False)

    # Persist in cache
    sanitized_params = clean_params_dict(params)
    serialized_params = json.dumps(sanitized_params, sort_keys=True)
    serialized_resp = json.dumps(data)

    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, provider, engine, params, response, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, provider, engine, serialized_params, serialized_resp, now),
            )
    except Exception:
        pass  # non-fatal if caching write fails
    finally:
        conn.close()

    return data, False, None


def save_report(scan_id: str, mode: int, query: str, report: Dict[str, Any]) -> None:
    """Save full JSON report to reports table."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports (scan_id, mode, query, report, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scan_id, mode, query, json.dumps(report), int(time.time())),
            )
    finally:
        conn.close()


def get_report(scan_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full JSON report by scan_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT report FROM reports WHERE scan_id = ?", (scan_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None
    except Exception:
        return None
    finally:
        conn.close()


def get_cache_stats() -> Dict[str, Any]:
    """Retrieve runtime cache and rate limit statistics."""
    conn = get_db_connection()
    cache_entries = 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM cache")
        row = cursor.fetchone()
        if row:
            cache_entries = row[0]
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "serpapi_live_calls_this_hour": _rate_limiter.calls_this_hour(),
        "cache_entries": cache_entries,
        "demo_mode": DEMO_MODE,
    }


# Auto-initialize DB on import
init_db()
