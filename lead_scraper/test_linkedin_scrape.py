"""Quick verification script for LinkedIn cookie-backed scraping."""

from __future__ import annotations

from pprint import pprint

from scrapers.linkedin_scraper import scrape_linkedin


def main() -> None:
    """Scrape a few LinkedIn posts to verify that the saved session works."""

    queries = ["need automation help", "automation", "ai tools"]
    for query in queries:
        leads = scrape_linkedin([query], max_per_keyword=3)
        print(f"Query: {query} | Leads found: {len(leads)}")
        if leads:
            pprint(leads[0])
            break
    print("LinkedIn verification complete.")


if __name__ == "__main__":
    main()
