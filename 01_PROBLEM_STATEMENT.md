# GapScope — Market Intelligence Where Every Insight Shows Its Source

**Beyond 9to5 Buildathon · Paytm Office, Bengaluru · Nov 21, 2026**
**Track 01: Best use of SerpApi** + **Track 02: You.com** (both are part of the core design, not add-ons)

---

## The problem

Founders and PMs decide what to build from gut feel, or from AI "idea validators" that make up SWOT analyses, competitors and "user pain points" without citing anything. You can't check that output, so you can't trust it.

The real signal is already public, spread across Play Store 1-star reviews, Reddit threads, Google Trends, news and the open web. Nobody has time to read 500 reviews and cross-check them against search demand and funding news.

## The solution

**GapScope** pulls live, structured market data and returns a **decision**, not an essay. Every claim links back to the review, post, headline or web page it came from.

| Layer | Tool | Job |
|---|---|---|
| **Structured data** | **SerpApi** | Play Store apps + 1★/5★/newest reviews, Google Trends (geo=IN), Google News, Reddit (via `site:reddit.com`), Google Autocomplete |
| **Web research** | **You.com Search API** | Competitor landscape, funding/pricing/layoff news, market reports, forum and blog complaints, and **fallback evidence when there is no Play Store app** (B2B SaaS, D2C, offline businesses) |
| **Reasoning** | **Gemini 2.5 Flash** | *Only* extracts keywords, clusters evidence and names the clusters. It refers to evidence **by ID** and never writes quotes. |
| **Scoring** | **Plain Python** | The Viability Score and Trajectory are **fixed formulas over measured signals**, not LLM opinions. Each factor shows its math and its sources. |

### Why this wins both tracks
- **SerpApi** is the data backbone: 5+ engines per scan, fetched in parallel, all cached.
- **You.com** covers what SerpApi's structured engines can't: open-web context with citations. This lets GapScope handle *any* business, not just apps.
- **Anti-hallucination by construction:** Gemini returns `evidence_ids`, the backend checks that every ID exists, and any claim without verified evidence gets an `AI-suggested` badge.

---

## The 3 modes

### Mode 1 — Validate my idea
*"I have an idea. Is there a real opportunity?"*
- A Gemini pre-step splits the messy idea into a **broad 1–2 word trend keyword** and **specific search terms**.
- Finds competitors (Play Store + You.com web), clusters their 1★ complaints, and measures India demand (Trends 12-month + slope).
- Output: **Viability Score 0–100 → `BUILD` (≥65) / `PIVOT` (40–64) / `KILL` (<40)**, a breakdown of each factor, the top pain clusters, and 3 ways to differentiate, each tied to a cluster.

### Mode 2 — Investigate a business
*"Why is this business succeeding or failing?"*
- Compares 1★ and 5★ review clusters (what people hate vs. love), recent reviews vs. all-time rating, Trends slope, and news + You.com coverage (funding, layoffs, launches).
- Output: **Trajectory `GROWING` / `STAGNATING` / `DECLINING`** with the signals behind it, the top reasons for growth or decline, and "What a new competitor would do differently".

### Mode 3 — Discover an opportunity
*"I don't have an idea. Find something worth building."*
- The user picks a category (e.g. Fintech, EdTech, Health, Quick-commerce). GapScope scans the top 5 apps, finds the frustrations that repeat **across several competitors**, and checks them against Reddit and You.com forum results.
- Output: **3 concrete startup concepts**, each backed by the exact complaints that point to it, with a demand check.

---

## Design principles (UI inspired by finprob.com's research style)
1. **Receipt-first cards:** a plain-language summary, a frequency badge ("38 of 120 reviews"), up to 3 verbatim quotes with source tags and `View original ↗` links, and an `AI-suggested` badge when nothing live supports the claim.
2. **Show the work:** a live progress timeline while scanning ("Fetched 120 Play Store reviews…") and a credit meter ("9 calls · 6 from cache").
3. **One-click demos:** example scan pills that hit a pre-warmed cache and load instantly at 0 credits.

## Engineering constraints
- SerpApi free tier: **50 searches/hour, 250/month.** Each scan has a fixed budget (≤8 SerpApi calls).
- **SQLite `cache.db`** keyed by `sha256(engine + sorted params)`, plus **`prewarm.py`** for the demo presets, plus a **`DEMO_MODE=1`** setting that only reads from cache (in case Wi-Fi fails during the demo).
- 2-person split: **Frontend** (HTML + Tailwind + Vanilla JS + Chart.js) and **Backend** (Flask + ThreadPoolExecutor). They are kept in sync by **one shared JSON contract**, and each side builds against **mock JSON** first so neither waits on the other.

## Demo script (3 minutes)
1. Click the "UPI expense tracker for college students" pill → Mode 1 → score **PIVOT 58**. Open a pain card to show the real quotes and click through to Play Store.
2. Mode 2 → "Dunzo" → **DECLINING**, backed by news receipts from SerpApi and You.com.
3. Mode 3 → "Personal Finance" → 3 concepts, each tied to complaints that repeat across competitors.
4. Point at the credit meter: "That whole demo cost 0 live credits. Every number on screen has a source."
