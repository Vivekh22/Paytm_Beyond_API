# Project Memory: GapScope (Idea Validator)

## Project Overview & Mission
GapScope is a live market-intelligence and startup idea validation engine designed for a one-day hackathon (Track 01: SerpApi, Track 02: You.com).
The user submits an idea, business, or category. GapScope fetches live multi-source evidence from SerpApi (Google Trends, Google Play Store reviews, Google News, Reddit) and You.com (Search API), clusters user pain points and strengths with Gemini 2.5 Flash, computes deterministic mathematical scores in Python, and returns a fully source-linked JSON intelligence report via Server-Sent Events (SSE).

## Tech Stack & Versions
- **Language**: Python 3.14 / 3.11+
- **Backend Web Server**: Flask 3.1.3 with flask-cors 6.0.5
- **Concurrency**: `concurrent.futures.ThreadPoolExecutor`
- **Cache & Storage**: SQLite3 (WAL mode)
- **AI / LLM**: `google-genai` 2.14.0 (`gemini-2.5-flash`, JSON schema output)
- **External Integrations**:
  - SerpApi (`google_trends`, `google_play`, `google_play_product`, `google_news`, `google`, `google_autocomplete`)
  - You.com (`https://ydc-index.io/v1/search`)

## Architecture & Core Decisions
1. **Thread-Safe SQLite Caching (`backend/cache.py`)**:
   - Uses `sha256(provider + engine + sorted_params_without_api_key)` as primary key.
   - Supports 72-hour TTL and `DEMO_MODE=1` to guarantee network-free instant demo execution.
   - In-memory sliding window rate limiter refuses calls above `SERPAPI_HOURLY_LIMIT=45` to prevent quota exhaustion.
2. **Anti-Hallucination Evidence Core (`backend/evidence.py` & `backend/llm.py`)**:
   - Evidence items receive stable sequentially mapped IDs (`ev_0001`...).
   - LLM groups items strictly by ID; post-validation enforces that every `evidence_ids` reference in clusters, opportunities, and verdict breakdowns exists in the `evidence` map.
3. **Deterministic Scoring Engine (`backend/scoring.py`)**:
   - **Mode 1**: Viability Score (0-100) based on Demand (30), Pain Intensity (30), Competition Gap (20), Momentum (10), Evidence Confidence (10). Thresholds: BUILD >= 65, PIVOT 40-64, KILL < 40.
   - **Mode 2**: Trajectory (-3 to +3 vote sum) based on Trends change %, recent review drift, and news sentiment.
   - **Mode 3**: Cross-app pain ranking highlighting systemic market opportunities.
4. **Streaming Protocol (`backend/app.py`)**:
   - `POST /api/scan` spawns background worker and returns `scan_id`.
   - `GET /api/scan/<id>/stream` streams SSE progress updates and final report.

## Progress & Roadmap
- [x] P0: SQLite Cache Layer with WAL mode and SerpApi rate limiting (`cache.py`)
- [x] P0: SerpApi client wrappers with defensive parsing (`serp_client.py`)
- [x] P0: You.com client integration for Track 02 (`youcom_client.py`)
- [x] P0: Anti-hallucination evidence normalization (`evidence.py`)
- [x] P0: Gemini 2.5/3.8 Flash clustering, opportunity generation, and post-validation (`llm.py`)
- [x] P0: Deterministic scoring formulas for Viability, Trajectory, and Discovery (`scoring.py`)
- [x] P0: Mode 1 Pipeline with ThreadPoolExecutor parallelization (`pipelines.py`)
- [x] P1: Mode 2 Pipeline (Competitor Investigation) and Mode 3 Pipeline (Category Discovery)
- [x] P0: Flask SSE routes, mock endpoints, and CORS config (`app.py`)
- [x] P0: Shared contract mock files (`mock/report_mode1.json`, `report_mode2.json`, `report_mode3.json`)
- [x] P0: Prewarm script with `--dry-run` and demo preset cache filling (`prewarm.py`)
- [x] P2: Setup documentation and curl examples (`README.md`)
- [x] Pulled Frontend application (`frontend/index.html`, `frontend/report.html`, `frontend/js/`, `frontend/css/`) from remote origin.
- [x] Integrated Mode 4 Protect (`protect.py`, `monitor.py`, `notify.py`, `timeline.py`, `compare.py`).
- [x] Configured serverless runtime: `api/index.py`, `requirements.txt`, and `vercel.json` rewrites.
- [x] Fixed Vercel 404 routing by removing legacy `version: 2`, bundling runtime modules directly into `api/`, and enabling on-demand SSE streaming.
- [x] Resolved Gemini 503/429 high demand & quota limits: default model updated to `gemini-3.1-flash-lite` with automatic fallback chain (`gemini-3.1-flash-lite` -> `gemini-3.5-flash-lite` -> `gemini-3.8-flash`) and backoff retry.
- [x] Verified live deployment on Vercel (`https://qwer-beta-ten.vercel.app`): `/api/health` returns HTTP 200, `/api/scan` returns HTTP 202, and SSE streams live progress chunks.
- [x] All code committed and synchronized across both `Vivekh22/Paytm_Beyond_API` and `AM-iSMAIL/qwer`.
