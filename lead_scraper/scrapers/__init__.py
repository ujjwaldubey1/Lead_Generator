"""Scraper exports for the lead scraper."""

from .apify_scraper import scrape_twitter
from .reddit_scraper import scrape_reddit

__all__ = ["scrape_reddit", "scrape_twitter"]

