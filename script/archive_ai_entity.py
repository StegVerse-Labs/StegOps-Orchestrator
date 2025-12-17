#!/usr/bin/env python3
import json
import os
from typing import Any, Dict

from openai import OpenAI

DEFAULT_MODEL = os.getenv("STEGARCHIVE_MODEL", "gpt-5.2")

SYSTEM = """You are StegArchive AI Entity.

Your task is to classify conversation exports and documents for StegVerse.

Classification rules:

- Use "active" if the content directly advances current StegVerse work:
  automation, ops, workflows, deployments, security, documentation,
  revenue planning, audits, or service requests.

- Use "archived" if the content is clearly historical, obsolete, exploratory,
  or no longer relevant to current execution.

LEAD DETECTION:
If the content includes:
- pricing questions
- requests for setup, help, audits, or support
- phrases like "how much", "pricing", "can you help", "we need", "looking for",
  "interested in", "services", or "quote"

Then:
- classification MUST be "active"
- include tag "lead"
- summary should clearly state the request

Return STRICT JSON ONLY in this format:
{
  "classification": "active" | "archived",
  "tags": ["tag1", "tag2", ...],   // lowercase, dashes allowed, max 8
  "summary": "1-2 sentence summary",
  "confidence": 0.0-1.0
}

No markdown. No extra keys. No commentary.
"""

def _safe_json_loads(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end + 1])
        raise

def classify_text(text: str) -> Dict[str, Any]:
    client = OpenAI()  # Uses OPENAI_API_KEY from environment

    response = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM,
        input=(text or "")[:120_000],
    )

    data = _safe_json_loads(response.output_text)

    classification = data.get("classification")
    if classification not in ("active", "archived"):
        classification = "active"

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip().lower().replace(" ", "-") for t in tags if str(t).strip()]
    tags = tags[:8]

    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = "No summary provided."

    try:
        confidence = float(data.get("confidence", 0.5))
    except Exception:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return {
        "classification": classification,
        "tags": tags,
        "summary": summary,
        "confidence": confidence,
    }
