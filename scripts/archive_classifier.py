#!/usr/bin/env python3
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX_DIR = os.path.join(BASE_DIR, "inbox")
PROCESSED_ACTIVE = os.path.join(BASE_DIR, "processed", "active")
PROCESSED_ARCHIVED = os.path.join(BASE_DIR, "processed", "archived")
ARCHIVE_INDEX = os.path.join(BASE_DIR, "ARCHIVE", "COMBINED_ARCHIVE_LIST.md")

os.makedirs(PROCESSED_ACTIVE, exist_ok=True)
os.makedirs(PROCESSED_ARCHIVED, exist_ok=True)

# Simple keyword-based heuristics
ARCHIVE_KEYWORDS = [
    "meta quest", "xr", "headset",
    "bash -p", "kali linux", "privilege escalation",
    "emoji", "unicode", "steganography",
    "gun law", "trump gun", "facebook summary",
    "week 12 cfp", "week 13 cfp", "chaos bracket",
    "nightmare bracket", "old simulation",
    "geopolitical", "ukraine", "taiwan", "russia"
]

ACTIVE_HINTS = [
    "scw v4", "stegcore", "stegverse infra", "patent engine",
    "patent entity", "ncaa ingestion", "tax summary",
    "memoir", "free-dom", "stegsocial", "stegtalk"
]


def classify_content(text: str) -> str:
    """
    Returns 'archived' or 'active' based on simple heuristics.
    You can override this later with AI from archive_ai_entity.py.
    """
    lower = text.lower()

    # If clearly infra-related, force active
    if any(hint in lower for hint in ACTIVE_HINTS):
        return "active"

    # If it hits archive keywords, call it archived
    if any(kw in lower for kw in ARCHIVE_KEYWORDS):
        return "archived"

    # Fallback: treat as active unless clearly labelled
    if "archive this" in lower or "ready to archive" in lower:
        return "archived"

    return "active"


def append_to_archive_index(filename: str, classification: str):
    """
    Adds a small log line at the bottom of COMBINED_ARCHIVE_LIST.md
    so you have a crude history of classifier decisions.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rel_path = f"processed/{classification}/{filename}"

    line = f"- `{ts}` — `{rel_path}` classified as **{classification.upper()}**\n"

    with open(ARCHIVE_INDEX, "a", encoding="utf-8") as f:
        f.write("\n" + line)


def main():
    if not os.path.isdir(INBOX_DIR):
        print(f"No inbox directory at {INBOX_DIR}. Nothing to do.")
        return

    files = [f for f in os.listdir(INBOX_DIR) if f.endswith(".md")]
    if not files:
        print("No new .md files in inbox/.")
        return

    for fname in files:
        src = os.path.join(INBOX_DIR, fname)
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        classification = classify_content(text)
        if classification == "archived":
            dst = os.path.join(PROCESSED_ARCHIVED, fname)
        else:
            dst = os.path.join(PROCESSED_ACTIVE, fname)

        shutil.move(src, dst)
        print(f"{fname}: classified as {classification}, moved to {dst}")

        append_to_archive_index(fname, classification)


if __name__ == "__main__":
    main()
