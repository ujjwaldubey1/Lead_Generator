"""Save authenticated browser session cookies for X and LinkedIn."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional until Playwright is installed.
    sync_playwright = None  # type: ignore[assignment]


BASE_DIR = Path(__file__).resolve().parent
COOKIES_DIR = BASE_DIR / "cookies"


def save_cookies(platform: str, url: str, output_path: Path) -> None:
    """Open a visible browser so the user can log in and save session cookies."""

    if sync_playwright is None:
        print("Playwright is not installed. Run pip install -r requirements.txt first.")
        return

    print(f"\nOpening {platform} in browser...")
    print("Please log in manually, then press ENTER in this terminal.")
    print("Do NOT close the browser window.")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=30_000)
            input(f"\nPress ENTER after you have logged into {platform}...")
            cookies = context.cookies()
            COOKIES_DIR.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
            print(f"Cookies saved to {output_path}")
            browser.close()
    except Exception as exc:
        print(f"Failed to save cookies for {platform}: {exc}")


def main() -> None:
    """Run the cookie setup wizard for X and LinkedIn."""

    print("Cookie Setup Wizard")
    print("===================")
    print("This saves your login sessions for X and LinkedIn.")
    print("Your credentials are never stored, only session cookies.\n")

    choice = input(
        "Which platform to set up?\n"
        "1. X (Twitter)\n"
        "2. LinkedIn\n"
        "3. Both\n"
        "Enter 1, 2, or 3: "
    ).strip()

    if choice in {"1", "3"}:
        save_cookies("X (Twitter)", "https://x.com/login", COOKIES_DIR / "x_cookies.json")

    if choice in {"2", "3"}:
        save_cookies(
            "LinkedIn",
            "https://www.linkedin.com/login",
            COOKIES_DIR / "linkedin_cookies.json",
        )

    print("\nSetup complete. Run python run_scraper.py to start scraping.")


if __name__ == "__main__":
    main()
