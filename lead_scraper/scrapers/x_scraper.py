"""Cookie-backed X scraping using Playwright."""

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
    from .browser_utils import launch_chromium
    from ..config import BASE_DIR
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from scrapers.browser_utils import launch_chromium
    from config import BASE_DIR
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
COOKIES_PATH = BASE_DIR / "cookies" / "x_cookies.json"


def _user_agent() -> str:
    """Return a realistic browser user agent with a fallback."""

    if UserAgent is None:
        return DEFAULT_USER_AGENT
    try:
        return UserAgent().chrome
    except Exception:
        return DEFAULT_USER_AGENT


def _sleep(min_seconds: float = 2.0, max_seconds: float = 3.5) -> None:
    """Pause briefly with jitter to reduce scraping cadence."""

    time.sleep(random.uniform(min_seconds, max_seconds))


def _session_expired(page: Page) -> bool:
    """Detect when X has redirected the browser back to a login flow."""

    current_url = page.url.lower()
    if "login" in current_url or "i/flow" in current_url:
        print("Session expired. Run setup_cookies.py again.")
        return True
    return False


def scrape_x(keywords: list[str], max_per_keyword: int = 30) -> list[Lead]:
    """
    Scrape X posts for each keyword using a saved authenticated session.
    """

    if not COOKIES_PATH.exists():
        print("X cookies not found. Run python setup_cookies.py first.")
        return []

    if sync_playwright is None:
        print("Playwright is not installed. Run pip install -r requirements.txt first.")
        return []

    try:
        cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Unable to read X cookies: %s", exc)
        return []

    leads: list[Lead] = []
    seen_ids: set[str] = set()

    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright, headless=True)
            context = browser.new_context(
                user_agent=_user_agent(),
                viewport={"width": 1280, "height": 800},
            )
            context.add_cookies(cookies)
            page = context.new_page()
            if stealth_sync is not None:
                stealth_sync(page)

            page.goto("https://x.com/home", timeout=30_000, wait_until="domcontentloaded")
            _sleep(2.0, 3.0)
            if _session_expired(page):
                browser.close()
                return []

            for keyword in keywords:
                print(f"Scraping X for: {keyword}")
                collected = 0
                scroll_attempts = 0

                try:
                    search_url = f"https://x.com/search?q={quote_plus(keyword)}&f=live&src=typed_query"
                    page.goto(search_url, timeout=30_000, wait_until="domcontentloaded")
                    _sleep(2.5, 4.0)
                    if _session_expired(page):
                        browser.close()
                        return []

                    while collected < max_per_keyword and scroll_attempts < 10:
                        articles = page.query_selector_all("article[data-testid='tweet']")
                        for article in articles:
                            try:
                                link_el = article.query_selector("a[href*='/status/']")
                                if link_el is None:
                                    continue

                                href = str(link_el.get_attribute("href") or "").strip()
                                if "/status/" not in href:
                                    continue

                                post_id = href.split("/status/")[-1].split("/")[0]
                                if not post_id or post_id in seen_ids:
                                    continue

                                text_el = article.query_selector("div[data-testid='tweetText']")
                                text = text_el.inner_text().strip() if text_el else ""
                                if len(text) < 20:
                                    continue

                                seen_ids.add(post_id)

                                username = ""
                                user_el = article.query_selector("div[data-testid='User-Name']")
                                if user_el:
                                    for span in user_el.query_selector_all("span"):
                                        value = span.inner_text().strip()
                                        if value.startswith("@"):
                                            username = value[1:]
                                            break

                                profile_url = f"https://x.com/{username}" if username else ""
                                post_url = f"https://x.com{href}" if href.startswith("/") else href

                                leads.append(
                                    {
                                        "id": f"x_{post_id}",
                                        "title": text[:100],
                                        "body": text,
                                        "author": username,
                                        "url": post_url,
                                        "profile_url": profile_url,
                                        "subreddit": "",
                                        "platform": "twitter",
                                        "created_utc": int(time.time()),
                                        "score": 0,
                                        "outreach_type": "manual_dm",
                                    }
                                )
                                collected += 1
                                if collected >= max_per_keyword:
                                    break
                            except Exception as exc:
                                logger.debug("Skipping malformed X article for keyword '%s': %s", keyword, exc)

                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(random.randint(2_000, 3_500))
                        scroll_attempts += 1

                    print(f"  Collected {collected} posts for '{keyword}'")
                except Exception as exc:
                    print(f"  Error scraping X for '{keyword}': {exc}")

                _sleep(3.0, 6.0)

            browser.close()
    except Exception as exc:
        logger.error("X scraping failed: %s", exc)
        return []

    return leads
