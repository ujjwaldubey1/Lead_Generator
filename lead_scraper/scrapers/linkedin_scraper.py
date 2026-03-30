"""Cookie-backed LinkedIn scraping using Playwright."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path
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
DEBUG_MODE = True
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
COOKIES_PATH = BASE_DIR / "cookies" / "linkedin_cookies.json"
DEBUG_HTML_PATH = BASE_DIR / "debug_linkedin.html"
DEBUG_SCREENSHOT_PATH = BASE_DIR / "debug_linkedin.png"
BROWSER_PROFILE_DIR = BASE_DIR / "linkedin_browser_profile"
DEBUG_SELECTORS = [
    "div[data-urn]",
    ".feed-shared-update-v2",
    ".occludable-update",
    "li.artdeco-list__item",
    '[class*="update-components"]',
    '[class*="feed-shared"]',
    "article",
    'div[class*="ember-view"]',
]


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


def _pause_after_navigation(page: Page) -> None:
    """Wait for LinkedIn navigation to settle before the next action."""

    try:
        page.wait_for_load_state("networkidle", timeout=60_000)
    except Exception:
        pass
    time.sleep(3)


def _pause_before_extraction(page: Page) -> None:
    """Give the page a final buffer before extraction starts."""

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    time.sleep(3)


def _close_browser(browser: Any) -> None:
    """Keep the browser open in debug mode so the page can be inspected."""

    if DEBUG_MODE:
        print("Browser will stay open for 60 seconds. Press Ctrl+C to close early.")
        time.sleep(60)
        input("Scraping done. Press ENTER to close the browser...")
    browser.close()


def _add_anti_detection(page: Page) -> None:
    """Inject anti-detection scripts before any LinkedIn navigation."""

    page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });

        window.chrome = {
            runtime: {}
        };

        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """
    )


def human_like_search(page: Page, keyword: str) -> str:
    """Navigate LinkedIn like a real user before landing on the posts results."""

    print("Navigating to feed...")
    page.goto("https://www.linkedin.com/feed/", timeout=60_000, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=60_000)
    time.sleep(random.uniform(3, 6))

    print(f"Typing search query: {keyword}")
    search_box = page.wait_for_selector("input[placeholder*='Search']", timeout=15_000)
    search_box.click()
    time.sleep(random.uniform(0.5, 1.5))
    search_box.fill("")

    for char in keyword:
        search_box.type(char, delay=random.randint(80, 200))

    time.sleep(random.uniform(1, 2))
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle", timeout=60_000)
    time.sleep(random.uniform(3, 5))

    print("Clicking Posts filter...")
    try:
        posts_button = page.wait_for_selector("button:has-text('Posts')", timeout=10_000)
        posts_button.click()
        page.wait_for_load_state("networkidle", timeout=60_000)
        time.sleep(random.uniform(3, 5))
    except Exception:
        print("Posts filter button not found, trying direct URL...")
        encoded = quote_plus(keyword)
        page.goto(
            f"https://www.linkedin.com/search/results/content/?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL",
            timeout=60_000,
            wait_until="domcontentloaded",
        )
        page.wait_for_load_state("networkidle", timeout=60_000)
        time.sleep(random.uniform(4, 6))

    return str(page.url)


def scroll_to_load_posts(page: Page) -> None:
    """Scroll the results page to trigger lazy-loading of post cards."""

    print("Scrolling to load posts...")
    for _ in range(5):
        page.mouse.wheel(0, random.randint(400, 700))
        time.sleep(random.uniform(1.5, 3))
    page.mouse.wheel(0, -300)
    time.sleep(2)


def _session_expired(page: Page) -> bool:
    """Detect login redirects on LinkedIn search pages."""

    current_url = page.url.lower()
    if "/login" in current_url or "checkpoint" in current_url:
        print("Session expired. Run setup_cookies.py again.")
        return True
    return False


def _debug_page_state(page: Page) -> None:
    """Capture and print LinkedIn page-debug artifacts after navigation."""

    if not DEBUG_MODE:
        return

    try:
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            page.wait_for_timeout(5_000)

        final_url = page.evaluate("window.location.href")
        page_title = page.title()
        print(f"LinkedIn debug URL: {final_url}")
        print(f"LinkedIn debug title: {page_title}")

        html = page.content()
        DEBUG_HTML_PATH.write_text(html, encoding="utf-8")
        page.screenshot(path=str(DEBUG_SCREENSHOT_PATH), full_page=True)
        print(f"Saved LinkedIn HTML to: {DEBUG_HTML_PATH}")
        print(f"Saved LinkedIn screenshot to: {DEBUG_SCREENSHOT_PATH}")

        selector_counts: list[tuple[str, int]] = []
        best_selector = ""
        best_count = -1

        for selector in DEBUG_SELECTORS:
            try:
                elements = page.query_selector_all(selector)
                count = len(elements)
                selector_counts.append((selector, count))
                print(f"LinkedIn debug selector '{selector}': {count} matches")
                if count > best_count:
                    best_selector = selector
                    best_count = count
            except Exception as exc:
                print(f"LinkedIn debug selector '{selector}' failed: {exc}")

        if best_selector and best_count > 0:
            try:
                first_el = page.query_selector_all(best_selector)[0]
                preview = first_el.inner_text().strip()[:300] if first_el else ""
            except Exception as exc:
                preview = f"[failed to read first element: {exc}]"
        else:
            preview = "[no matching elements found]"

        print("LinkedIn debug summary:")
        print(f"  Best selector: {best_selector or 'none'}")
        print(f"  Match count: {best_count if best_count >= 0 else 0}")
        print(f"  First element preview: {preview}")
    except Exception as exc:
        print(f"LinkedIn debug capture failed: {exc}")


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
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=False,
                slow_mo=50,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                    "--window-size=1280,800",
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
            )
            context.add_cookies(cookies)
            page = context.pages[0] if context.pages else context.new_page()
            time.sleep(2)
            print("Browser opened. Navigating to LinkedIn...")
            _add_anti_detection(page)
            if stealth_sync is not None:
                stealth_sync(page)

            page.goto("https://www.linkedin.com/feed/", timeout=60_000, wait_until="domcontentloaded")
            _pause_after_navigation(page)
            if _session_expired(page):
                _close_browser(context)
                return []

            for keyword in keywords:
                print(f"Scraping LinkedIn for: {keyword}")
                collected = 0
                scroll_attempts = 0

                try:
                    human_like_search(page, keyword)
                    scroll_to_load_posts(page)
                    _debug_page_state(page)
                    _pause_before_extraction(page)
                    if _session_expired(page):
                        _close_browser(context)
                        return []

                    while collected < max_per_keyword and scroll_attempts < 8:
                        posts = page.query_selector_all("div[data-urn]")
                        print(f"Found {len(posts)} post containers")
                        for post in posts:
                            try:
                                author = ""
                                author_el = post.query_selector(
                                    ".update-components-actor__name, "
                                    ".feed-shared-actor__name, "
                                    "[class*='actor__name']"
                                )
                                if author_el:
                                    author = author_el.inner_text().strip()

                                body = ""
                                body_el = post.query_selector(
                                    ".feed-shared-update-v2__description, "
                                    ".update-components-text, "
                                    "[class*='commentary'], "
                                    "[class*='description']"
                                )
                                if body_el:
                                    body = body_el.inner_text().strip()

                                profile_url = ""
                                profile_el = post.query_selector("a[href*='/in/']")
                                if profile_el:
                                    profile_url = str(profile_el.get_attribute("href") or "").strip()
                                    if profile_url and "?" in profile_url:
                                        profile_url = profile_url.split("?")[0]

                                post_url = ""
                                post_el = post.query_selector("a[href*='/posts/'], a[href*='/activity-'], a[href*='/feed/update/']")
                                if post_el:
                                    post_url = str(post_el.get_attribute("href") or "").strip()
                                    if post_url and "?" in post_url:
                                        post_url = post_url.split("?")[0]

                                urn = str(post.get_attribute("data-urn") or "").strip()
                                post_id = urn or f"li_{abs(hash((author + body)[:120]))}"
                                if post_id in seen_ids:
                                    continue

                                if not author or not body:
                                    continue

                                seen_ids.add(post_id)
                                leads.append(
                                    {
                                        "id": post_id,
                                        "title": body[:100],
                                        "body": body,
                                        "author": author,
                                        "url": post_url,
                                        "profile_url": (
                                            f"https://www.linkedin.com{profile_url}"
                                            if profile_url.startswith("/")
                                            else profile_url
                                        ),
                                        "subreddit": "",
                                        "platform": "linkedin",
                                        "created_utc": int(time.time()),
                                        "score": 0,
                                        "scraped_at": datetime.utcnow().isoformat(),
                                        "keyword_used": keyword,
                                        "outreach_type": "manual_dm",
                                    }
                                )
                                collected += 1
                                if collected >= max_per_keyword:
                                    break
                            except Exception as exc:
                                print(f"Error extracting post: {exc}")
                                continue

                        page.evaluate("window.scrollBy(0, 2000)")
                        time.sleep(2)
                        page.wait_for_timeout(random.randint(2_500, 4_000))
                        scroll_attempts += 1

                    print(f"  Collected {collected} posts for '{keyword}'")
                except Exception as exc:
                    print(f"  Error scraping LinkedIn for '{keyword}': {exc}")

                _sleep(8.0, 15.0)

            _close_browser(context)
    except Exception as exc:
        logger.error("LinkedIn scraping failed: %s", exc)
        return []

    return leads
