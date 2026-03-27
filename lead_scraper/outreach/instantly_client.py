"""Instantly.ai client for adding leads to a campaign."""

from __future__ import annotations

from typing import Any, Callable

try:
    import requests
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    requests = None  # type: ignore[assignment]

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ImportError:  # pragma: no cover - fallback keeps module importable.
    retry = None  # type: ignore[assignment]
    stop_after_attempt = None  # type: ignore[assignment]
    wait_exponential = None  # type: ignore[assignment]

try:
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from utils.logger import get_logger


logger = get_logger(__name__)
INSTANTLY_URL = "https://api.instantly.ai/api/v1/lead/add"


def _get_retry_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return the configured tenacity retry decorator or a no-op fallback."""

    if retry is None:
        def passthrough(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return passthrough

    return retry(
        wait=wait_exponential(min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=False,
        retry_error_callback=lambda _state: False,
    )


@_get_retry_decorator()
def add_lead_to_campaign(
    email: str,
    first_name: str,
    custom_vars: dict[str, Any],
    campaign_id: str,
    api_key: str,
) -> bool:
    """Add a lead to an Instantly campaign."""

    if requests is None or not email.strip() or not campaign_id.strip() or not api_key.strip():
        return False

    payload = {
        "api_key": api_key,
        "campaign_id": campaign_id,
        "skip_if_in_workspace": True,
        "leads": [
            {
                "email": email,
                "first_name": first_name,
                "custom_variables": {
                    "pain_point": custom_vars.get("pain_point", ""),
                    "ai_score": custom_vars.get("ai_score", ""),
                    "platform": custom_vars.get("platform", ""),
                    "post_url": custom_vars.get("post_url", ""),
                    "subject": custom_vars.get("subject", ""),
                    "body": custom_vars.get("body", ""),
                },
            }
        ],
    }

    try:
        response = requests.post(INSTANTLY_URL, json=payload, timeout=20)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Instantly add-lead failed for email=%s: %s", email, exc)
        raise
    except Exception as exc:
        logger.error("Unexpected Instantly error for email=%s: %s", email, exc)
        return False


if __name__ == "__main__":
    print("instantly_client.py provides add_lead_to_campaign(...).")
