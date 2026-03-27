"""Qwen-based lead scoring and filtering via NVIDIA NIM."""

from __future__ import annotations

import json
import logging
import os
import time
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
    from .prompt_builder import build_scoring_prompt
except ImportError:  # pragma: no cover - direct script execution fallback.
    from utils.logger import get_logger
    from ai_filter.prompt_builder import build_scoring_prompt


Lead = dict[str, Any]
ScoreResult = dict[str, Any]
Checkpoint = dict[str, Any]
logger = get_logger(__name__)
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
BUYING_INTENTS = {"high", "medium", "low", "none"}


def _get_retry_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return the configured tenacity retry decorator or a no-op fallback."""

    if retry is None:
        def passthrough(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return passthrough

    return retry(wait=wait_exponential(min=2, max=30), stop=stop_after_attempt(3), reraise=True)


def _is_valid_score_payload(payload: dict[str, Any]) -> bool:
    """Validate that the parsed model payload contains the required keys."""

    required_keys = {
        "relevance_score",
        "buying_intent",
        "pain_point",
        "is_qualified",
        "disqualify_reason",
    }
    return required_keys.issubset(payload.keys())


def _coerce_bool(value: Any) -> bool:
    """Coerce common model outputs into a boolean safely."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _coerce_int(value: Any) -> int:
    """Convert a numeric-like value into an integer without raising."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _post_reference(post: Lead) -> tuple[str, str]:
    """Return safe identifiers for logging without exposing post content."""

    return str(post.get("id", "")).strip() or "unknown", str(post.get("author", "")).strip() or "unknown"


def is_worth_scoring(post: dict[str, Any]) -> bool:
    """
    Quick pre-filter to skip posts that are obviously not leads.
    Saves API calls and prevents timeouts on junk posts.
    """

    body = str(post.get("body", "")).strip()
    title = str(post.get("title", "")).strip()
    combined = (title + " " + body).lower()

    if len(combined) < 30:
        return False

    skip_phrases = [
        "i made",
        "i built",
        "i created",
        "i launched",
        "showing off",
        "proud of",
        "just finished",
        "meme",
        "funny",
        "joke",
        "rant",
        "vent",
        "thank you",
        "thanks everyone",
        "appreciation post",
    ]
    if any(phrase in combined for phrase in skip_phrases):
        return False

    buying_signals = [
        "need",
        "looking for",
        "want",
        "help",
        "hire",
        "recommend",
        "suggestion",
        "advice",
        "struggling",
        "how do i",
        "anyone know",
        "automate",
        "save time",
        "too much time",
        "manual",
        "repetitive",
        "outsource",
    ]
    if not any(signal in combined for signal in buying_signals):
        return False

    return True


def call_nvidia_api(prompt: str) -> str | None:
    """Call NVIDIA NIM API with llama model and return cleaned response text."""

    headers = {
        "Authorization": f"Bearer {os.getenv('NVIDIA_API_KEY')}",
        "Accept": "application/json"
    }
    payload = {
        "model": os.getenv("NVIDIA_FAST_MODEL", "meta/llama-3.1-8b-instruct"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a lead qualification assistant. "
                    "Always respond with valid JSON only. "
                    "No preamble. No markdown. No explanation. "
                    "No extra text before or after the JSON."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 300,
        "temperature": 0.3,
        "top_p": 0.95,
        "stream": False
    }
    try:
        response = requests.post(
            INVOKE_URL,
            headers=headers,
            json=payload,
            timeout=int(os.getenv("NVIDIA_TIMEOUT", "30"))
        )
        if response.status_code != 200:
            logging.error(
                f"NVIDIA API error {response.status_code}: {response.text[:200]}"
            )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        return raw.strip().strip("```json").strip("```").strip()
    except requests.Timeout:
        logging.error("NVIDIA API request timed out")
        raise
    except requests.HTTPError as e:
        logging.error(f"NVIDIA API request failed: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error calling NVIDIA API: {e}")
        raise


def clean_response(raw: str) -> str:
    """
    Strip code fences so JSON parsing sees only the payload.
    """

    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned.strip()


@_get_retry_decorator()
def score_lead(post: Lead, service_description: str) -> ScoreResult | None:
    """Score a single lead using Qwen via NVIDIA NIM."""

    if requests is None:
        logger.warning("requests is not installed; skipping AI scoring.")
        return None

    post_id, author = _post_reference(post)
    truncated_post = {**post, "body": str(post.get("body", ""))[:500]}
    prompt = build_scoring_prompt(truncated_post, service_description)
    raw = ""

    try:
        cleaned_response = call_nvidia_api(prompt)
        if cleaned_response is None:
            return None

        raw = cleaned_response
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed for post id=%s author=%s - skipping", post_id, author)
        logger.debug("Raw response was: %s", raw[:200])
        return None
    except requests.RequestException as exc:
        logger.error("HTTP error for post id=%s author=%s: %s", post_id, author, exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error for post id=%s author=%s: %s", post_id, author, exc)
        raise

    if not isinstance(parsed, dict) or not _is_valid_score_payload(parsed):
        logger.warning("Incomplete model payload for post id=%s author=%s - skipping", post_id, author)
        return None

    buying_intent = str(parsed.get("buying_intent", "")).strip().lower()
    if buying_intent not in BUYING_INTENTS:
        logger.warning("Unexpected buying_intent for post id=%s author=%s - skipping", post_id, author)
        return None

    return parsed


def filter_leads(
    raw_leads: list[Lead],
    service_description: str,
    min_score: int = 7,
    checkpoint: Checkpoint | None = None,
    save_checkpoint_fn: Callable[[Checkpoint], None] | None = None,
    save_batch_fn: Callable[[list[Lead]], None] | None = None,
    existing_qualified: list[Lead] | None = None,
    batch_size: int = 10,
) -> list[Lead]:
    """Score raw leads and keep only the qualified high-intent results."""

    if not raw_leads:
        print(f"0 / 0 leads qualified (min score: {min_score})")
        logger.info("No raw leads supplied for AI filtering.")
        return []

    if not service_description.strip():
        logger.warning("SERVICE_DESCRIPTION is empty; skipping AI filtering.")
        print(f"0 / {len(raw_leads)} leads qualified (min score: {min_score})")
        return []

    if requests is None:
        logger.warning("requests is not installed; skipping AI filtering.")
        print(f"0 / {len(raw_leads)} leads qualified (min score: {min_score})")
        return []

    if not os.getenv("NVIDIA_API_KEY", "").strip():
        logger.warning("NVIDIA_API_KEY is not configured; skipping AI filtering.")
        print(f"0 / {len(raw_leads)} leads qualified (min score: {min_score})")
        return []

    qualified_leads: list[Lead] = list(existing_qualified or [])
    total = len(raw_leads)
    processed_checkpoint = checkpoint if checkpoint is not None else {}
    successful_scores = 0

    for index, post in enumerate(raw_leads, start=1):
        post_id, author = _post_reference(post)
        if post_id in processed_checkpoint:
            continue

        print(f"Scoring lead {index} of {total}...")

        try:
            score_data = score_lead(post, service_description)
        except Exception as exc:
            logger.error("Failed scoring after retries for post id=%s author=%s: %s", post_id, author, exc)
            score_data = None

        if score_data is not None:
            ai_score = _coerce_int(score_data.get("relevance_score", 0))
            is_qualified = _coerce_bool(score_data.get("is_qualified", False))
            processed_checkpoint[post_id] = {
                "ai_score": ai_score,
                "is_qualified": is_qualified,
            }
            if save_checkpoint_fn is not None:
                save_checkpoint_fn(processed_checkpoint)

            if ai_score >= min_score and is_qualified:
                qualified_post = {
                    **post,
                    "ai_score": ai_score,
                    "buying_intent": str(score_data.get("buying_intent", "")).strip().lower(),
                    "pain_point": str(score_data.get("pain_point", "")).strip(),
                }
                if not any(str(item.get("id", "")).strip() == post_id for item in qualified_leads):
                    qualified_leads.append(qualified_post)

            successful_scores += 1
            if save_batch_fn is not None and successful_scores % batch_size == 0:
                save_batch_fn(qualified_leads)

        time.sleep(1)

    if save_batch_fn is not None:
        save_batch_fn(qualified_leads)

    print(f"{len(qualified_leads)} / {total} leads qualified (min score: {min_score})")
    logger.info(
        "AI qualification complete: %s of %s leads kept at min score %s.",
        len(qualified_leads),
        total,
        min_score,
    )
    return qualified_leads
