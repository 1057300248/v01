"""High-precision Google One offer-link filter.

Imported by the Docker entry command before main.py. It replaces only
``google_automation._extract_payment_link``; no other automation behavior is
changed.
"""

import logging
import re
from urllib.parse import urlparse

import google_automation as ga
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = {
    "support.google.com",
    "help.google.com",
    "policies.google.com",
    "myaccount.google.com",
    "accounts.google.com",
}

_ALLOWED_HOSTS = {
    "one.google.com",
    "gemini.google.com",
    "payments.google.com",
    "pay.google.com",
}

_ACTION_URL_RE = re.compile(
    r"(?:^|[/_?&=.-])"
    r"(offer|redeem|claim|trial|checkout|subscribe|subscription|upgrade|"
    r"activate|activation|signup|sign-up|purchase|buy|explore-plan)"
    r"(?:$|[/_?&=.-])",
    re.IGNORECASE,
)

_STRONG_TEXT_TERMS = (
    "claim offer",
    "redeem",
    "activate",
    "start trial",
    "free trial",
    "get started",
    "subscribe",
    "upgrade",
    "sign up",
    # Dutch UI strings visible on some Google One pages.
    "aanmelden",
    "proefperiode",
)


def _host_matches(host: str, choices: set[str]) -> bool:
    return any(host == item or host.endswith("." + item) for item in choices)


def _extract_payment_link(driver):
    """Return a high-confidence subscription/offer URL, never a help article."""
    candidates: list[tuple[int, str, str]] = []

    for link in driver.find_elements(By.TAG_NAME, "a"):
        try:
            href = (link.get_attribute("href") or "").strip()
            if not href:
                continue

            parsed = urlparse(href)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme not in ("http", "https") or not host:
                continue

            if _host_matches(host, _BLOCKED_HOSTS):
                continue
            if not _host_matches(host, _ALLOWED_HOSTS):
                continue

            text = " ".join(
                part for part in (
                    link.text,
                    link.get_attribute("aria-label") or "",
                    link.get_attribute("title") or "",
                )
                if part
            ).lower()

            url_text = (parsed.path + "?" + parsed.query + "#" + parsed.fragment).lower()
            action_url = bool(_ACTION_URL_RE.search(url_text))
            strong_text = any(term in text for term in _STRONG_TEXT_TERMS)

            # Generic navigation/product links are deliberately ignored.
            if not (action_url or strong_text):
                continue

            score = 0
            if host == "one.google.com" or host.endswith(".one.google.com"):
                score += 100
            elif host in ("payments.google.com", "pay.google.com"):
                score += 90
            elif host == "gemini.google.com" or host.endswith(".gemini.google.com"):
                score += 70

            if action_url:
                score += 50
            if strong_text:
                score += 25
            if any(term in url_text for term in ("checkout", "redeem", "claim", "offer", "trial")):
                score += 20

            candidates.append((score, href, text[:120]))
        except Exception:
            continue

    if not candidates:
        logger.info("Offer-link filter: no high-confidence offer URL found")
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, href, text = candidates[0]
    logger.info(
        "Offer-link filter: selected score=%s host=%s text=%r",
        score,
        urlparse(href).hostname,
        text,
    )
    return href


ga._extract_payment_link = _extract_payment_link
logger.info("Offer-link false-positive filter enabled")
