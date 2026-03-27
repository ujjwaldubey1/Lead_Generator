"""Run phase 3 and push qualified leads into Airtable."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False

try:
    from .config import BASE_DIR, QUALIFIED_OUTPUT_FILE
    from .database.airtable_client import push_all_leads
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR, QUALIFIED_OUTPUT_FILE
    from database.airtable_client import push_all_leads
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
INPUT_FILE = QUALIFIED_OUTPUT_FILE


def load_qualified_leads(input_path: Path) -> list[Lead]:
    """Load qualified leads from disk, returning an empty list when unavailable."""

    if not input_path.exists():
        raise FileNotFoundError(f"Input file missing: {INPUT_FILE}. Nothing to sync.")

    try:
        raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Input file is invalid JSON: {INPUT_FILE}. Nothing to sync.")
        logger.warning("Input file %s contains invalid JSON: %s", input_path.name, exc)
        return []
    except OSError as exc:
        print(f"Unable to read {INPUT_FILE}. Nothing to sync.")
        logger.warning("Unable to read input file %s: %s", input_path.name, exc)
        return []

    if not raw_data:
        print(f"Input file is empty: {INPUT_FILE}. Nothing to sync.")
        logger.info("Input file %s is empty.", input_path.name)
        return []

    if not isinstance(raw_data, list):
        print(f"Input file must contain a JSON array: {INPUT_FILE}. Nothing to sync.")
        logger.warning("Input file %s must contain a JSON array.", input_path.name)
        return []

    return [item for item in raw_data if isinstance(item, dict)]


def _load_env() -> tuple[str, str, str]:
    """Load Airtable credentials and table config from the project .env file."""

    load_dotenv(BASE_DIR / ".env")
    return (
        os.getenv("AIRTABLE_API_KEY", "").strip(),
        os.getenv("AIRTABLE_BASE_ID", "").strip(),
        os.getenv("AIRTABLE_TABLE_NAME", "").strip(),
    )


def main(exit_on_error: bool = True) -> dict[str, Any]:
    """Load qualified leads and sync them into Airtable."""

    try:
        leads = load_qualified_leads(BASE_DIR / INPUT_FILE)
    except FileNotFoundError as exc:
        print(str(exc))
        logger.warning(str(exc))
        if exit_on_error:
            sys.exit(1)
        return {"ok": False, "pushed": 0, "skipped": 0, "failed": 0, "message": str(exc)}

    if not leads:
        return {"ok": True, "pushed": 0, "skipped": 0, "failed": 0, "message": "No qualified leads to sync."}

    api_key, base_id, table_name = _load_env()
    summary = push_all_leads(leads, api_key=api_key, base_id=base_id, table_name=table_name)
    ok = not (leads and summary["pushed"] == 0 and summary["skipped"] == 0 and summary["failed"] > 0)

    print("Database sync complete.")
    print(f"Pushed:  {summary['pushed']} new leads")
    print(f"Skipped: {summary['skipped']} duplicates")
    print(f"Failed:  {summary['failed']} (will retry on next run)")

    if summary["failed"] > 0:
        if exit_on_error:
            sys.exit(1)

    message = (
        f"Pushed={summary['pushed']}, Skipped={summary['skipped']}, Failed={summary['failed']}"
    )
    return {"ok": ok, **summary, "message": message}


if __name__ == "__main__":
    main()
