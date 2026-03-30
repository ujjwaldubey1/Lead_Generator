"""Backward-compatible X scraper alias with no Apify dependency."""

from __future__ import annotations

from typing import Any

try:
    from .x_scraper import scrape_x
except ImportError:  # pragma: no cover - script execution fallback.
    from x_scraper import scrape_x


Lead = dict[str, Any]


def scrape_twitter(keywords: list[str], max_per_keyword: int = 30) -> list[Lead]:
    """Compatibility wrapper that routes old Twitter calls to the X scraper."""

    return scrape_x(keywords, max_per_keyword=max_per_keyword)
