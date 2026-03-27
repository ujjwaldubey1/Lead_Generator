"""Lead deduplication helpers."""

from __future__ import annotations

from typing import Any

try:
    from .logger import get_logger
except ImportError:  # pragma: no cover - script execution fallback.
    from logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)


def deduplicate(leads: list[Lead]) -> list[Lead]:
    """Remove duplicate leads by id and by author-platform identity."""

    unique_leads: list[Lead] = []
    seen_ids: set[str] = set()
    seen_author_platform: set[tuple[str, str]] = set()
    duplicate_count = 0

    for lead in leads:
        lead_id = str(lead.get("id", "")).strip()
        author = str(lead.get("author", "")).strip().lower()
        platform = str(lead.get("platform", "")).strip().lower()
        author_platform_key = (author, platform)

        if lead_id and lead_id in seen_ids:
            duplicate_count += 1
            continue

        # Keeping one lead per author-platform pair prevents repeated outreach
        # to the same account on the same source.
        if author and platform and author_platform_key in seen_author_platform:
            duplicate_count += 1
            continue

        if lead_id:
            seen_ids.add(lead_id)
        if author and platform:
            seen_author_platform.add(author_platform_key)

        unique_leads.append(lead)

    print(f"Removed {duplicate_count} duplicate leads.")
    logger.info("Removed %s duplicate leads during deduplication.", duplicate_count)
    return unique_leads

