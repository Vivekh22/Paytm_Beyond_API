"""Telegram alerts for Mode 4 (Protect). Sends only when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set."""
import logging
from typing import Any, Dict

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def send_protect_alert(report: Dict[str, Any]) -> bool:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return False
    flagged = [f for f in report.get("findings", [])
               if f.get("severity") in ("high", "medium") and f.get("is_new", True)]
    if not flagged:
        return False
    lines = [f"GapScope Protect: {len(flagged)} NEW suspected impersonation(s) for {report.get('query')}"]
    for f in flagged[:8]:
        lines.append(f"- [{f['severity'].upper()}] {f['title']}: {f['value']}\n  {f.get('url') or ''}")
    if len(flagged) > 8:
        lines.append(f"...and {len(flagged) - 8} more in the report.")
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines), "disable_web_page_preview": True},
            timeout=10,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("Telegram alert failed: %s", exc)
        return False
