"""Connection test for Apify."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False

try:
    from apify_client import ApifyClient
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    ApifyClient = None  # type: ignore[assignment]

try:
    from .config import BASE_DIR
except ImportError:  # pragma: no cover - direct script execution fallback.
    from config import BASE_DIR


def main() -> None:
    """Test Apify connectivity by fetching the current user profile."""

    load_dotenv(BASE_DIR / ".env")

    try:
        if ApifyClient is None:
            raise RuntimeError("apify-client is not installed.")
        client = ApifyClient(os.getenv("APIFY_TOKEN", "").strip())
        user = client.user().get()
        username = user.get("username", "unknown")
        print(f"Apify connected. User: {username}")
    except Exception as exc:
        print(f"Apify test failed: {exc}")


if __name__ == "__main__":
    main()
