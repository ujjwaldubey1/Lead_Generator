"""Compatibility entry point for phase 1 scraping."""

from __future__ import annotations

try:
    from .run_scraper import main as run_scraper_main
except ImportError:  # pragma: no cover - direct script execution fallback.
    from run_scraper import main as run_scraper_main


def main() -> None:
    """Run phase 1 scraping."""

    run_scraper_main()


if __name__ == "__main__":
    main()
