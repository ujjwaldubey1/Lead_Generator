"""Run phase 4 outreach against new Airtable leads."""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False

try:
    from pyairtable import Api
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    Api = None  # type: ignore[assignment]

try:
    from .config import BASE_DIR
    from .outreach.email_writer import generate_email
    from .outreach.instantly_client import add_lead_to_campaign
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR
    from outreach.email_writer import generate_email
    from outreach.instantly_client import add_lead_to_campaign
    from utils.logger import get_logger


logger = get_logger(__name__)
MANUAL_DM_STATUS = "Manual DM"


def _load_env() -> dict[str, str]:
    """Load outreach configuration from the project .env file."""

    load_dotenv(BASE_DIR / ".env")
    return {
        "airtable_api_key": os.getenv("AIRTABLE_API_KEY", "").strip(),
        "airtable_base_id": os.getenv("AIRTABLE_BASE_ID", "").strip(),
        "airtable_table_name": os.getenv("AIRTABLE_TABLE_NAME", "Leads").strip(),
        "instantly_api_key": os.getenv("INSTANTLY_API_KEY", "").strip(),
        "instantly_campaign_id": os.getenv("INSTANTLY_CAMPAIGN_ID", "").strip(),
        "service_description": os.getenv("SERVICE_DESCRIPTION", "").strip(),
        "sender_name": os.getenv("SENDER_NAME", "").strip(),
        "sender_company": os.getenv("SENDER_COMPANY", "").strip(),
        "calendar_link": os.getenv("CALENDAR_LINK", "").strip(),
    }


def _first_name(handle: str) -> str:
    """Extract a simple first-name-like token from a handle."""

    cleaned = handle.strip().lstrip("@").replace("_", " ").replace(".", " ").replace("-", " ")
    return (cleaned.split() or ["there"])[0].capitalize()


def _update_record(table: Any, record_id: str, fields: dict[str, Any]) -> bool:
    """Update a single Airtable record."""

    try:
        table.update(record_id, fields)
        return True
    except Exception as exc:
        logger.error("Airtable update failed for record=%s: %s", record_id, exc)
        return False


def _manual_dm_note(fields: dict[str, Any], platform: str, handle: str) -> str:
    """Build the note text for leads that should be handled via manual social DM."""

    post_url = str(fields.get("Post URL", "")).strip()
    pain_point = str(fields.get("Pain point", "")).strip()
    existing_notes = str(fields.get("Notes", "")).strip()
    base_note = (
        f"No email found - DM via {platform or 'unknown'}. "
        f"Handle: {handle or 'unknown'} | "
        f"Post URL: {post_url or 'n/a'} | "
        f"Pain point: {pain_point or 'n/a'}"
    )
    return f"{base_note} | {existing_notes}" if existing_notes else base_note


def _email_settings_ready(config: dict[str, str]) -> bool:
    """Return whether the cold-email path has the required configuration."""

    return all(
        (
            config["instantly_api_key"],
            config["instantly_campaign_id"],
            config["service_description"],
            config["sender_name"],
            config["sender_company"],
            config["calendar_link"],
        )
    )


def _should_use_manual_dm(fields: dict[str, Any], platform: str) -> bool:
    """Decide whether a record should stay in the manual-DM queue."""

    email = str(fields.get("Email", "")).strip()
    outreach_type = str(fields.get("Outreach type", "")).strip().lower()
    return platform == "reddit" or not email or outreach_type == "manual dm"


def _mark_manual_dm(table: Any, record_id: str, fields: dict[str, Any], platform: str, handle: str) -> bool:
    """Update a record to the manual-DM queue with a human-friendly note."""

    return _update_record(
        table,
        record_id,
        {
            "Status": MANUAL_DM_STATUS,
            "Notes": _manual_dm_note(fields, platform, handle),
        },
    )


def main(exit_on_error: bool = True) -> dict[str, Any]:
    """Run outreach for Airtable leads that are either new or need retrying."""

    config = _load_env()
    if Api is None:
        print("pyairtable is not installed. Outreach cannot run.")
        if exit_on_error:
            sys.exit(1)
        return {
            "ok": False,
            "found": 0,
            "queued": 0,
            "no_email": 0,
            "errors": 0,
            "message": "pyairtable is not installed.",
        }

    required_values = (
        config["airtable_api_key"],
        config["airtable_base_id"],
        config["airtable_table_name"],
    )
    if not all(required_values):
        print("Outreach configuration is incomplete. Check your .env file.")
        if exit_on_error:
            sys.exit(1)
        return {
            "ok": False,
            "found": 0,
            "queued": 0,
            "no_email": 0,
            "errors": 0,
            "message": "Outreach configuration is incomplete.",
        }

    try:
        table = Api(config["airtable_api_key"]).table(
            config["airtable_base_id"],
            config["airtable_table_name"],
        )
        records = table.all(formula="OR({Status}='New', {Status}='No email')")
    except Exception as exc:
        print(f"Failed to load Airtable leads: {exc}")
        if exit_on_error:
            sys.exit(1)
        return {
            "ok": False,
            "found": 0,
            "queued": 0,
            "no_email": 0,
            "errors": 0,
            "message": str(exc),
        }

    summary = {"ok": True, "found": 0, "queued": 0, "no_email": 0, "manual_dm": 0, "errors": 0}

    for record in records:
        record_id = str(record.get("id", "")).strip()
        fields = record.get("fields", {})
        handle = str(fields.get("Handle", "")).strip()
        platform = str(fields.get("Platform", "")).strip().lower()

        if _should_use_manual_dm(fields, platform):
            _mark_manual_dm(table, record_id, fields, platform, handle)
            summary["manual_dm"] += 1
            time.sleep(1)
            continue

        if not _email_settings_ready(config):
            logger.error("Cold-email configuration missing for record=%s platform=%s", record_id, platform)
            summary["errors"] += 1
            time.sleep(1)
            continue

        email = str(fields.get("Email", "")).strip()
        summary["found"] += 1

        lead = {
            "id": record_id,
            "author": handle,
            "platform": platform,
            "pain_point": str(fields.get("Pain point", "")).strip(),
            "title": str(fields.get("Post title", "")).strip(),
            "url": str(fields.get("Post URL", "")).strip(),
            "ai_score": fields.get("AI score", 0),
        }
        email_copy = generate_email(
            lead=lead,
            service_description=config["service_description"],
            sender_name=config["sender_name"],
            sender_company=config["sender_company"],
            calendar_link=config["calendar_link"],
        )
        if email_copy is None:
            summary["errors"] += 1
            time.sleep(1)
            continue

        queued = add_lead_to_campaign(
            email=email,
            first_name=_first_name(handle),
            custom_vars={
                "pain_point": lead["pain_point"],
                "ai_score": lead["ai_score"],
                "platform": lead["platform"],
                "post_url": lead["url"],
                "subject": email_copy["subject"],
                "body": email_copy["body"],
            },
            campaign_id=config["instantly_campaign_id"],
            api_key=config["instantly_api_key"],
        )
        if not queued:
            summary["errors"] += 1
            time.sleep(1)
            continue

        summary["queued"] += 1
        _update_record(
            table,
            record_id,
            {
                "Status": "Contacted",
                "Notes": f"Subject: {email_copy['subject']} | Queued: {date.today().isoformat()}",
            },
        )
        time.sleep(1)

    print(
        f"found {summary['found']} emails, queued {summary['queued']}, "
        f"manual dm {summary['manual_dm']}, no email {summary['no_email']}, errors {summary['errors']}"
    )
    summary["message"] = (
        f"found={summary['found']}, queued={summary['queued']}, "
        f"manual_dm={summary['manual_dm']}, no_email={summary['no_email']}, errors={summary['errors']}"
    )
    return summary


if __name__ == "__main__":
    main()
