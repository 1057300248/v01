"""Runtime configuration for the safe cloud deployment."""

import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_TELEGRAM_ID_RAW = os.environ.get("ADMIN_TELEGRAM_ID", "").strip()
ADMIN_TELEGRAM_ID = int(ADMIN_TELEGRAM_ID_RAW) if ADMIN_TELEGRAM_ID_RAW else None

GMAIL_LOGIN_URL = "https://accounts.google.com/signin/v2/identifier"
GOOGLE_ONE_URL = "https://one.google.com/"
GOOGLE_ONE_OFFERS_URL = "https://one.google.com/about/plans"

GEMINI_OFFER_KEYWORDS = [
    "google ai pro",
    "gemini",
    "free trial",
    "trial",
    "activate",
    "get started",
    "offer",
    "redeem",
]

WEBDRIVER_TIMEOUT = int(os.environ.get("WEBDRIVER_TIMEOUT", "30"))
IMPLICIT_WAIT = int(os.environ.get("IMPLICIT_WAIT", "5"))
PAGE_LOAD_TIMEOUT = int(os.environ.get("PAGE_LOAD_TIMEOUT", "60"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() not in {"0", "false", "no"}

SESSION_STORE: dict = {}

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
