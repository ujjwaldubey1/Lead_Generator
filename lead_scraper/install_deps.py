"""Install project dependencies with pip."""

from __future__ import annotations

import subprocess
import sys


def main() -> None:
    """Install all required dependencies for the lead generation pipeline."""

    packages = [
        "requests",
        "openai",
        "apify-client",
        "pyairtable",
        "python-dotenv",
        "tenacity",
    ]

    for package in packages:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"Installed: {package}")

    print("All dependencies installed successfully.")


if __name__ == "__main__":
    main()
