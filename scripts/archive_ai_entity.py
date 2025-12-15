#!/usr/bin/env python3
import os
from typing import Dict, Any

"""
Optional AI helper for StegArchive.

To enable:
- pip install openai
- export OPENAI_API_KEY=sk-...
- call classify_with_ai(text) from archive_classifier.py instead of classify_content()
"""

try:
    import openai
except ImportError:
    openai = None


def classify_with_ai(text: str) -> Dict[str, Any]:
    """
    Return a dict like:
    {
      "classification": "archived" or "active",
      "tags": ["ncaaf", "simulation", "historical"],
      "summary": "Short 1–2 sentence description"
    }
    """
    if openai is None:
        raise RuntimeError("openai library not installed")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    openai.api_key = api_key

    prompt = f"""
You are the StegArchive AI Entity. You receive raw conversation text and must decide:

1. classification: "active" if it relates to current StegVerse infra, SCW v4,
   StegCore, tax claims, NCAA ingestion engine, patent engine, or memoirs.
   "archived" if it is outdated simulations, political posts, random device Q&A, or clearly historical.

2. tags: a few short keywords (lowercase, no spaces, use dashes).

3. summary: 1–2 sentences summarizing the conversation.

Return ONLY valid JSON with keys: classification, tags, summary.

Conversation:
{text}
"""

    # Use a generic chat completion call; the exact model name is a placeholder
    response = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a classification assistant for StegArchive."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    import json
    content = response.choices[0].message["content"]
    data = json.loads(content)
    return data
