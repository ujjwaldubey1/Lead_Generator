"""Central configuration for the lead generation pipeline."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback keeps local runs working without deps installed.
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        """Fallback no-op when python-dotenv is unavailable."""

        return False


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

TARGET_SUBREDDITS = [
    "entrepreneur",
    "smallbusiness",
    "startups",
]

KEYWORDS = [
    "looking for",
    "need help with",
    "recommend a",
    "hiring for",
    "struggling with",
    "need a freelancer",
]

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "qwen/qwen3.5-122b-a10b").strip()
NVIDIA_FALLBACK_MODEL = os.getenv("NVIDIA_FALLBACK_MODEL", "meta/llama-3.1-8b-instruct").strip()
NVIDIA_MAX_TOKENS = int(os.getenv("NVIDIA_MAX_TOKENS", "1500"))
NVIDIA_TIMEOUT = int(os.getenv("NVIDIA_TIMEOUT", "45"))
SERVICE_DESCRIPTION = os.getenv("SERVICE_DESCRIPTION", "").strip()
MIN_SCORE = int(os.getenv("MIN_SCORE", "7"))
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "").strip()
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "").strip()
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads").strip()
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "").strip()
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "").strip()
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID", "").strip()
SENDER_NAME = os.getenv("SENDER_NAME", "").strip()
SENDER_COMPANY = os.getenv("SENDER_COMPANY", "").strip()
CALENDAR_LINK = os.getenv("CALENDAR_LINK", "").strip()
SCRAPE_DELAY = 2
OUTPUT_FILE = "raw_leads.json"
QUALIFIED_OUTPUT_FILE = "qualified_leads.json"
SYNC_LOG_FILE = "sync_log.json"
REDDIT_USER_AGENT = "LeadScraper/1.0"
REQUEST_TIMEOUT = 20
