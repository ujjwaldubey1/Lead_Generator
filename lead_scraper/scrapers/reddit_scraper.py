"""Reddit scraping utilities built on the public JSON API."""

from __future__ import annotations

import random
import time
from typing import Any

try:
    from ..config import REDDIT_USER_AGENT, REQUEST_TIMEOUT, SCRAPE_DELAY
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - script execution fallback.
    from config import REDDIT_USER_AGENT, REQUEST_TIMEOUT, SCRAPE_DELAY
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
REDDIT_SEARCH_URL = "https://www.reddit.com/r/{subreddit}/search.json"
SKIPPED_AUTHORS = {"AutoModerator", "[deleted]"}


def _normalize_post(post: dict[str, Any]) -> Lead:
    """Map a Reddit post payload into the shared lead schema."""

    permalink = post.get("permalink", "")
    return {
        "id": str(post.get("id", "")).strip(),
        "title": str(post.get("title", "")).strip(),
        "body": str(post.get("selftext", "")).strip(),
        "author": str(post.get("author", "")).strip(),
        "url": f"https://reddit.com{permalink}" if permalink else str(post.get("url", "")).strip(),
        "subreddit": str(post.get("subreddit", "")).strip(),
        "platform": "reddit",
        "created_utc": int(post.get("created_utc", 0) or 0),
        "score": int(post.get("score", 0) or 0),
    }


def _is_valid_post(lead: Lead) -> bool:
    """Return whether the normalized lead should be kept."""

    author = str(lead.get("author", "")).strip()
    title = str(lead.get("title", "")).strip()
    body = str(lead.get("body", "")).strip()

    if author in SKIPPED_AUTHORS:
        return False

    if not body and len(title) < 10:
        return False

    return True


def _request_with_backoff(
    session: Any,
    request_url: str,
    headers: dict[str, str],
    params: dict[str, str | int],
    subreddit: str,
    keyword: str,
) -> Any | None:
    """Issue a Reddit request with limited retry and 429 backoff handling."""

    backoff_seconds = max(float(SCRAPE_DELAY), 4.0)

    for attempt in range(3):
        try:
            response = session.get(
                request_url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 429:
                retry_after_raw = str(response.headers.get("Retry-After", "")).strip()
                retry_after = float(retry_after_raw) if retry_after_raw else 0.0
                wait_seconds = max(backoff_seconds, retry_after) + random.uniform(1.0, 3.0)
                logger.warning(
                    "Reddit rate limited for r/%s keyword '%s'. Waiting %.1fs before retry %s.",
                    subreddit,
                    keyword,
                    wait_seconds,
                    attempt + 1,
                )
                time.sleep(wait_seconds)
                backoff_seconds = min(backoff_seconds * 2, 60.0)
                continue

            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if getattr(exc.response, "status_code", None) == 429 and attempt < 2:
                wait_seconds = backoff_seconds + random.uniform(1.0, 3.0)
                logger.warning(
                    "Reddit 429 for r/%s keyword '%s'. Waiting %.1fs before retry %s.",
                    subreddit,
                    keyword,
                    wait_seconds,
                    attempt + 1,
                )
                time.sleep(wait_seconds)
                backoff_seconds = min(backoff_seconds * 2, 60.0)
                continue
            raise

    return None


def scrape_reddit(subreddits: list[str], keywords: list[str]) -> list[Lead]:
    """Scrape matching Reddit posts from the public search JSON endpoint."""

    try:
        import requests
    except ImportError:
        logger.warning("requests is not installed; skipping Reddit scraping.")
        return []

    headers = {"User-Agent": REDDIT_USER_AGENT, "Accept": "application/json"}
    leads: list[Lead] = []
    seen_ids: set[str] = set()
    session = requests.Session()

    for subreddit in subreddits:
        for keyword in keywords:
            request_url = REDDIT_SEARCH_URL.format(subreddit=subreddit)
            params = {
                "q": keyword,
                "sort": "new",
                "limit": 25,
                "t": "week",
                "restrict_sr": "on",
            }

            try:
                response = _request_with_backoff(
                    session,
                    request_url,
                    headers,
                    params,
                    subreddit,
                    keyword,
                )
                if response is None:
                    continue
                response.raise_for_status()
                payload = response.json()
                children = payload.get("data", {}).get("children", [])

                for item in children:
                    post = item.get("data", {})
                    lead = _normalize_post(post)
                    lead_id = str(lead.get("id", "")).strip()
                    if lead_id and lead_id in seen_ids:
                        continue
                    if _is_valid_post(lead):
                        if lead_id:
                            seen_ids.add(lead_id)
                        leads.append(lead)
            except requests.RequestException as exc:
                logger.error(
                    "Reddit request failed for r/%s with keyword '%s': %s",
                    subreddit,
                    keyword,
                    exc,
                )
            except ValueError as exc:
                logger.error(
                    "Failed to decode Reddit JSON for r/%s with keyword '%s': %s",
                    subreddit,
                    keyword,
                    exc,
                )
            finally:
                time.sleep(SCRAPE_DELAY + random.uniform(1.0, 2.5))

    logger.info("Collected %s Reddit posts before deduplication.", len(leads))
    return leads
