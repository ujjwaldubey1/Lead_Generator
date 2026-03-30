"""Local email discovery helpers for social leads without paid enrichment APIs."""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests

try:
    from fake_useragent import UserAgent
except ImportError:  # pragma: no cover - optional dependency.
    UserAgent = None  # type: ignore[assignment]

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional until Playwright is installed.
    sync_playwright = None  # type: ignore[assignment]

try:
    from playwright_stealth import stealth_sync
except ImportError:  # pragma: no cover - optional until playwright-stealth is installed.
    stealth_sync = None  # type: ignore[assignment]

try:
    from ..config import BASE_DIR
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
COOKIES_DIR = BASE_DIR / "cookies"


def _user_agent() -> str:
    """Return a realistic browser user agent with a static fallback."""

    if UserAgent is None:
        return DEFAULT_USER_AGENT
    try:
        return UserAgent().chrome
    except Exception:
        return DEFAULT_USER_AGENT


def find_email_in_text(text: str) -> str | None:
    """Extract the first likely personal email address from text."""

    matches = EMAIL_REGEX.findall(text)
    skip = ["noreply", "support", "info@", "hello@", "admin@", "contact@"]
    for match in matches:
        if not any(marker in match.lower() for marker in skip):
            return match
    return None


def _cookie_path_for_platform(platform: str) -> Path:
    """Return the saved cookie path for the given social platform."""

    normalized = platform.strip().lower()
    if normalized == "twitter":
        return COOKIES_DIR / "x_cookies.json"
    return COOKIES_DIR / "linkedin_cookies.json"


def find_email_from_profile(profile_url: str, platform: str) -> str | None:
    """
    Visit a social profile and look for an email address in the visible page HTML.
    """

    if not profile_url or sync_playwright is None:
        return None

    cookie_path = _cookie_path_for_platform(platform)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_user_agent(),
                viewport={"width": 1280, "height": 800},
            )
            if cookie_path.exists():
                context.add_cookies(json.loads(cookie_path.read_text(encoding="utf-8")))
            page = context.new_page()
            if stealth_sync is not None:
                stealth_sync(page)
            page.goto(profile_url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(random.randint(1_500, 2_500))
            html = page.content()
            browser.close()
            return find_email_in_text(html)
    except Exception as exc:
        logger.info("Profile email scan failed for platform=%s url=%s: %s", platform, profile_url, exc)
        return None


def find_email_google(name: str, company: str = "") -> str | None:
    """
    Search Google snippets for an email address using a person's name and company.
    """

    if not name:
        return None

    query = f'"{name}" {company} email contact'.strip()
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=5"
    headers = {"User-Agent": _user_agent()}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        time.sleep(random.uniform(1.0, 2.0))
        return find_email_in_text(response.text)
    except requests.RequestException as exc:
        logger.info("Google email search failed for name=%s: %s", name, exc)
        return None


def _extract_company_domain(lead: Lead) -> str:
    """Infer a company or profile domain from known lead URLs."""

    for field in ("company_website", "profile_url", "company_url", "url"):
        value = str(lead.get(field, "")).strip()
        if not value:
            continue
        parsed = urlparse(value)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain and domain not in {"x.com", "twitter.com", "linkedin.com"}:
            return domain
    return ""


def _guess_email_candidates(name: str, domain: str) -> list[str]:
    """Generate common email address patterns from a name and company domain."""

    if not name or not domain:
        return []

    parts = [part for part in re.split(r"[^A-Za-z]+", name.lower()) if part]
    if not parts:
        return []

    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    candidates = {
        f"{first}@{domain}",
        f"{first}.{last}@{domain}" if last else "",
        f"{first[0]}{last}@{domain}" if last else "",
        f"{first}{last[0]}@{domain}" if last else "",
    }
    return [candidate for candidate in candidates if candidate]


def find_email_for_lead(lead: Lead) -> Lead:
    """
    Try local profile scraping and lightweight public search to enrich a lead.
    """

    enriched = dict(lead)
    email = str(enriched.get("email", "")).strip() or None

    if not email:
        profile_url = str(enriched.get("profile_url") or enriched.get("url") or "").strip()
        if profile_url:
            email = find_email_from_profile(profile_url, str(enriched.get("platform", "")).strip())

    if not email:
        email = find_email_google(
            str(enriched.get("author", "")).strip(),
            str(enriched.get("company", "")).strip(),
        )

    if not email:
        domain = _extract_company_domain(enriched)
        guessed = _guess_email_candidates(str(enriched.get("author", "")).strip(), domain)
        email = guessed[0] if guessed else None

    enriched["email"] = email
    enriched["outreach_type"] = "cold_email" if email else "manual_dm"
    return enriched
