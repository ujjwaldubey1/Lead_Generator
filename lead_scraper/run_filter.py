"""Run phase 2 lead qualification against raw_leads.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False

try:
    from .ai_filter.scorer import filter_leads, is_worth_scoring
    from .config import BASE_DIR, OUTPUT_FILE, QUALIFIED_OUTPUT_FILE
    from .utils.logger import get_logger
except ImportError:  # pragma: no cover - direct script execution fallback.
    from ai_filter.scorer import filter_leads, is_worth_scoring
    from config import BASE_DIR, OUTPUT_FILE, QUALIFIED_OUTPUT_FILE
    from utils.logger import get_logger


Lead = dict[str, Any]
logger = get_logger(__name__)
INPUT_FILE = OUTPUT_FILE
FILTER_OUTPUT_FILE = QUALIFIED_OUTPUT_FILE
CHECKPOINT_FILE = "filter_checkpoint.json"


def _load_env() -> tuple[str, int]:
    """Load runtime filter settings from the project .env file."""

    load_dotenv(BASE_DIR / ".env")

    service_description = os.getenv("SERVICE_DESCRIPTION", "").strip()
    min_score_raw = os.getenv("MIN_SCORE", "7").strip()

    try:
        min_score = int(min_score_raw)
    except ValueError:
        logger.warning("Invalid MIN_SCORE value '%s'; defaulting to 7.", min_score_raw)
        min_score = 7

    return service_description, min_score


def load_raw_leads(input_path: Path) -> list[Lead]:
    """Load raw leads from disk, returning an empty list when unavailable."""

    if not input_path.exists():
        raise FileNotFoundError(f"Input file missing: {input_path.name}")

    try:
        raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Input file %s contains invalid JSON: %s", input_path.name, exc)
        return []
    except OSError as exc:
        logger.warning("Unable to read input file %s: %s", input_path.name, exc)
        return []

    if not raw_data:
        logger.info("Input file %s is empty.", input_path.name)
        return []

    if not isinstance(raw_data, list):
        logger.warning("Input file %s must contain a JSON array.", input_path.name)
        return []

    return [item for item in raw_data if isinstance(item, dict)]


def load_checkpoint() -> dict[str, Any]:
    """Load already-scored post IDs from the checkpoint file."""

    checkpoint_path = BASE_DIR / CHECKPOINT_FILE
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to load checkpoint %s: %s", checkpoint_path.name, exc)
    return {}


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    """Save checkpoint after each successful score."""

    checkpoint_path = BASE_DIR / CHECKPOINT_FILE
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def load_existing_qualified(output_path: Path) -> list[Lead]:
    """Load any previously saved qualified leads so resume mode keeps them."""

    if not output_path.exists():
        return []

    try:
        raw_data = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to load existing qualified leads from %s: %s", output_path.name, exc)
        return []

    if not isinstance(raw_data, list):
        return []
    return [item for item in raw_data if isinstance(item, dict)]


def save_qualified(leads: list[Lead], output_file: Path) -> None:
    """Save qualified leads incrementally so partial results are preserved."""

    try:
        output_file.write_text(json.dumps(leads, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write %s: %s", output_file.name, exc)
        raise


def main(exit_on_error: bool = True) -> dict[str, Any]:
    """Load raw leads, qualify them with NVIDIA/Qwen, and persist the results."""

    summary: dict[str, Any] = {"ok": True, "raw": 0, "qualified": 0}
    service_description, min_score = _load_env()
    input_path = BASE_DIR / INPUT_FILE
    output_path = BASE_DIR / FILTER_OUTPUT_FILE

    try:
        raw_leads = load_raw_leads(input_path)
    except FileNotFoundError as exc:
        print(str(exc))
        logger.warning(str(exc))
        if exit_on_error:
            sys.exit(1)
        return {"ok": False, "raw": 0, "qualified": 0, "message": str(exc)}

    summary["raw"] = len(raw_leads)
    eligible = [post for post in raw_leads if is_worth_scoring(post)]
    skipped = len(raw_leads) - len(eligible)
    print(
        f"Pre-filter: {len(raw_leads)} total posts -> "
        f"{len(eligible)} worth scoring (skipping {skipped})"
    )

    checkpoint = load_checkpoint()
    existing_qualified = load_existing_qualified(output_path)
    qualified_leads = filter_leads(
        eligible,
        service_description,
        min_score=min_score,
        checkpoint=checkpoint,
        save_checkpoint_fn=save_checkpoint,
        save_batch_fn=lambda leads: save_qualified(leads, output_path),
        existing_qualified=existing_qualified,
    )
    summary["qualified"] = len(qualified_leads)
    summary["eligible"] = len(eligible)

    save_qualified(qualified_leads, output_path)
    expected_ids = {
        str(post.get("id", "")).strip()
        for post in eligible
        if str(post.get("id", "")).strip()
    }
    checkpoint_path = BASE_DIR / CHECKPOINT_FILE
    if checkpoint_path.exists() and expected_ids and expected_ids.issubset(set(load_checkpoint().keys())):
        checkpoint_path.unlink(missing_ok=True)

    message = f"Filter complete. {len(qualified_leads)} qualified leads saved to {FILTER_OUTPUT_FILE}"
    print(message)
    logger.info(message)
    summary["message"] = message
    return summary


if __name__ == "__main__":
    main()
