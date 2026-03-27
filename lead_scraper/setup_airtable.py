"""Set up the Airtable Leads table schema automatically."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads")
META_TABLES_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables"
META_FIELDS_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields"
REQUEST_TIMEOUT = 30

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

FIELDS_TO_CREATE: list[dict[str, Any]] = [
    {"name": "Handle", "type": "singleLineText"},
    {
        "name": "Platform",
        "type": "singleSelect",
        "options": {
            "choices": [{"name": "Reddit"}, {"name": "Twitter"}, {"name": "LinkedIn"}],
        },
    },
    {"name": "Post URL", "type": "url"},
    {"name": "Pain point", "type": "multilineText"},
    {"name": "AI score", "type": "number", "options": {"precision": 0}},
    {
        "name": "Buying intent",
        "type": "singleSelect",
        "options": {
            "choices": [{"name": "High"}, {"name": "Medium"}, {"name": "Low"}, {"name": "None"}],
        },
    },
    {"name": "Post title", "type": "singleLineText"},
    {"name": "Subreddit", "type": "singleLineText"},
    {
        "name": "Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "New"},
                {"name": "Reviewed"},
                {"name": "Contacted"},
                {"name": "Replied"},
                {"name": "No email"},
                {"name": "Closed"},
            ],
        },
    },
    {"name": "Email", "type": "email"},
    {"name": "Notes", "type": "multilineText"},
    {"name": "Date scraped", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    {"name": "Source post date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
]


def _permission_help_message() -> str:
    """Return the remediation text for Airtable schema permission failures."""

    return (
        "Airtable schema write permission is missing.\n"
        "Required fix:\n"
        "  1. Edit your Personal Access Token in Airtable.\n"
        "  2. Add scopes: schema.bases:read and schema.bases:write.\n"
        "  3. Add this base as an allowed resource.\n"
        "  4. Make sure the Airtable user behind the token is a Creator on the base.\n"
        "Then rerun: python setup_airtable.py"
    )


def get_table_id(base_id: str, table_name: str) -> str | None:
    """Get the table ID for a given table name."""

    url = META_TABLES_URL.format(base_id=base_id)
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        tables = response.json().get("tables", [])
    except requests.RequestException as exc:
        print(f"ERROR: Failed to load Airtable tables: {exc}")
        return None
    except (TypeError, ValueError, KeyError) as exc:
        print(f"ERROR: Failed to parse Airtable table metadata: {exc}")
        return None

    for table in tables:
        if table.get("name") == table_name:
            return str(table.get("id", "")).strip() or None
    return None


def get_existing_fields(base_id: str, table_id: str) -> set[str]:
    """Get names of fields that already exist in the table."""

    url = META_TABLES_URL.format(base_id=base_id)
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        tables = response.json().get("tables", [])
    except requests.RequestException as exc:
        print(f"ERROR: Failed to load existing Airtable fields: {exc}")
        return set()
    except (TypeError, ValueError, KeyError) as exc:
        print(f"ERROR: Failed to parse Airtable field metadata: {exc}")
        return set()

    for table in tables:
        if table.get("id") == table_id:
            return {str(field.get("name", "")).strip() for field in table.get("fields", []) if field.get("name")}
    return set()


def create_field(base_id: str, table_id: str, field: dict[str, Any]) -> tuple[bool, str | None]:
    """Create a single field in the table."""

    url = META_FIELDS_URL.format(base_id=base_id, table_id=table_id)
    try:
        response = requests.post(url, headers=HEADERS, json=field, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  Failed:  {field['name']} - {exc}")
        return False, None

    if response.status_code in {200, 201}:
        print(f"  Created: {field['name']} ({field['type']})")
        return True, None

    error_text = response.text[:100]
    error_type = None
    try:
        error_json = response.json()
        error_text = json.dumps(error_json)[:100]
        error_type = str(error_json.get("error", {}).get("type", "")).strip() or None
    except (TypeError, ValueError):
        pass
    print(f"  Failed:  {field['name']} - {error_text}")
    return False, error_type


def main() -> None:
    """Create any missing Airtable fields required by the pipeline."""

    if not API_KEY or not BASE_ID:
        print("ERROR: AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env")
        return

    print(f"Connecting to Airtable base: {BASE_ID}")
    print(f"Setting up table: {TABLE_NAME}")
    print()

    table_id = get_table_id(BASE_ID, TABLE_NAME)
    if not table_id:
        print(f"ERROR: Table '{TABLE_NAME}' not found in base {BASE_ID}")
        print("Make sure the table exists and your token has schema.bases:read scope")
        return

    print(f"Found table ID: {table_id}")
    existing = get_existing_fields(BASE_ID, table_id)
    print(f"Existing fields: {existing}")
    print()

    created = 0
    skipped = 0
    failed = 0

    for field in FIELDS_TO_CREATE:
        if field["name"] in existing:
            print(f"  Skipped: {field['name']} (already exists)")
            skipped += 1
        else:
            success, error_type = create_field(BASE_ID, table_id, field)
            if success:
                created += 1
            else:
                failed += 1
                if error_type == "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND":
                    print()
                    print("ERROR: Airtable rejected schema changes.")
                    print(_permission_help_message())
                    break

    print()
    print("Setup complete.")
    print(f"  Created:  {created} fields")
    print(f"  Skipped:  {skipped} fields (already existed)")
    print(f"  Failed:   {failed} fields")

    if failed == 0:
        print()
        print("Your Airtable table is ready. Run python run_database.py next.")


if __name__ == "__main__":
    main()
