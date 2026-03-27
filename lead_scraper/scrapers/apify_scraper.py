"""Apify-powered scrapers for social lead sources."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

try:
    from ..config import APIFY_TOKEN, SCRAPE_DELAY
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - script execution fallback.
    from config import APIFY_TOKEN, SCRAPE_DELAY
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
TWITTER_ACTOR_ID = "apidojo/tweet-scraper"


def _to_unix_timestamp(date_value: str | None) -> int:
    """Convert an ISO-like timestamp string into a Unix timestamp."""

    if not date_value:
        return 0

    normalized = date_value.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0


def _build_title(text: str, max_length: int = 120) -> str:
    """Create a compact title from tweet text."""

    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3].rstrip()}..."


def _extract_author(item: dict[str, Any]) -> str:
    """Extract the best available author handle or display name."""

    user = item.get("author") or item.get("user") or {}
    if isinstance(user, dict):
        for field in ("userName", "screen_name", "screenName", "username", "name"):
            value = str(user.get(field, "")).strip()
            if value:
                return value

    for field in ("authorUsername", "username", "userName"):
        value = str(item.get(field, "")).strip()
        if value:
            return value

    return ""


def _normalize_tweet(item: dict[str, Any]) -> Lead:
    """Map an Apify tweet result into the shared lead schema."""

    body = str(item.get("text", "") or item.get("fullText", "")).strip()
    author = _extract_author(item)
    tweet_id = str(item.get("id", "") or item.get("tweetId", "")).strip()
    url = str(item.get("url", "")).strip()
    if not url and author and tweet_id:
        url = f"https://twitter.com/{author}/status/{tweet_id}"

    return {
        "id": tweet_id,
        "title": _build_title(body),
        "body": body,
        "author": author,
        "url": url,
        "subreddit": "",
        "platform": "twitter",
        "created_utc": _to_unix_timestamp(str(item.get("createdAt", "")).strip() or None),
        "score": int(item.get("likeCount", 0) or 0),
    }


def scrape_twitter(keywords: list[str]) -> list[Lead]:
    """Scrape recent tweets for the supplied keywords via Apify."""

    if not APIFY_TOKEN:
        logger.warning("APIFY_TOKEN is not configured; skipping Twitter scraping.")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client is not installed; skipping Twitter scraping.")
        return []

    client = ApifyClient(APIFY_TOKEN)
    leads: list[Lead] = []

    for keyword in keywords:
        run_input = {
            "queries": [keyword],
            "maxItems": 50,
            "queryType": "Latest",
        }

        try:
            run = client.actor(TWITTER_ACTOR_ID).call(run_input=run_input)
            dataset = client.dataset(run["defaultDatasetId"])
            items = dataset.list_items().items

            for item in items:
                lead = _normalize_tweet(item)
                if lead["id"] and lead["author"]:
                    leads.append(lead)
        except Exception as exc:  # pragma: no cover - depends on external API/runtime.
            logger.error("Apify Twitter scrape failed for keyword '%s': %s", keyword, exc)
        finally:
            time.sleep(SCRAPE_DELAY)

    logger.info("Collected %s Twitter posts before deduplication.", len(leads))
    return leads
