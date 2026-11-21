# GapScope — Backend Engine

> Live Market-Intelligence Engine for Idea Validation, Competitor Investigation, and Category Discovery.
> Built for Track 01 (SerpApi) and Track 02 (You.com).

GapScope pulls verified, real-world evidence from **SerpApi** (Google Trends, Google Play Store reviews, Google News, Reddit) and **You.com** (web index, news), clusters user sentiment with **Gemini 2.5 Flash**, computes deterministic viability and trajectory formulas in Python, and serves verified market-gap reports via SSE streams.

---

## ⚡ Quickstart in 5 Commands

```bash
# 1. Navigate to backend directory
cd backend

# 2. (Optional) Create and activate virtual environment
python -m venv venv
venv\Scripts\activate   # Windows (or source venv/bin/activate on Linux/macOS)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your SERPAPI_KEY, YDC_API_KEY, and GEMINI_API_KEY

# 5. Start the backend server
python app.py
```

The server runs on `http://localhost:5000` with open CORS for frontend development.

---

## 🧪 Demo Prewarming & Cache

Fill the SQLite cache ahead of demo presentations so no network latency or quota limits affect live judging:

```bash
# Dry run: inspect call budget without executing requests
python prewarm.py --dry-run

# Run full prewarm across all 9 demo presets
python prewarm.py
```

To run completely offline during the demo:
Set `DEMO_MODE=1` in `.env`. On cache hit it serves instantly from SQLite `cache.db`; on cache miss it returns safely without making external calls.

---

## 📡 API Endpoints & `curl` Examples

### 1. Check Health & Quota Telemetry
```bash
curl http://localhost:5000/api/health
```
**Response:**
```json
{
  "cache_entries": 14,
  "demo_mode": false,
  "serpapi_live_calls_this_hour": 3
}
```

### 2. Get Demo Presets
```bash
curl http://localhost:5000/api/examples
```

### 3. Fetch Mock Reports (For Frontend Dev)
```bash
# Mode 1: Idea Validation mock
curl http://localhost:5000/api/mock/1

# Mode 2: Competitor Investigation mock
curl http://localhost:5000/api/mock/2

# Mode 3: Category Discovery mock
curl http://localhost:5000/api/mock/3
```

### 4. Start a Live Scan
```bash
curl -X POST http://localhost:5000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"mode": 1, "query": "UPI expense tracker for college students"}'
```
**Response:**
```json
{"scan_id": "a1b2c3d4"}
```

### 5. Stream Live Progress (Server-Sent Events)
```bash
curl -N http://localhost:5000/api/scan/a1b2c3d4/stream
```
**Streamed SSE Events:**
```
data: {"type": "progress", "step": "extract_keywords", "message": "Analyzing concept: 'UPI expense tracker for college students'", "pct": 10}

data: {"type": "progress", "step": "parallel_search", "message": "Querying Trends, Play Store, News, Reddit & You.com", "pct": 25}

data: {"type": "progress", "step": "play_reviews", "message": "Fetching 1★ reviews for 3 competitors", "pct": 50}

data: {"type": "progress", "step": "clustering", "message": "Clustering 95 evidence items into pain points", "pct": 70}

data: {"type": "progress", "step": "scoring", "message": "Computing deterministic Viability Score", "pct": 95}

data: {"type": "done", "report": { ... }}
```

### 6. Retrieve Stored Report (Share Links)
```bash
curl http://localhost:5000/api/report/a1b2c3d4
```

---

## 🛡️ Architecture & Guardrails

1. **SQLite WAL Cache (`cache.py`)**:
   - `sha256(provider + engine + sorted_params_without_key)` primary key.
   - 72-hour TTL with thread-safe SQLite WAL connections.
   - Sliding-window in-memory hourly limiter (`SERPAPI_HOURLY_LIMIT=45`) to safeguard hackathon account budgets.
2. **Anti-Hallucination Evidence Core (`evidence.py`)**:
   - Every raw review, reddit discussion, news snippet, and web citation is normalized into an Evidence item with a stable ID (`ev_0001`...).
   - Gemini clusters feedback by evidence ID **only**. No paraphrased or invented quotes.
   - Post-validation strips any dangling or nonexistent evidence IDs and flags AI-generated suggestions if evidence support is empty.
3. **Deterministic Scoring (`scoring.py`)**:
   - **Mode 1 Viability Score (0-100)**: Demand (30), Pain Intensity (30), Competition Gap (20), Momentum (10), Confidence (10). Thresholds: `BUILD >= 65`, `PIVOT 40-64`, `KILL < 40`.
   - **Mode 2 Trajectory**: Multi-signal voting across Google Trends slope, recent review rating drift, and news sentiment (`GROWING`, `STAGNATING`, `DECLINING`).
   - **Mode 3 Discovery**: Cross-app pain frequency ranking uncovering systemic whitespace.

## Demo-safety changes (21 Nov)

- **Gemini calls are cached** in `cache.db` (provider `gemini`, keyed by model + prompt hash). Same input → same keywords → same SerpApi cache keys, so `DEMO_MODE=1` works offline.
- **Preset replay:** `prewarm.py` now saves each preset report. With `DEMO_MODE=1`, scanning a preset query replays its saved report (short progress stream, no network).
- **Demand uses an anchor:** Trends is fetched as `"<keyword>,<TRENDS_ANCHOR>"` in one call (default anchor `credit card`, set in `.env`). Demand = keyword mean ÷ anchor mean.
- **Scoring tightened:** pain uses the items the model actually saw; momentum counts only news dated in the last `MOMENTUM_WINDOW_DAYS` (90); confidence = review depth + number of source families; no invented 4.0★ ratings when data is missing.
- **No invented content:** if Gemini is unavailable, clustering and opportunities return empty lists instead of template themes.
- **apps_affected** comes only from Play Store reviews. Cluster labels read "N of M items analysed".
- **SSE** replays earlier events on reconnect and pings every 15 s.
- **Contract:** `trend` is `null` when there is no Trends data; mock files carry `"sample": true`.
- **Check reports:** `python check_contract.py` (mocks + every saved report). Run after prewarm.
- Trends fallback retry is skipped once the per-scan SerpApi budget is used.

## New: Mode 2 timeline and Mode 4 Protect

**Mode 2 `timeline`** (null in other modes): month-by-month rows
`{month, search_interest, avg_rating, reviews_count, complaints, news_positive, news_negative, evidence_ids}`
and rule-based `turning_points` `{month, kind, description, evidence_ids}` where kind is
`search_rise|search_drop|rating_rise|rating_drop|complaint_spike|positive_news|negative_news`.
Ratings use only the newest reviews (the 1★/5★ sets are filtered and would bias averages).
Turning points show what changed and when, not proof of cause.

**Mode 4 Protect** (`POST /api/scan` with `{"mode": 4, "query": "<brand>", "official": {"domains": [], "phones": [], "app_ids": []}}`):
6 SerpApi calls (Google x2, Maps, Jobs, Play, News). Report has `findings[]`:
`{id, type, severity: high|medium|info, status: "suspected", title, value, why, url, evidence_ids, report_to[], report_text}`,
types `helpline|job_post|lookalike_site|fake_app|scam_report`. Without official records, items are `info` ("to confirm"), never flagged.
New evidence sources: `google_search`, `google_maps`, `google_jobs`.
Presets "Blue Dart" and "IRCTC" use their websites only: add official phones and app IDs in `DEMO_PRESETS` (app.py) before prewarming.

**Telegram alerts:** set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`; a Mode 4 scan with high/medium findings sends a message.

Tests: `python test_new_features.py` (timeline + Protect, all mocked).

## More features (21 Nov, afternoon)

| Feature | Where | Notes |
|---|---|---|
| Top Indian regions | Mode 1 `regions: [{name, value}]` | 1 extra Trends call (`GEO_MAP_0`); Mode 1 is now 8 calls |
| Offline businesses | Mode 1 | No Play Store match → Google Maps places + their newest reviews (source `google_maps`) |
| "Open as investigation" | Mode 1 `competitors[].investigate` | `{mode: 2, query}` for the frontend button |
| Underserved needs | Mode 3 `clusters[].underserved`, `underserved_reason` | True when a complaint appears in 2+ apps and demand is rising or flat |
| App Store reviews (optional) | Mode 2 | `ENABLE_APP_STORE=1`; +2 calls; source `app_store` |
| Compare | `GET /api/compare?a=<scan_id>&b=<scan_id>` | Two finished Mode 2 reports side by side |
| Saved official records | `POST/GET /api/protect/official` | Remembered for scans, the scheduler and the public page |
| Mark as allowed | `POST/DELETE/GET /api/protect/allow` | Allowed items are hidden from later scans (`allowed_count`) |
| New-only alerts | `findings[].is_new`, `new_count` | Telegram sends only new high/medium items; prewarm doesn't mark items as seen |
| Scheduled scans | `POST /api/protect/watch` + `python monitor.py` | `--once` for Windows Task Scheduler |
| Extract check | Mode 4 look-alike sites | Reads up to 2 pages; flags password/OTP/card/payment fields. Param names in `.env` (`EXTRACT_*`) are unverified: check the SerpApi docs |
| Public page | `GET /verified/<brand>` | Lists official websites, numbers and apps |

Tests: `python test_more_features.py`.
