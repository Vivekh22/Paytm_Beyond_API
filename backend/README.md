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
