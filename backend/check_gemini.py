"""Quick Gemini check: python check_gemini.py  (prints OK or the exact error)."""
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL

if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is empty in backend/.env")
print(f"Key length {len(GEMINI_API_KEY)}, model {GEMINI_MODEL}")
try:
    r = genai.Client(api_key=GEMINI_API_KEY).models.generate_content(
        model=GEMINI_MODEL, contents='Return {"ok": true} as JSON',
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0))
    print("OK:", r.text)
except Exception as e:
    print("FAILED:", type(e).__name__, e)
