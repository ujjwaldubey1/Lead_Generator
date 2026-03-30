"""Run phase 1 scraping and save raw leads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .config import BASE_DIR, OUTPUT_FILE
    from .scrapers.email_hunter import find_email_for_lead
    from .scrapers.linkedin_scraper import scrape_linkedin
    from .scrapers.reddit_scraper import scrape_reddit
    from .scrapers.x_scraper import scrape_x
    from .utils.deduplicator import deduplicate
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR, OUTPUT_FILE
    from scrapers.email_hunter import find_email_for_lead
    from scrapers.linkedin_scraper import scrape_linkedin
    from scrapers.reddit_scraper import scrape_reddit
    from scrapers.x_scraper import scrape_x
    from utils.deduplicator import deduplicate
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
COOKIES_DIR = BASE_DIR / "cookies"
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


def enrich_social_leads(leads: list[Lead]) -> list[Lead]:
    """Attempt local email enrichment for X and LinkedIn leads."""

    enriched: list[Lead] = []
    for lead in leads:
        platform = str(lead.get("platform", "")).strip().lower()
        if platform in {"twitter", "linkedin"}:
            enriched.append(find_email_for_lead(lead))
        else:
            enriched.append(lead)
    return enriched


def main() -> dict[str, int | bool]:
    """Run phase 1 scraping and return the summary."""

    reddit_leads = scrape_reddit(SUBREDDITS, KEYWORDS)
    all_leads = list(reddit_leads)

    x_cookies = COOKIES_DIR / "x_cookies.json"
    if x_cookies.exists():
        print("Scraping X...")
        x_leads = scrape_x(KEYWORDS, max_per_keyword=30)
        print(f"X: {len(x_leads)} posts found")
        all_leads.extend(x_leads)
    else:
        print("X cookies not found - skipping. Run setup_cookies.py to enable.")

    linkedin_cookies = COOKIES_DIR / "linkedin_cookies.json"
    if linkedin_cookies.exists():
        print("Scraping LinkedIn...")
        linkedin_leads = scrape_linkedin(KEYWORDS, max_per_keyword=20)
        print(f"LinkedIn: {len(linkedin_leads)} posts found")
        all_leads.extend(linkedin_leads)
    else:
        print("LinkedIn cookies not found - skipping.")

    unique_leads = deduplicate(all_leads)
    enriched_leads = enrich_social_leads(unique_leads)
    save_raw_leads(enriched_leads, BASE_DIR / OUTPUT_FILE)

    message = (
        f"{len(all_leads)} raw posts scraped, "
        f"{len(enriched_leads)} unique leads saved to {OUTPUT_FILE}"
    )
    print(message)
    logger.info(message)
    return {"ok": True, "raw": len(all_leads), "unique": len(enriched_leads)}


if __name__ == "__main__":
    main()
