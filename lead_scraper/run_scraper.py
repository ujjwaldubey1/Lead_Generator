"""Run phase 1 scraping and save raw leads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .config import APIFY_TOKEN, BASE_DIR, OUTPUT_FILE
    from .scrapers.apify_scraper import scrape_twitter
    from .scrapers.reddit_scraper import scrape_reddit
    from .utils.deduplicator import deduplicate
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import APIFY_TOKEN, BASE_DIR, OUTPUT_FILE
    from scrapers.apify_scraper import scrape_twitter
    from scrapers.reddit_scraper import scrape_reddit
    from utils.deduplicator import deduplicate
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
SUBREDDITS = [
    "entrepreneur",
    "smallbusiness",
    "startups",
    "digitalnomad",
    "ecommerce",
    "SaaS",
    "artificial",
    "automation",
    "nocode",
]
KEYWORDS = [
    "need automation help",
    "looking for AI tools",
    "automate my business",
    "repetitive tasks taking too long",
    "need a chatbot",
    "looking for developer",
    "workflow automation",
    "save time on manual work",
    "need help with lead follow up",
    "anyone recommend automation tool",
]


def save_raw_leads(leads: list[Lead], output_path: Path) -> None:
    """Save raw leads to disk."""

    output_path.write_text(json.dumps(leads, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> dict[str, int | bool]:
    """Run phase 1 scraping and return the summary."""

    reddit_leads = scrape_reddit(SUBREDDITS, KEYWORDS)
    twitter_leads = scrape_twitter(KEYWORDS) if APIFY_TOKEN else []

    raw_leads = reddit_leads + twitter_leads
    unique_leads = deduplicate(raw_leads)
    save_raw_leads(unique_leads, BASE_DIR / OUTPUT_FILE)

    message = f"{len(raw_leads)} raw posts scraped, {len(unique_leads)} unique leads saved to {OUTPUT_FILE}"
    print(message)
    logger.info(message)
    return {"ok": True, "raw": len(raw_leads), "unique": len(unique_leads)}


if __name__ == "__main__":
    main()

