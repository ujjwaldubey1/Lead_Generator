"""Run phase 1 scraping and save raw leads."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .config import BASE_DIR, OUTPUT_FILE
    from .keywords_config import LINKEDIN_KEYWORDS
    from .scrapers.email_hunter import find_email_for_lead
    from .scrapers.linkedin_scraper import scrape_linkedin
    from .scrapers.reddit_scraper import scrape_reddit
    from .scrapers.x_scraper import scrape_x
    from .utils.deduplicator import deduplicate
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR, OUTPUT_FILE
    from keywords_config import LINKEDIN_KEYWORDS
    from scrapers.email_hunter import find_email_for_lead
    from scrapers.linkedin_scraper import scrape_linkedin
    from scrapers.reddit_scraper import scrape_reddit
    from scrapers.x_scraper import scrape_x
    from utils.deduplicator import deduplicate
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
COOKIES_DIR = BASE_DIR / "cookies"
LEADS_OUTPUT_FILE = "leads_output.json"
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


def save_leads_to_json(new_leads: list[Lead], filepath: str = LEADS_OUTPUT_FILE) -> int:
    """Merge newly scraped leads into a local JSON array, deduplicated by id."""

    output_path = BASE_DIR / filepath
    existing_leads: list[Lead] = []

    if output_path.exists():
        try:
            raw_data = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(raw_data, list):
                existing_leads = [item for item in raw_data if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load existing lead output file %s: %s", output_path.name, exc)

    existing_ids = {
        str(lead.get("id", "")).strip()
        for lead in existing_leads
        if str(lead.get("id", "")).strip()
    }
    saved_count = 0

    for lead in new_leads:
        lead_id = str(lead.get("id", "")).strip()
        if not lead_id or lead_id in existing_ids:
            continue

        enriched_lead = dict(lead)
        enriched_lead.setdefault("scraped_at", datetime.utcnow().isoformat())
        enriched_lead.setdefault("keyword_used", "")
        existing_leads.append(enriched_lead)
        existing_ids.add(lead_id)
        saved_count += 1

    output_path.write_text(json.dumps(existing_leads, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {saved_count} new leads. Total leads in file: {len(existing_leads)}")
    return saved_count


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
    linkedin_leads: list[Lead] = []
    linkedin_saved_count = 0
    if linkedin_cookies.exists():
        print("Scraping LinkedIn...")
        linkedin_leads = scrape_linkedin(LINKEDIN_KEYWORDS, max_per_keyword=20)
        print(f"LinkedIn: {len(linkedin_leads)} posts found")
        all_leads.extend(linkedin_leads)
        total_keywords = len(LINKEDIN_KEYWORDS)
        total_leads = len(linkedin_leads)
        new_leads_saved = save_leads_to_json(linkedin_leads)
        linkedin_saved_count = new_leads_saved
        print(f"\n{'='*50}")
        print("Run complete.")
        print(f"Keywords searched : {total_keywords}")
        print(f"Total leads found : {total_leads}")
        print(f"New leads saved   : {new_leads_saved}")
        print(f"Output file       : {LEADS_OUTPUT_FILE}")
        print(f"{'='*50}")
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
