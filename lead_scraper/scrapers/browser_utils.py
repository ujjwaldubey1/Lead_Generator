"""Shared Playwright browser launch helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _candidate_browser_paths() -> list[Path]:
    """Return likely local Chrome or Edge executable paths on Windows."""

    candidates = [
        Path(os.getenv("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return [path for path in candidates if str(path) and path.exists()]


def launch_chromium(playwright: Any, headless: bool) -> Any:
    """Launch Chromium with fallbacks for system Chrome or Edge."""

    launch_kwargs = {"headless": headless}
    errors: list[str] = []

    try:
        return playwright.chromium.launch(**launch_kwargs)
    except Exception as exc:
        errors.append(str(exc))

    for channel in ("chrome", "msedge"):
        try:
            return playwright.chromium.launch(channel=channel, **launch_kwargs)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")

    for executable_path in _candidate_browser_paths():
        try:
            return playwright.chromium.launch(executable_path=str(executable_path), **launch_kwargs)
        except Exception as exc:
            errors.append(f"{executable_path}: {exc}")

    raise RuntimeError(
        "Unable to launch a Chromium browser. Install Playwright browsers with "
        "'playwright install chromium' or ensure Chrome/Edge is installed locally. "
        f"Launch attempts failed: {' | '.join(errors[:3])}"
    )
