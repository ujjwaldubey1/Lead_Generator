"""Prompt construction utilities for NVIDIA-based lead scoring."""

from __future__ import annotations

import json
from typing import Any


def build_scoring_prompt(post: dict[str, Any], service_description: str) -> str:
    """Build the scoring prompt used to evaluate a single lead."""

    compact_post = {
        "id": post.get("id", ""),
        "title": post.get("title", ""),
        "body": post.get("body", ""),
        "author": post.get("author", ""),
        "subreddit": post.get("subreddit", ""),
        "platform": post.get("platform", ""),
        "url": post.get("url", ""),
    }
    post_json = json.dumps(compact_post, ensure_ascii=False, indent=2)

    return f"""You are qualifying inbound lead opportunities from public social posts.

Service description:
{service_description}

Analyze the following post and decide whether the author appears to need this service.

Post:
{post_json}

Return ONLY valid JSON. Do not include markdown, code fences, labels, commentary, or any preamble.
Your response must match this exact schema:
{{
  "relevance_score": int,
  "buying_intent": "high" | "medium" | "low" | "none",
  "pain_point": str,
  "is_qualified": bool,
  "disqualify_reason": str | null
}}

Scoring guidance:
- 9-10 = actively asking for this exact service right now
- 7-8 = clear pain point, likely open to a solution
- 5-6 = related problem but intent unclear
- 1-4 = not relevant or just browsing

Rules:
- Set "pain_point" to one concise sentence describing the core problem.
- Set "is_qualified" to true only if the post is a strong match for the service and shows real need.
- Set "disqualify_reason" to null when qualified, otherwise provide a short reason.
- Do not invent facts that are not in the post.
- Output JSON only.
"""
