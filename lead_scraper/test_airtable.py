"""Connection test for Airtable."""

from __future__ import annotations

import os

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
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR


def main() -> None:
    """Test Airtable connectivity by fetching all records from the configured table."""

    load_dotenv(BASE_DIR / ".env")

    try:
        if Api is None:
            raise RuntimeError("pyairtable is not installed.")
        api = Api(os.getenv("AIRTABLE_API_KEY", "").strip())
        table = api.table(
            os.getenv("AIRTABLE_BASE_ID", "").strip(),
            os.getenv("AIRTABLE_TABLE_NAME", "Leads").strip(),
        )
        records = table.all()
        print(f"Airtable connected. Records: {len(records)}")
    except Exception as exc:
        print(f"Airtable test failed: {exc}")


if __name__ == "__main__":
    main()

