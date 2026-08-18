"""Runtime patch for high-precision Google One offer-link detection.

This file is imported automatically by Python's site module. It replaces only
``google_automation._extract_payment_link`` and intentionally leaves the rest
of the automation code untouched.
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _patch_offer_detection() -> None:
    import google_automation as ga
    from selenium.webdriver.common.by import By

    # Help/documentation destinations must never be treated as redemption URLs.
    blocked_hosts = {
        "support.google.com",
        "help.google.com",
        "policies.google.com",
        "myaccount.google.com",
        "accounts.google.com",
    }

    # Keep candidates constrained to the actual Google subscription/product flow.
    allowed_hosts = {
        "one.google.com",
        "gemini.google.com",
        "payments.google.com",
        "pay.google.com",
    }

    action_url_re = re.compile(
        r"(?:^|[/_?&=.-])"
        r"(offer|redeem|claim|trial|checkout|subscribe|subscription|upgrade|"
        r"activate|activation|signup|sign-up|purchase|buy|explore-plan)"
        r"(?:$|[/_?&=.-])",
        re.IGNORECASE,
    )

    strong_text_terms = (
        "claim offer",
        "redeem",
        "activate",
        "start trial",
        "free trial",
        "get started",
        "subscribe",
        "upgrade",
        # Common CTA text seen on localized Google One pages.
        "sign up",
        "aanmelden",
        "proefperiode",
    )

    def _host_matches(host: str, choices: set[str]) -> bool:
        return any(host == item or host.endswith("." + item) for item in choices)

    def _extract_payment_link(driver):
        """Return a likely subscription/offer URL without matching help pages."""
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

                if _host_matches(host, blocked_hosts):
                    continue
                if not _host_matches(host, allowed_hosts):
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
                action_url = bool(action_url_re.search(url_text))
                strong_text = any(term in text for term in strong_text_terms)

                # A generic product/navigation link is not enough. Require a real
                # action-looking URL or explicit CTA text.
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
            logger.info("Offer-link patch: no high-confidence offer URL found")
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        score, href, text = candidates[0]
        logger.info(
            "Offer-link patch: selected score=%s host=%s text=%r",
            score,
            urlparse(href).hostname,
            text,
        )
        return href

    ga._extract_payment_link = _extract_payment_link
    logger.info("Offer-link false-positive filter enabled")


try:
    _patch_offer_detection()
except Exception:
    # Never prevent the bot from starting if the patch cannot be applied.
    logger.exception("Failed to apply offer-link false-positive filter")
