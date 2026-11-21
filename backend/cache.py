import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

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
                "CREATE TABLE IF NOT EXISTS brand_official (brand TEXT PRIMARY KEY, official TEXT, "
                "watch INTEGER DEFAULT 0, interval_hours INTEGER DEFAULT 24, last_run INTEGER DEFAULT 0)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS protect_allow (brand TEXT, type TEXT, value TEXT, created_at INTEGER, "
                "PRIMARY KEY (brand, type, value))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS protect_seen (brand TEXT, type TEXT, value TEXT, first_seen INTEGER, "
                "PRIMARY KEY (brand, type, value))"
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


def find_latest_report(mode: int, query: str) -> Optional[Dict[str, Any]]:
    """Latest saved report for (mode, query), case-insensitive. Used to replay presets in DEMO_MODE."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT report FROM reports WHERE mode = ? AND lower(query) = lower(?) "
            "ORDER BY created_at DESC LIMIT 1",
            (mode, query.strip()),
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None
    finally:
        conn.close()


def _bkey(brand: str) -> str:
    return " ".join((brand or "").lower().split())


def save_official(brand: str, official: Dict[str, Any], watch: Optional[bool] = None,
                  interval_hours: Optional[int] = None) -> None:
    conn = get_db_connection()
    try:
        with conn:
            row = conn.execute("SELECT watch, interval_hours FROM brand_official WHERE brand = ?", (_bkey(brand),)).fetchone()
            w = int(watch) if watch is not None else (row[0] if row else 0)
            ih = int(interval_hours) if interval_hours else (row[1] if row else 24)
            conn.execute(
                "INSERT OR REPLACE INTO brand_official (brand, official, watch, interval_hours, last_run) "
                "VALUES (?, ?, ?, ?, COALESCE((SELECT last_run FROM brand_official WHERE brand = ?), 0))",
                (_bkey(brand), json.dumps(official), w, ih, _bkey(brand)),
            )
    finally:
        conn.close()


def get_official(brand: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT official, watch, interval_hours, last_run FROM brand_official WHERE brand = ?",
                           (_bkey(brand),)).fetchone()
        if not row:
            return None
        return {"brand": _bkey(brand), "official": json.loads(row[0] or "{}"), "watch": bool(row[1]),
                "interval_hours": row[2], "last_run": row[3]}
    finally:
        conn.close()


def list_watched() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT brand, official, interval_hours, last_run FROM brand_official WHERE watch = 1").fetchall()
        return [{"brand": r[0], "official": json.loads(r[1] or "{}"), "interval_hours": r[2], "last_run": r[3]} for r in rows]
    finally:
        conn.close()


def mark_watch_run(brand: str) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("UPDATE brand_official SET last_run = ? WHERE brand = ?", (int(time.time()), _bkey(brand)))
    finally:
        conn.close()


def allow_item(brand: str, ftype: str, value: str, allowed: bool = True) -> None:
    """Mark a finding as allowed (e.g. a franchisee's number), or undo it. Removes a DB row, not a file."""
    conn = get_db_connection()
    try:
        with conn:
            if allowed:
                conn.execute("INSERT OR REPLACE INTO protect_allow (brand, type, value, created_at) VALUES (?, ?, ?, ?)",
                             (_bkey(brand), ftype, str(value), int(time.time())))
            else:
                conn.execute("DELETE FROM protect_allow WHERE brand = ? AND type = ? AND value = ?",
                             (_bkey(brand), ftype, str(value)))
    finally:
        conn.close()


def list_allowed(brand: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT type, value, created_at FROM protect_allow WHERE brand = ?", (_bkey(brand),)).fetchall()
        return [{"type": r[0], "value": r[1], "created_at": r[2]} for r in rows]
    finally:
        conn.close()


def mark_seen(brand: str, items: List[Tuple[str, str]]) -> set:
    """Record findings; return the (type, value) pairs that were NOT seen before."""
    conn = get_db_connection()
    new = set()
    try:
        with conn:
            for ftype, value in items:
                cur = conn.execute("INSERT OR IGNORE INTO protect_seen (brand, type, value, first_seen) VALUES (?, ?, ?, ?)",
                                   (_bkey(brand), ftype, str(value), int(time.time())))
                if cur.rowcount:
                    new.add((ftype, str(value)))
    finally:
        conn.close()
    return new


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
        "gemini_last_error": _gemini_error(),
    }


def _gemini_error():
    try:
        import llm
        return llm.LAST_GEMINI_ERROR
    except Exception:
        return None


# Auto-initialize DB on import
init_db()
