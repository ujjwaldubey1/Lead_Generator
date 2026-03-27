"""Run all four pipeline phases sequentially."""

from __future__ import annotations

import time
from typing import Any, Callable

try:
    from .run_database import main as run_database_main
    from .run_filter import main as run_filter_main
    from .run_outreach import main as run_outreach_main
    from .run_scraper import main as run_scraper_main
except ImportError:  # pragma: no cover - direct script execution fallback.
    from run_database import main as run_database_main
    from run_filter import main as run_filter_main
    from run_outreach import main as run_outreach_main
    from run_scraper import main as run_scraper_main


def _format_result(summary: dict[str, Any]) -> str:
    """Convert a summary dictionary into a compact one-line result."""

    return ", ".join(f"{key}={value}" for key, value in summary.items() if key != "ok")


def main() -> None:
    """Run the entire lead generation pipeline."""

    phases: list[tuple[int, str, Callable[..., dict[str, Any]]]] = [
        (1, "scraping", run_scraper_main),
        (2, "qualification", run_filter_main),
        (3, "database sync", run_database_main),
        (4, "outreach", run_outreach_main),
    ]

    pipeline_start = time.perf_counter()

    for number, name, func in phases:
        print(f"--- Running Phase {number}: {name} ---")
        start = time.perf_counter()

        try:
            summary = func(exit_on_error=False) if number in {2, 3, 4} else func()
        except Exception as exc:
            print(f"Phase {number} failed completely: {exc}")
            return

        duration = round(time.perf_counter() - start, 2)
        if not summary.get("ok", True):
            print(f"Phase {number} failed completely. Result: {_format_result(summary)}")
            return

        print(f"Phase {number} complete in {duration}s. Result: {_format_result(summary)}")

    total_duration = round(time.perf_counter() - pipeline_start, 2)
    print(f"Total pipeline time: {total_duration}s")


if __name__ == "__main__":
    main()

