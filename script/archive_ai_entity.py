#!/usr/bin/env python3
import json
import os
from typing import Any, Dict

from openai import OpenAI

DEFAULT_MODEL = os.getenv("STEGARCHIVE_MODEL", "gpt-5.2")

SYSTEM = """You are StegArchive AI Entity.

Your task:
Classify conversation exports for StegVerse.

Rules:
- "active" if it directly advances current StegVerse work:
  SCW / StegCore / StegSocial automation, repo workflows, ops, deployments,
  PAT/secrets, tax/VA claims docs, memoir preservation,
  NCAA ingestion engine, patent engine.
- "archived" if it is:
  outdated simulations, one-off device Q&A, XR/MetaQuest,
  generic Kali/bash escalation, political posting content,
  or clearly historical/moot.

Return STRICT JSON only:
{
  "classification": "active" | "archived",
  "tags": ["tag1","tag2",...],   // lowercase, dashes ok, max 8
  "summary": "1-2 sentences",
  "confidence": 0.0-1.0
}

No markdown. No extra keys.
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
    """
    Core AI classification entrypoint.
    Called by archive_classifier.py
    """
    client = OpenAI()  # reads OPENAI_API_KEY from env

    resp = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM,
        input=(text or "")[:120_000],  # size guardrail
    )

    data = _safe_json_loads(resp.output_text)

    cls = data.get("classification")
    if cls not in ("active", "archived"):
        cls = "active"

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip().lower().replace(" ", "-") for t in tags if str(t).strip()]
    tags = tags[:8]

    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = "No summary provided."

    try:
        conf = float(data.get("confidence", 0.5))
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))

    return {
        "classification": cls,
        "tags": tags,
        "summary": summary,
        "confidence": conf,
    }
