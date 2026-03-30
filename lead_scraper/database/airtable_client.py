"""Airtable synchronization client for qualified leads."""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Callable

import requests

try:
    from pyairtable import Api
    from pyairtable.exceptions import PyAirtableError
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    Api = None  # type: ignore[assignment]
    PyAirtableError = Exception  # type: ignore[assignment]

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except ImportError:  # pragma: no cover - fallback keeps module importable.
    retry = None  # type: ignore[assignment]
    retry_if_exception_type = None  # type: ignore[assignment]
    stop_after_attempt = None  # type: ignore[assignment]
    wait_exponential = None  # type: ignore[assignment]

try:
    from ..utils.logger import get_logger
    from .sync_log import is_duplicate, load_log, save_log
except ImportError:  # pragma: no cover - direct script execution fallback.
    from utils.logger import get_logger
    from database.sync_log import is_duplicate, load_log, save_log


Lead = dict[str, Any]
Record = dict[str, Any]
logger = get_logger(__name__)
META_TABLES_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables"


def _get_retry_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return the configured tenacity retry decorator or a no-op fallback."""

    if retry is None:
        def passthrough(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return passthrough

    return retry(
        wait=wait_exponential(min=2, max=60),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type((PyAirtableError,)),
        reraise=False,
        retry_error_callback=lambda _state: None,
    )


def _safe_int(value: Any) -> int:
    """Convert a numeric-like value to an integer without raising."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _source_post_date(created_utc: Any) -> str:
    """Convert a Unix timestamp into an ISO date string."""

    try:
        return datetime.fromtimestamp(float(created_utc), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _platform_label(value: str) -> str:
    """Convert platform names to Airtable single-select labels."""

    normalized = value.strip().lower()
    mapping = {
        "reddit": "Reddit",
        "twitter": "Twitter",
        "linkedin": "LinkedIn",
    }
    return mapping.get(normalized, normalized.capitalize() if normalized else "")


def build_record(lead: Lead) -> Record:
    """Map a qualified lead into the Airtable schema."""

    platform = _platform_label(str(lead.get("platform", "")))
    buying_intent = str(lead.get("buying_intent", "")).strip().capitalize()

    return {
        "Handle": str(lead.get("author", "")).strip(),
        "Platform": platform,
        "Post URL": str(lead.get("url", "")).strip(),
        "Pain point": str(lead.get("pain_point", "")).strip(),
        "AI score": _safe_int(lead.get("ai_score", 0)),
        "Buying intent": buying_intent if buying_intent else "None",
        "Post title": str(lead.get("title", "")).strip(),
        "Subreddit": str(lead.get("subreddit", "")).strip() if platform == "Reddit" else "",
        "Outreach type": str(lead.get("outreach_type", "manual_dm")).replace("_", " ").title(),
        "Status": "New",
        "Email": str(lead.get("email", "")).strip(),
        "Notes": str(lead.get("notes", "")).strip(),
        "Date scraped": date.today().isoformat(),
        "Source post date": _source_post_date(lead.get("created_utc")),
    }


def get_existing_field_names(api_key: str, base_id: str, table_name: str) -> set[str] | None:
    """Load the current Airtable field names for the target table via the Meta API."""

    headers = {"Authorization": f"Bearer {api_key}"}
    url = META_TABLES_URL.format(base_id=base_id)

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        tables = response.json().get("tables", [])
    except requests.RequestException as exc:
        logger.error("Failed to read Airtable schema for table %s: %s", table_name, exc)
        return None
    except (TypeError, ValueError, KeyError) as exc:
        logger.error("Failed to parse Airtable schema for table %s: %s", table_name, exc)
        return None

    for table in tables:
        if table.get("name") == table_name:
            return {
                str(field.get("name", "")).strip()
                for field in table.get("fields", [])
                if field.get("name")
            }
    return None


@_get_retry_decorator()
def push_lead(record: Record, table: Any) -> str | None:
    """Create a new Airtable record and return its Airtable record ID."""

    try:
        response = table.create(record)
    except PyAirtableError as exc:
        logger.error("Airtable create failed: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected Airtable error: %s", exc)
        return None

    return str(response.get("id", "")).strip() or None


def push_all_leads(leads: list[Lead], api_key: str, base_id: str, table_name: str) -> dict[str, int]:
    """Push all qualified leads into Airtable with local deduplication."""

    summary = {"pushed": 0, "skipped": 0, "failed": 0}

    if not leads:
        logger.info("No qualified leads supplied for Airtable sync.")
        return summary

    if not api_key.strip() or not base_id.strip() or not table_name.strip():
        logger.warning("Airtable credentials or table configuration are missing.")
        summary["failed"] = len(leads)
        return summary

    if Api is None:
        logger.warning("pyairtable is not installed; cannot sync to Airtable.")
        summary["failed"] = len(leads)
        return summary

    try:
        table = Api(api_key).table(base_id, table_name)
    except Exception as exc:
        logger.error("Failed to initialize Airtable client: %s", exc)
        summary["failed"] = len(leads)
        return summary

    existing_fields = get_existing_field_names(api_key, base_id, table_name)
    required_fields = set(build_record(leads[0]).keys())
    if existing_fields is None:
        logger.error("Unable to verify Airtable schema before syncing leads.")
        summary["failed"] = len(leads)
        return summary

    missing_fields = sorted(required_fields - existing_fields)
    if missing_fields:
        logger.error(
            "Airtable table '%s' is missing required fields: %s",
            table_name,
            ", ".join(missing_fields),
        )
        print("Database sync aborted.")
        print(f"Missing Airtable fields: {', '.join(missing_fields)}")
        print("Create these columns in Airtable first, then rerun python run_database.py.")
        summary["failed"] = len(leads)
        return summary

    synced_ids = load_log()

    for lead in leads:
        lead_id = str(lead.get("id", "")).strip()
        author = str(lead.get("author", "")).strip() or "unknown"
        platform = str(lead.get("platform", "")).strip() or "unknown"

        if not lead_id:
            logger.warning("Skipping lead with missing id for author=%s platform=%s", author, platform)
            summary["failed"] += 1
            continue

        if is_duplicate(lead_id, synced_ids):
            logger.info("Skipping %s - already in Airtable", lead_id)
            summary["skipped"] += 1
            continue

        record = build_record(lead)
        record_id = push_lead(record, table)

        if record_id:
            synced_ids.add(lead_id)
            summary["pushed"] += 1
            print(f"Pushed: {author} ({platform})")
        else:
            summary["failed"] += 1
            print(f"Failed: {lead_id}")

        time.sleep(0.3)

    save_log(synced_ids)
    return summary
