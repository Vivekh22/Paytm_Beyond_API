# BACKEND PROMPT — paste into Claude

---

You are a senior Python engineer. Build the complete backend for **GapScope**, a live market-intelligence engine for a one-day hackathon (Track 01: SerpApi, Track 02: You.com). Write **complete, runnable files**: no placeholders, no "TODO: implement". I have one day, so put correctness and the demo first.

## Product in one line
The user submits an idea, a business, or a category. We fetch live evidence from **SerpApi** and **You.com**, **Gemini 2.5 Flash** clusters it by evidence ID, **Python computes the scores**, and we return one JSON report where every claim links to a real source.

## Stack
Python 3.11, Flask, flask-cors, requests, python-dotenv, `google-genai` (Gemini SDK), sqlite3 (stdlib), `concurrent.futures.ThreadPoolExecutor`. No other frameworks.

## File layout
```
backend/
  app.py              # Flask routes, SSE stream
  config.py           # env vars, budgets, thresholds
  cache.py            # SQLite cache layer
  serp_client.py      # SerpApi wrappers (all cached)
  youcom_client.py    # You.com wrappers (all cached)
  llm.py              # Gemini calls: keyword extraction, clustering, concepts (strict JSON)
  evidence.py         # normalise raw results → Evidence items with stable IDs
  scoring.py          # deterministic Viability Score + Trajectory formulas
  pipelines.py        # mode1_validate, mode2_investigate, mode3_discover
  prewarm.py          # runs every demo preset to fill cache.db
  mock/report_mode1.json, report_mode2.json, report_mode3.json   # valid contract examples
  .env.example        # SERPAPI_KEY, YDC_API_KEY, GEMINI_API_KEY, DEMO_MODE=0
  requirements.txt
  README.md           # setup + run in 5 commands
```

## 1. Cache (`cache.py`): critical
- SQLite file `cache.db`, table `cache(key TEXT PRIMARY KEY, provider TEXT, engine TEXT, params TEXT, response TEXT, created_at INTEGER)`.
- `key = sha256(provider + engine + json.dumps(params_without_api_key, sort_keys=True))`.
- `cached_call(provider, engine, params, fetch_fn, ttl_hours=72)` returns `(data, was_cached)`.
- Thread-safe: open a new connection per call (`check_same_thread=False`, WAL mode).
- If `DEMO_MODE=1`: **never call the network**. On a cache miss return `None` and add a warning to the report.
- Keep an in-memory hourly counter of live SerpApi calls. If it reaches `SERPAPI_HOURLY_LIMIT=45` (leave headroom under 50), refuse new live calls and return a clear `warnings[]` entry. Don't crash.

## 2. SerpApi client (`serp_client.py`)
All requests go to `https://serpapi.com/search.json` with `api_key`, and all use India defaults (`gl=in`, `hl=en`, `geo=IN` for Trends). Functions:
- `trends_timeseries(keyword)`: `engine=google_trends, q, geo=IN, data_type=TIMESERIES, date="today 12-m"` → `[{date, value}]`
- `trends_related(keyword)`: `data_type=RELATED_QUERIES` → rising queries (demand signals)
- `play_search(query)`: `engine=google_play, store=apps, q` → top apps `[{title, product_id, rating, installs?, thumbnail, link}]` (parse defensively: results sit under `organic_results[].items[]` or `app_highlight`)
- `play_reviews(product_id, rating=None, sort_by=None, num=100)`: `engine=google_play_product, store=apps, product_id, all_reviews=true`, optional `rating` (1–5) and `sort_by` (1 relevant, 2 newest) → reviews `[{id, title/user, rating, snippet, date, likes}]`, plus product `rating` and `reviews` count
- `news(query)`: `engine=google_news, q, gl=in, hl=en` → `[{title, source, date, link, snippet}]`
- `reddit(query)`: `engine=google, q="{query} site:reddit.com", gl=in, num=10` → `[{title, snippet, link}]`
- `autocomplete(query)` (optional, cheap): `engine=google_autocomplete` → suggestions

Every function: wrap in `cached_call`, use `timeout=20`, on any failure return `[]` plus a warning. One failed source must never kill a scan.

## 3. You.com client (`youcom_client.py`): Track 02
- `you_search(query, count=10)`: You.com Search API, `GET https://ydc-index.io/v1/search?query=...&count=...&country=IN` with header `X-API-Key: {YDC_API_KEY}`. Return a normalised list `[{title, url, snippet, page_age, kind: "web"|"news"}]` from `results.web[]` (use `snippets[0]` or `description`) and `results.news[]`.
  **Parse defensively and keep the base URL and field names in `config.py`**, because I'll check them against docs.you.com on the day. If the response shape differs, log the raw keys.
- What each mode uses You.com for:
  - Mode 1: `"{broad} startups India competitors funding"` and `"{specific} problems complaints"`, to find competitors that aren't Play Store apps, plus forum and blog pain points.
  - Mode 2: `"{company} funding layoffs revenue 2026"` and `"{company} customer complaints"`, for trajectory context.
  - Mode 3: `"{category} India users biggest problems"` and `"{category} market report India 2026"`.
- **Fallback:** if `play_search` returns 0 relevant apps (B2B or offline business), You.com plus Reddit results become the main pain evidence.
- All You.com calls are cached with `provider="youcom"`.

## 4. Evidence normalisation (`evidence.py`): anti-hallucination core
Turn every raw item into:
```json
{"id":"ev_0007","source":"play_store|reddit|google_news|you_web|you_news",
 "text":"verbatim text, trimmed to 400 chars","title":null,"author":null,
 "rating":1,"date":"2026-10-02","url":"https://...","entity":"App or site name","likes":12}
```
- IDs are stable within a report (`ev_0001`…). Drop items under 20 characters, deduplicate near-identical texts, and keep at most ~150 items (prefer the most-liked reviews).
- Play Store reviews have no per-review URL, so use the app's Play Store link as `url`.

## 5. LLM layer (`llm.py`): Gemini `gemini-2.5-flash`
Use `response_mime_type="application/json"` with a response schema and temperature 0.2. Retry once if the JSON doesn't parse.
- `extract_keywords(idea)` → `{"broad":"expense tracker","specific":["UPI expense tracker","student budget app"],"category":"Finance"}`. The broad term **must** be 1–2 common words so Google Trends returns data. If Trends comes back empty, retry with a shorter fallback.
- `cluster_evidence(evidence_list, context)`: send items as `[ev_0007] (play_store, 1★) text…`. The prompt **must** say: *"Group these into 3–6 pain clusters. Reference evidence ONLY by ID. Never write or paraphrase quotes. If a cluster has no supporting IDs, set ai_suggested=true."* It returns `[{title, summary, evidence_ids[], severity: high|medium|low}]`.
- `generate_opportunities(clusters, context)` → `[{title, pitch, target_user, addresses_cluster_ids[]}]`.
- Mode 2: `classify_news(headlines_with_ids)` → per-ID `positive|neutral|negative`.

**Post-validation (required):** remove every `evidence_id` that doesn't exist in the pool. Compute `frequency.count = len(valid ids)`. If 0 remain, set `ai_suggested=true`. Quotes in the response always come from the evidence pool, never from LLM text.

## 6. Deterministic scoring (`scoring.py`)
**Viability Score (Mode 1), 0–100**, where every factor returns `{factor, score, max, explanation, evidence_ids}`:
| Factor | Max | Formula |
|---|---|---|
| Demand | 30 | mean Trends value (0–100) × 0.2 + slope bonus (last 3 months vs previous 9: +10 rising, +5 flat, 0 falling) |
| Pain intensity | 30 | share of scanned 1★ reviews that land in the top 3 clusters × 30 |
| Competition gap | 20 | `(5 − avg competitor rating) / 2 × 20`, capped; low-rated incumbents mean an open gap |
| Momentum | 10 | count of news + You.com items from the last 90 days, scaled (≥10 items = 10) |
| Evidence confidence | 10 | `min(total_evidence / 100, 1) × 10` |

Label: `BUILD ≥ 65`, `PIVOT 40–64`, `KILL < 40`. Put the thresholds in `config.py`.

**Trajectory (Mode 2):** combine (a) Trends change % (last 3 months vs previous 9), (b) average rating of the newest 100 reviews minus the all-time rating, (c) news sentiment ratio. Each signal votes +1/0/−1. A sum ≥ +2 is `GROWING`, ≤ −2 is `DECLINING`, anything else is `STAGNATING`. Return every signal with its value and sources.

## 7. Pipelines (`pipelines.py`): parallel with ThreadPoolExecutor(max_workers=8)
SerpApi budget per scan: **at most 8 live calls.** Emit a progress event after each step.
- **Mode 1:** extract_keywords → in parallel: trends_timeseries(broad), play_search(specific[0]), news(broad), reddit(specific[0]), you_search ×2 → play_reviews(rating=1) for the top 3 apps (in parallel) → normalise → cluster → opportunities → score.
- **Mode 2:** play_search(name) → pick the best-matching product_id → in parallel: reviews rating=1, rating=5, sort_by=2 (newest), news(name), trends(name), reddit(name), you_search ×2 → cluster the 1★ set as `weaknesses` and the 5★ set as `strengths` → classify_news → trajectory → "what a challenger would do differently" (opportunities).
- **Mode 3:** play_search(category) → top 5 apps → play_reviews(rating=1) ×5 in parallel, plus reddit(category), trends(category), you_search ×2 → cluster across apps. **Rank clusters by how many different apps they appear in** (a cross-competitor pain is the real gap) → 3 concepts.

## 8. API (`app.py`)
- `POST /api/scan` with body `{"mode":1|2|3,"query":"..."}` → `{"scan_id":"..."}` (run the pipeline in a background thread and store the result in memory plus a SQLite `reports` table)
- `GET /api/scan/<id>/stream`: **Server-Sent Events** carrying `{"type":"progress","step":"play_reviews","message":"Fetched 120 1★ reviews from 3 apps","pct":55}`, then a final `{"type":"done","report":{...}}` or `{"type":"error","message":"..."}`
- `GET /api/report/<id>` → full report (for share links)
- `GET /api/examples` → demo presets `[{mode, query, label}]` (same list prewarm.py uses)
- `GET /api/health` → `{serpapi_live_calls_this_hour, cache_entries, demo_mode}`
- `GET /api/mock/<mode>` → returns `mock/report_mode{n}.json` so the frontend can build before the pipelines work
- CORS open for local dev. Run on port 5000.

## 9. SHARED JSON CONTRACT (the frontend dev has the same copy, so don't change names)
```json
{
  "scan_id": "a1b2c3", "mode": 1, "query": "UPI expense tracker for college students",
  "generated_at": "2026-11-21T10:00:00Z",
  "keywords": {"broad": "expense tracker", "specific": ["UPI expense tracker"], "category": "Finance"},
  "credits": {"serpapi_live": 3, "serpapi_cached": 5, "youcom_live": 1, "youcom_cached": 1},
  "verdict": {
    "kind": "viability|trajectory|discovery",
    "label": "BUILD|PIVOT|KILL|GROWING|STAGNATING|DECLINING|null",
    "score": 58,
    "headline": "Real pain, crowded market — differentiate on privacy",
    "breakdown": [{"factor": "Demand", "score": 18, "max": 30, "explanation": "Avg interest 52/100, rising 14%", "evidence_ids": []}]
  },
  "trend": {"keyword": "expense tracker", "geo": "IN", "points": [{"date": "2025-12", "value": 41}], "change_pct": 14.2, "direction": "rising|flat|falling"},
  "competitors": [{"name": "Walnut", "product_id": "com.daamitt.walnut.app", "rating": 4.1, "installs": "10M+", "icon": "https://...", "url": "https://...", "source": "play_store|you_web", "reviews_scanned": 100}],
  "clusters": [{
    "id": "cl_1", "group": "pain|strength", "title": "Auto-categorisation is wrong",
    "summary": "Users say UPI transactions get mis-tagged and fixing them takes manual effort.",
    "severity": "high", "frequency": {"count": 38, "total": 300, "label": "38 of 300 reviews"},
    "apps_affected": ["Walnut", "Money View"], "evidence_ids": ["ev_0007", "ev_0019", "ev_0044"],
    "ai_suggested": false
  }],
  "opportunities": [{"id": "op_1", "title": "Privacy-first SMS-free tracker", "pitch": "...", "target_user": "College students on UPI",
                     "addresses_cluster_ids": ["cl_1"], "evidence_ids": ["ev_0007"], "ai_suggested": false}],
  "news": [{"evidence_id": "ev_0101", "sentiment": "negative|neutral|positive"}],
  "evidence": {"ev_0007": {"id": "ev_0007", "source": "play_store", "text": "...", "title": null, "author": "R. K.", "rating": 1, "date": "2026-10-02", "url": "https://...", "entity": "Walnut", "likes": 12}},
  "warnings": ["Google Trends returned no data for 'upi expense tracker for students'; used 'expense tracker'"]
}
```
Rules: `evidence` is a map keyed by ID, and every `evidence_ids` entry anywhere **must** exist in it. Mode 2 uses `group: "strength"` clusters for 5★ themes. Arrays may be empty, but no key may be missing.

## 10. `prewarm.py`
Run the full pipeline for these presets and print credits used:
- Mode 1: "UPI expense tracker for college students", "AI tutor for JEE aspirants", "Pet care booking app in Bengaluru"
- Mode 2: "Dunzo", "Swiggy Instamart", "Cult.fit"
- Mode 3: "Personal Finance", "EdTech", "Healthcare"

Add a `--dry-run` flag that only estimates how many SerpApi calls it would make.

## Priorities
**P0:** cache, serp_client, evidence, llm with validation, Mode 1 pipeline, `/api/scan` + SSE + `/api/mock`, prewarm.
**P1:** Modes 2 and 3, You.com client, scoring breakdown.
**P2:** report persistence and share link, autocomplete, health endpoint.

Start with `requirements.txt`, `.env.example`, `config.py` and `cache.py`, then the other files in dependency order. Finish with the README and an example `curl` for each endpoint.
