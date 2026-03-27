"""Generate personalized outreach emails with NVIDIA NIM."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    requests = None  # type: ignore[assignment]

try:
    from ..ai_filter.scorer import clean_response
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from ai_filter.scorer import clean_response
    from utils.logger import get_logger


Lead = dict[str, Any]
EmailPayload = dict[str, str]
logger = get_logger(__name__)
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _call_nvidia_api(prompt: str) -> str | None:
    """Call NVIDIA NIM for outreach email generation."""

    if requests is None:
        return None

    headers = {
        "Authorization": f"Bearer {os.getenv('NVIDIA_API_KEY', '').strip()}",
        "Accept": "application/json",
    }
    payload = {
        "model": os.getenv("NVIDIA_MODEL", "qwen/qwen3.5-122b-a10b"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an outreach email assistant. "
                    "Always respond with valid JSON only. "
                    "No preamble. No markdown. No explanation. "
                    "Do not include <think> tags in output."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": int(os.getenv("NVIDIA_MAX_TOKENS", "1500")),
        "temperature": 0.3,
        "top_p": 0.95,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": True},
    }

    try:
        response = requests.post(
            INVOKE_URL,
            headers=headers,
            json=payload,
            timeout=int(os.getenv("NVIDIA_TIMEOUT", "45")),
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    except requests.RequestException as exc:
        logger.error("NVIDIA email request failed: %s", exc)
        return None
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.error("Unexpected NVIDIA email response shape: %s", exc)
        return None

    return clean_response(raw)


def generate_email(
    lead: Lead,
    service_description: str,
    sender_name: str,
    sender_company: str,
    calendar_link: str,
) -> EmailPayload | None:
    """Generate outreach email copy for a lead using NVIDIA/Qwen."""

    prompt = f"""
You are writing a cold outreach email to a lead who publicly shared a pain point.

Service:
{service_description}

Lead context:
{json.dumps({
    "author": lead.get("author", ""),
    "platform": lead.get("platform", ""),
    "pain_point": lead.get("pain_point", ""),
    "title": lead.get("title", ""),
    "url": lead.get("url", ""),
    "ai_score": lead.get("ai_score", 0),
}, ensure_ascii=False, indent=2)}

Return ONLY this JSON:
{{
  "subject": str,
  "body": str
}}

Rules:
- Max 100 words in body.
- Line 1 must reference their specific pain_point.
- Include one social proof sentence.
- Include one CTA with this calendar link: {calendar_link}
- Avoid these words entirely: synergy, leverage, revolutionary, game-changer
- Tone must be direct, human, peer-to-peer.
- Sign off with {sender_name} and {sender_company}.
""".strip()

    try:
        raw = _call_nvidia_api(prompt)
        if raw is None:
            return None
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "Email JSON parse failed for post id=%s author=%s",
            str(lead.get("id", "")).strip() or "unknown",
            str(lead.get("author", "")).strip() or "unknown",
        )
        return None
    except Exception as exc:
        logger.error(
            "Email generation failed for post id=%s author=%s: %s",
            str(lead.get("id", "")).strip() or "unknown",
            str(lead.get("author", "")).strip() or "unknown",
            exc,
        )
        return None

    if not isinstance(parsed, dict):
        return None

    subject = str(parsed.get("subject", "")).strip()
    body = str(parsed.get("body", "")).strip()
    if not subject or not body:
        return None

    return {"subject": subject, "body": body}


if __name__ == "__main__":
    print("email_writer.py provides generate_email(...).")
