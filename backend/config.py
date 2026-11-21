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
GEMINI_MODEL = "gemini-2.5-flash"

# Scoring Thresholds
VIABILITY_BUILD_THRESHOLD = 65
VIABILITY_PIVOT_THRESHOLD = 40  # 40-64 = PIVOT, < 40 = KILL
