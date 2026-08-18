"""Standard-browser Google One offer checker for the safe cloud deployment.

This module intentionally uses a normal Chromium profile. It does not spoof a
Pixel device, alter browser fingerprints, or hide Selenium automation signals.
It is intended for checking offers that the signed-in account is legitimately
eligible to see.
"""

import io
import logging
import re
import shutil
import time
from typing import Callable, Optional
from urllib.parse import urlparse

import pyotp
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config

logger = logging.getLogger(__name__)
ProgressCB = Optional[Callable[[str, Optional[bytes]], None]]


class GoogleAutomationError(Exception):
    pass


def _shot(driver: webdriver.Chrome) -> Optional[bytes]:
    try:
        return driver.get_screenshot_as_png()
    except Exception:
        return None


def _report(cb: ProgressCB, msg: str, driver: Optional[webdriver.Chrome] = None) -> None:
    logger.info(msg)
    if cb:
        try:
            cb(msg, _shot(driver) if driver else None)
        except Exception as exc:
            logger.warning("progress callback failed: %s", exc)


def _build_driver() -> webdriver.Chrome:
    options = Options()
    if config.HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1365,900")
    options.add_argument("--lang=en-US")

    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    chromedriver = shutil.which("chromedriver")
    if chromium:
        options.binary_location = chromium

    service = Service(executable_path=chromedriver) if chromedriver else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(config.IMPLICIT_WAIT)
    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    return driver


def _wait(driver: webdriver.Chrome, by: str, value: str):
    return WebDriverWait(driver, config.WEBDRIVER_TIMEOUT).until(
        EC.element_to_be_clickable((by, value))
    )


def _generate_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _handle_totp_if_present(driver: webdriver.Chrome, secret: Optional[str], cb: ProgressCB) -> None:
    if not secret:
        return

    inputs = driver.find_elements(By.CSS_SELECTOR, "input")
    candidate = None
    for field in inputs:
        try:
            field_type = (field.get_attribute("type") or "").lower()
            name = (field.get_attribute("name") or "").lower()
            autocomplete = (field.get_attribute("autocomplete") or "").lower()
            if field.is_displayed() and (
                field_type in {"tel", "number"}
                or "totp" in name
                or "pin" in name
                or "one-time" in autocomplete
            ):
                candidate = field
                break
        except Exception:
            continue

    if not candidate:
        return

    _report(cb, "Authenticator-code field detected; submitting your TOTP code.", driver)
    candidate.clear()
    candidate.send_keys(_generate_totp(secret))
    for selector in ((By.ID, "totpNext"), (By.CSS_SELECTOR, 'button[type="submit"]')):
        try:
            driver.find_element(*selector).click()
            time.sleep(3)
            return
        except NoSuchElementException:
            continue


def _gmail_login(driver: webdriver.Chrome, email: str, password: str,
                 totp_secret: Optional[str], cb: ProgressCB) -> None:
    _report(cb, "Loading Google sign-in…", driver)
    driver.get(config.GMAIL_LOGIN_URL)

    try:
        email_field = _wait(driver, By.CSS_SELECTOR, 'input[name="identifier"], input[type="email"]')
        email_field.clear()
        email_field.send_keys(email)
        _wait(driver, By.ID, "identifierNext").click()
        time.sleep(2)

        password_field = _wait(driver, By.CSS_SELECTOR, 'input[type="password"]')
        password_field.clear()
        password_field.send_keys(password)
        _wait(driver, By.ID, "passwordNext").click()
        time.sleep(3)
    except TimeoutException as exc:
        raise GoogleAutomationError(f"Google sign-in form timed out: {exc}") from exc

    _handle_totp_if_present(driver, totp_secret, cb)

    parsed = urlparse(driver.current_url)
    if parsed.hostname == "accounts.google.com":
        page_text = (driver.page_source or "").lower()
        challenge_terms = (
            "verify it's you", "verify it’s you", "try another way",
            "security key", "google prompt", "captcha", "confirm it's you",
        )
        if any(term in page_text for term in challenge_terms):
            raise GoogleAutomationError(
                "Google requested an additional verification challenge. "
                "Complete that verification manually in your own browser, then retry."
            )
        if "/signin" in parsed.path:
            raise GoogleAutomationError("Google sign-in did not complete.")

    _report(cb, "Google sign-in completed.", driver)


def _extract_offer_link(driver: webdriver.Chrome) -> Optional[str]:
    keywords = config.GEMINI_OFFER_KEYWORDS
    url_pattern = re.compile(r"(gemini|googleone|upgrade|activate|offer|redeem|trial|checkout)", re.I)

    for link in driver.find_elements(By.TAG_NAME, "a"):
        try:
            text = " ".join(filter(None, [link.text, link.get_attribute("aria-label")])).lower()
            href = link.get_attribute("href") or ""
            if href and any(keyword in text for keyword in keywords):
                return href
        except Exception:
            continue

    for link in driver.find_elements(By.TAG_NAME, "a"):
        try:
            href = link.get_attribute("href") or ""
            if href and url_pattern.search(href):
                return href
        except Exception:
            continue

    return None


def _check_google_one(driver: webdriver.Chrome, cb: ProgressCB) -> Optional[str]:
    for url in (config.GOOGLE_ONE_URL, config.GOOGLE_ONE_OFFERS_URL):
        _report(cb, f"Checking {url}", driver)
        try:
            driver.get(url)
            time.sleep(3)
        except (TimeoutException, WebDriverException) as exc:
            _report(cb, f"Could not load {url}: {exc}", driver)
            continue

        link = _extract_offer_link(driver)
        if link:
            _report(cb, "A visible Google One / Google AI offer link was found.", driver)
            return link

    return None


def check_gemini_offer(email: str, password: str,
                       totp_secret: Optional[str] = None,
                       progress_callback: ProgressCB = None) -> Optional[str]:
    driver: Optional[webdriver.Chrome] = None
    try:
        _report(progress_callback, "Starting standard Chromium session…")
        driver = _build_driver()
        _gmail_login(driver, email, password, totp_secret, progress_callback)
        return _check_google_one(driver, progress_callback)
    except WebDriverException as exc:
        raise GoogleAutomationError(f"Browser automation failed: {exc}") from exc
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
