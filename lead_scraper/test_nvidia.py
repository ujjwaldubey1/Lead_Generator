"""Connection test for NVIDIA NIM with the configured Qwen model."""

from __future__ import annotations

import json

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False

try:
    from .ai_filter.scorer import call_nvidia_api
    from .config import BASE_DIR
except ImportError:  # pragma: no cover - direct script execution fallback.
    from ai_filter.scorer import call_nvidia_api
    from config import BASE_DIR


def main() -> None:
    """Test the NVIDIA API connection and print the parsed JSON response."""

    load_dotenv(BASE_DIR / ".env")
    prompt = 'Return {"status":"working","score":10}'

    try:
        raw = call_nvidia_api(prompt)
        if raw is None:
            raise RuntimeError("NVIDIA API returned no response.")
        parsed = json.loads(raw)
        print(parsed)
        print("NVIDIA connection successful")
    except Exception as exc:
        print(f"NVIDIA test failed: {exc}")


if __name__ == "__main__":
    main()

