import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current file dir and parent dir
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

# API Keys
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
YDC_API_KEY = os.getenv("YDC_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Operational Modes
DEMO_MODE = os.getenv("DEMO_MODE", "0").strip().lower() in ("1", "true", "yes")

# Rate Limiting & Budgets
SERPAPI_HOURLY_LIMIT = int(os.getenv("SERPAPI_HOURLY_LIMIT", "45"))
SERPAPI_SCAN_BUDGET = int(os.getenv("SERPAPI_SCAN_BUDGET", "8"))
PORT = int(os.getenv("PORT", "5000"))

# Database
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent / "cache.db"))

# SerpApi Settings
SERPAPI_BASE_URL = "https://serpapi.com/search.json"
SERPAPI_DEFAULT_GL = "in"
SERPAPI_DEFAULT_HL = "en"
SERPAPI_DEFAULT_GEO = "IN"

# You.com Settings
YOUCOM_BASE_URL = "https://ydc-index.io/v1/search"
YOUCOM_COUNTRY = "IN"
YOUCOM_WEB_FIELD = "web"
YOUCOM_NEWS_FIELD = "news"

# Gemini LLM Settings
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash-lite").split(",") if m.strip()]
GEMINI_RETRIES = int(os.getenv("GEMINI_RETRIES", "2"))

# Scoring Thresholds
VIABILITY_BUILD_THRESHOLD = 65
VIABILITY_PIVOT_THRESHOLD = 40  # 40-64 = PIVOT, < 40 = KILL

# Google Trends is relative (each series peaks at 100). Demand is measured against
# a fixed anchor term fetched in the SAME request so the two series share one scale.
TRENDS_ANCHOR = os.getenv("TRENDS_ANCHOR", "credit card").strip()

# How many evidence items the LLM sees when clustering (interleaved across apps/sources)
LLM_SAMPLE_SIZE = int(os.getenv("LLM_SAMPLE_SIZE", "80"))

# Momentum counts dated news items inside this window
MOMENTUM_WINDOW_DAYS = int(os.getenv("MOMENTUM_WINDOW_DAYS", "90"))

# Telegram alerts for Mode 4 (optional; alerts are skipped when unset)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Optional extra sources (each costs SerpApi credits)
ENABLE_APP_STORE = os.getenv("ENABLE_APP_STORE", "0").strip().lower() in ("1", "true", "yes")
APP_STORE_COUNTRY = os.getenv("APP_STORE_COUNTRY", "in").strip()

# SerpApi Extract API. Parameter names are configurable because they are unverified;
# check them against serpapi.com docs on the day.
EXTRACT_ENGINE = os.getenv("EXTRACT_ENGINE", "extract").strip()
EXTRACT_URL_PARAM = os.getenv("EXTRACT_URL_PARAM", "url").strip()
EXTRACT_MAX_SITES = int(os.getenv("EXTRACT_MAX_SITES", "2"))
