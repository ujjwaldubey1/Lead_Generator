"""Find contact emails for qualified leads using Hunter.io."""

from __future__ import annotations

import re
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    requests = None  # type: ignore[assignment]

try:
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from utils.logger import get_logger


logger = get_logger(__name__)
EmailResult = dict[str, str | int | None]
HUNTER_URL = "https://api.hunter.io/v2/domain-search"


def _username_tokens(username: str) -> list[str]:
    """Extract useful username tokens for matching against Hunter results."""

    cleaned = username.strip().lstrip("@").lower()
    return [token for token in re.split(r"[^a-z0-9]+", cleaned) if len(token) >= 2]


def find_email(username: str, platform: str, api_key: str) -> EmailResult:
    """Find a likely email address for the provided handle using Hunter.io."""

    if requests is None or not api_key.strip() or not username.strip():
        return {"email": None, "confidence": None}

    tokens = _username_tokens(username)
    params = {
        "company": username.strip().lstrip("@"),
        "limit": 10,
        "api_key": api_key,
    }

    try:
        response = requests.get(HUNTER_URL, params=params, timeout=20)
        response.raise_for_status()
        emails = response.json().get("data", {}).get("emails", [])
    except requests.RequestException as exc:
        logger.error("Hunter lookup failed for handle=%s platform=%s: %s", username, platform, exc)
        return {"email": None, "confidence": None}
    except (TypeError, ValueError, KeyError) as exc:
        logger.error("Hunter response parse failed for handle=%s platform=%s: %s", username, platform, exc)
        return {"email": None, "confidence": None}

    best_match: EmailResult = {"email": None, "confidence": None}
    best_confidence = 0

    for item in emails:
        value = str(item.get("value", "")).strip()
        confidence = int(item.get("confidence", 0) or 0)
        if not value or confidence < 70:
            continue

        local_part = value.split("@")[0].lower()
        if tokens and not any(token in local_part for token in tokens):
            continue

        if confidence > best_confidence:
            best_confidence = confidence
            best_match = {"email": value, "confidence": confidence}

    return best_match


if __name__ == "__main__":
    print("email_finder.py provides find_email(username, platform, api_key).")

