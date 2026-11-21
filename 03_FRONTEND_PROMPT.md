# FRONTEND PROMPT — paste into Claude

---

You are a senior frontend engineer with a strong eye for editorial design. Build the complete frontend for **GapScope**, a live market-intelligence engine for a one-day hackathon (Track 01: SerpApi, Track 02: You.com). Write **complete, working files** with no placeholders.

## Product in one line
The user submits an idea, a business, or a category. The backend pulls live evidence from **SerpApi** (Play Store, Trends, News, Reddit) and **You.com** (web research), clusters it, and returns a report where **every claim links to its source**. The UI's job is to make that trust visible.

## Stack (strict)
HTML5, Tailwind CSS (CDN `https://cdn.tailwindcss.com`), Vanilla JS (ES modules, no framework, no build step), Chart.js 4.4.1 from cdnjs, and the Inter font from Google Fonts. It must work by opening `index.html` through any static server.

## File layout
```
frontend/
  index.html          # landing + search + report container
  report.html         # optional: same app, loads /api/report/<id> from ?id= for share links
  js/config.js        # API_BASE = "http://localhost:5000", USE_MOCK = true/false
  js/api.js           # startScan(), streamScan(id, onEvent) via EventSource, getReport(id), getExamples(), getMock(mode)
  js/render.js        # pure functions: data → HTML strings (verdict, breakdown, clusters, competitors, opportunities, news)
  js/charts.js        # trend line chart + score gauge
  js/app.js           # state, events, mode switching, URL hash (#mode=1&q=...)
  mock/report_mode1.json, report_mode2.json, report_mode3.json   # matching the contract below
```
**Mock-first:** with `USE_MOCK=true`, every flow (including a fake progress stream driven by `setTimeout`) runs on the mock JSON, so I can build and demo before the backend is ready. Switching to the live backend means changing one flag.

## Design language (inspired by finprob.com's research aesthetic: take the style, don't copy the brand)
- Light, editorial, calm. Background `#FAFAFA`, cards `#FFFFFF` with a `1px #E5E7EB` border, `rounded-xl`, no heavy shadows (at most `shadow-sm` on hover).
- Text: near-black `#0A0A0A` headings, `#525252` body, `#A3A3A3` meta. Inter, tight tracking on headings, `tabular-nums` for all numbers.
- One accent: indigo `#4F46E5`. Verdict colours: BUILD/GROWING `#16A34A`, PIVOT/STAGNATING `#D97706`, KILL/DECLINING `#DC2626`.
- Source tags as small outlined pills, each with its own tint: `Play Store` green, `Reddit` orange, `Google News` blue, `You.com Web` violet, `You.com News` violet-outline.
- Generous whitespace, a max content width of `max-w-6xl`, and a readable 16px base size. It should feel like a research report, **not a chatbot**: no chat bubbles, no typing animations.
- Fully responsive (single column on mobile, 16px gutters, no horizontal scroll). Visible focus rings, `aria-live` on the progress area, and every interactive element reachable by keyboard.

## Page structure

### A. Header
"GapScope" wordmark, the tagline *"Market intelligence that shows its sources"*, a small "Powered by SerpApi · You.com · Gemini" note, and a **credit meter pill** on the right (`9 calls · 6 cached`, filled from `report.credits`).

### B. Hero + search
- **Mode switch:** a 3-option segmented control:
  1. **Validate an idea** — placeholder "e.g. UPI expense tracker for college students"
  2. **Investigate a business** — placeholder "e.g. Dunzo, Cult.fit, Swiggy Instamart"
  3. **Discover an opportunity** — swaps the text input for a grid of category chips (Personal Finance, EdTech, Healthcare, Quick-commerce, Travel, Mental Health, Agritech, plus "Other…" which opens a text input)
- A large search input with a primary "Scan" button. Enter submits.
- **Example scan pills** under the input (from `GET /api/examples`, falling back to a hard-coded list). One click fills the input, switches mode and scans immediately. Mark them with a small "⚡ instant" tag because they're cached.

### C. Live progress timeline (while scanning)
- A vertical step list fed by SSE `progress` events: each step shows a spinner, then a ✓, its message ("Fetched 120 1★ reviews from 3 apps") and a source icon, plus a thin progress bar from `pct`.
- Below it, skeleton cards that match the final layout. The aim is for judges to *see* the data being fetched.
- On an `error` event, show an inline card with the message and a Retry button. Show `report.warnings[]` as a dismissible amber notice above the report.

### D. Report
1. **Verdict hero card**
   - Mode 1: a Chart.js doughnut gauge (half-circle, 0–100) with the score in the centre, a large label pill (BUILD/PIVOT/KILL) and `verdict.headline`.
   - Mode 2: a large trajectory label with an arrow (↗ → ↘) and the headline.
   - Mode 3: "3 opportunities found across N apps · M complaints analysed".
   - Next to it, the **score breakdown**: one horizontal bar per `breakdown[]` factor (`score/max`) with its explanation. Clicking a factor that has evidence_ids opens the Evidence Drawer.
2. **Demand trend card:** a Chart.js line chart of `trend.points` ("Google Trends · India · last 12 months"), with a `change_pct` badge (▲14% rising). Thin line, no grid clutter, accent colour, gradient fill.
3. **Competitors:** a compact table/grid with icon, name, ★ rating, installs, source tag, "reviews scanned" and a `↗` link.
4. **Receipt cards (the core component)**, rendered from `clusters[]`. Mode 2 shows two columns, "Why users leave" (pain) and "Why users stay" (strength). Each card has:
   - a title plus a severity dot (high/med/low)
   - a plain-language `summary`
   - a **frequency badge**, e.g. `38 of 300 reviews`, with a tiny inline bar
   - an `apps_affected` chip list (Mode 3: "Seen in 4 of 5 apps", which is the key signal)
   - **up to 3 verbatim quotes** looked up from `report.evidence[id]`: italic quote text, `★1` for reviews, entity · date in meta, a source pill, and a **`View original ↗`** link (`target="_blank" rel="noopener"`)
   - a "+ N more receipts" button that opens the Evidence Drawer
   - an **`AI-suggested`** badge (dashed amber border plus a tooltip: "No live post supports this; treat as a hypothesis") when `ai_suggested` is true. In that case **render no quotes**.
5. **Opportunities / Concepts:** cards with title, pitch, target user, "Solves →" chips linking (scroll + highlight) to the cluster cards they address, and 1 supporting quote.
6. **News & web coverage:** a list of `news[]` items resolved via `evidence`, each with a sentiment dot, headline link, source and date, and a You.com or Google News tag.
7. **Report footer:** "Copy share link" (`report.html?id=scan_id`), "Print / Save PDF" (`window.print()` with a clean print stylesheet), and "N sources · generated at …".

### E. Evidence Drawer
A right-side slide-over (a bottom sheet on mobile) listing every evidence item for a cluster or factor, with filter chips by source and the full text with links. Esc closes it and focus is trapped while it's open.

## Rendering rules
- **Never show a quote that isn't in `report.evidence`.** Skip evidence IDs that don't resolve, without throwing an error.
- Escape all API text before inserting it (write an `esc()` helper) to prevent XSS from review content.
- Empty states: if there are no clusters, show "Not enough live evidence; try a broader term." A missing trend hides its card.
- Dates are shown as "2 Oct 2026". Numbers use `toLocaleString('en-IN')`.
- Destroy old Chart.js instances before redrawing.

## SHARED JSON CONTRACT (the backend dev builds exactly this; don't rename fields)
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
  "warnings": []
}
```
`source` values: `play_store | reddit | google_news | you_web | you_news`.
SSE events from `GET /api/scan/<id>/stream`: `{"type":"progress","step":"...","message":"...","pct":55}`, `{"type":"done","report":{...}}`, `{"type":"error","message":"..."}`.
Flow: `POST /api/scan {mode, query}` → `{scan_id}` → open the EventSource → render on `done`.

## Mock data
Write **realistic, India-flavoured** mock reports for all 3 modes (Mode 1: "UPI expense tracker for college students" → PIVOT 58; Mode 2: "Dunzo" → DECLINING; Mode 3: "Personal Finance" → 3 concepts). Each needs about 4 clusters, about 15 evidence items across all 5 sources, 12 trend points and 1 `ai_suggested` cluster so that state gets shown. Label the mock quotes clearly as sample data in a comment in the JSON-loading code.

## Priorities
**P0:** layout, mode switch, search and example pills, mock flow, verdict hero, receipt cards, Evidence Drawer.
**P1:** SSE progress timeline, trend chart, competitors, opportunities, Mode 2 two-column layout.
**P2:** share link and report.html, print stylesheet, credit meter, URL hash state.

Output files in this order: `index.html`, `js/config.js`, `js/api.js`, `js/render.js`, `js/charts.js`, `js/app.js`, then the mock JSONs.
