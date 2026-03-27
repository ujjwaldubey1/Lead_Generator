"""Local sync log used to prevent duplicate Airtable inserts."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from utils.logger import get_logger


SYNC_LOG_PATH = Path(__file__).resolve().parents[1] / "sync_log.json"
logger = get_logger(__name__)


def load_log() -> set[str]:
    """Load the set of already-synced lead IDs from the local JSON log."""

    if not SYNC_LOG_PATH.exists():
        return set()

    try:
        raw_data = json.loads(SYNC_LOG_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Unable to read sync log %s: %s", SYNC_LOG_PATH.name, exc)
        return set()
    except json.JSONDecodeError as exc:
        logger.warning("Sync log %s contains invalid JSON: %s", SYNC_LOG_PATH.name, exc)
        return set()

    if not isinstance(raw_data, list):
        return set()

    return {str(item).strip() for item in raw_data if str(item).strip()}


def save_log(synced_ids: set[str]) -> None:
    """Persist the updated synced lead ID set to the local JSON log."""

    try:
        SYNC_LOG_PATH.write_text(
            json.dumps(sorted(synced_ids), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Unable to write sync log %s: %s", SYNC_LOG_PATH.name, exc)


def is_duplicate(lead_id: str, log: set[str]) -> bool:
    """Return whether the given lead ID has already been synced."""

    return lead_id in log
