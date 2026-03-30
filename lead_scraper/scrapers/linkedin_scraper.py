"""Cookie-backed LinkedIn scraping using Playwright."""

from __future__ import annotations

import json
import random
import time
from typing import Any
from urllib.parse import quote_plus

try:
    from fake_useragent import UserAgent
except ImportError:  # pragma: no cover - optional dependency.
    UserAgent = None  # type: ignore[assignment]

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError:  # pragma: no cover - optional until Playwright is installed.
    Page = Any  # type: ignore[misc,assignment]
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
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
COOKIES_PATH = BASE_DIR / "cookies" / "linkedin_cookies.json"


def _user_agent() -> str:
    """Return a realistic browser user agent with a fallback."""

    if UserAgent is None:
        return DEFAULT_USER_AGENT
    try:
        return UserAgent().chrome
    except Exception:
        return DEFAULT_USER_AGENT


def _sleep(min_seconds: float = 2.5, max_seconds: float = 4.0) -> None:
    """Pause briefly with jitter to reduce scraping cadence."""

    time.sleep(random.uniform(min_seconds, max_seconds))


def _session_expired(page: Page) -> bool:
    """Detect login redirects on LinkedIn search pages."""

    current_url = page.url.lower()
    if "/login" in current_url or "checkpoint" in current_url:
        print("Session expired. Run setup_cookies.py again.")
        return True
    return False


def scrape_linkedin(keywords: list[str], max_per_keyword: int = 20) -> list[Lead]:
    """
    Scrape LinkedIn content search results using a saved authenticated session.
    """

    if not COOKIES_PATH.exists():
        print("LinkedIn cookies not found. Run python setup_cookies.py first.")
        return []

    if sync_playwright is None:
        print("Playwright is not installed. Run pip install -r requirements.txt first.")
        return []

    try:
        cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Unable to read LinkedIn cookies: %s", exc)
        return []

    leads: list[Lead] = []
    seen_ids: set[str] = set()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_user_agent(),
                viewport={"width": 1280, "height": 800},
            )
            context.add_cookies(cookies)
            page = context.new_page()
            if stealth_sync is not None:
                stealth_sync(page)

            page.goto("https://www.linkedin.com/feed/", timeout=30_000, wait_until="domcontentloaded")
            _sleep(2.5, 3.5)
            if _session_expired(page):
                browser.close()
                return []

            for keyword in keywords:
                print(f"Scraping LinkedIn for: {keyword}")
                collected = 0
                scroll_attempts = 0

                try:
                    search_url = (
                        "https://www.linkedin.com/search/results/content/"
                        f"?keywords={quote_plus(keyword)}&sortBy=date_posted"
                    )
                    page.goto(search_url, timeout=30_000, wait_until="domcontentloaded")
                    _sleep(3.0, 4.5)
                    if _session_expired(page):
                        browser.close()
                        return []

                    while collected < max_per_keyword and scroll_attempts < 8:
                        cards = page.query_selector_all("div.feed-shared-update-v2, li.reusable-search__result-container")
                        for card in cards:
                            try:
                                text = ""
                                for selector in (
                                    "div.update-components-text",
                                    "span.break-words",
                                    "div.feed-shared-inline-show-more-text",
                                ):
                                    text_el = card.query_selector(selector)
                                    if text_el:
                                        text = text_el.inner_text().strip()
                                        if text:
                                            break
                                if len(text) < 20:
                                    continue

                                author = ""
                                for selector in (
                                    "span.update-components-actor__name",
                                    "span.entity-result__title-text",
                                    "span[dir='ltr']",
                                ):
                                    author_el = card.query_selector(selector)
                                    if author_el:
                                        author = author_el.inner_text().strip()
                                        if author:
                                            break

                                profile_url = ""
                                post_url = ""
                                for selector in (
                                    "a.update-components-actor__container-link",
                                    "a[href*='/in/']",
                                    "a[href*='/company/']",
                                ):
                                    profile_link = card.query_selector(selector)
                                    if profile_link:
                                        href = str(profile_link.get_attribute("href") or "").strip()
                                        if href:
                                            profile_url = href.split("?")[0]
                                            break

                                for selector in ("a[href*='/posts/']", "a[href*='/activity-']", "a[href*='/feed/update/']"):
                                    post_link = card.query_selector(selector)
                                    if post_link:
                                        href = str(post_link.get_attribute("href") or "").strip()
                                        if href:
                                            post_url = href.split("?")[0]
                                            break

                                unique_seed = post_url or profile_url or text[:80]
                                post_id = f"li_{abs(hash(unique_seed))}"
                                if post_id in seen_ids:
                                    continue

                                seen_ids.add(post_id)
                                leads.append(
                                    {
                                        "id": post_id,
                                        "title": text[:100],
                                        "body": text,
                                        "author": author,
                                        "url": post_url or profile_url,
                                        "profile_url": profile_url,
                                        "subreddit": "",
                                        "platform": "linkedin",
                                        "created_utc": int(time.time()),
                                        "score": 0,
                                        "outreach_type": "manual_dm",
                                    }
                                )
                                collected += 1
                                if collected >= max_per_keyword:
                                    break
                            except Exception as exc:
                                logger.debug("Skipping malformed LinkedIn card for keyword '%s': %s", keyword, exc)

                        page.evaluate("window.scrollBy(0, 2000)")
                        page.wait_for_timeout(random.randint(2_500, 4_000))
                        scroll_attempts += 1

                    print(f"  Collected {collected} posts for '{keyword}'")
                except Exception as exc:
                    print(f"  Error scraping LinkedIn for '{keyword}': {exc}")

                _sleep(4.0, 7.0)

            browser.close()
    except Exception as exc:
        logger.error("LinkedIn scraping failed: %s", exc)
        return []

    return leads
