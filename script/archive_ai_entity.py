#!/usr/bin/env python3
import os
import shutil
from datetime import datetime
from pathlib import Path

from scripts.archive_ai_entity import classify_text

REPO = Path(__file__).resolve().parents[1]

INBOX = REPO / "inbox"
ACTIVE_DIR = REPO / "processed" / "active"
ARCHIVED_DIR = REPO / "processed" / "archived"

# Prefer your current structure shown in screenshots
INDEX_PRIMARY = REPO / "apps" / "routers" / "ARCHIVE" / "COMBINED_ARCHIVE_LIST.md"
INDEX_FALLBACK = REPO / "ARCHIVE" / "COMBINED_ARCHIVE_LIST.md"

def get_index_path() -> Path:
    if INDEX_PRIMARY.exists() or INDEX_PRIMARY.parent.exists():
        return INDEX_PRIMARY
    return INDEX_FALLBACK

def ensure_dirs(index_path: Path):
    INBOX.mkdir(parents=True, exist_ok=True)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    if not index_path.exists():
        index_path.write_text(
            "# StegVerse Combined Archive List\n\n## Auto-log\n",
            encoding="utf-8"
        )

def append_log(index_path: Path, filename: str, result: dict, dest_rel: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = (
        f"- `{ts}` — `{dest_rel}` → **{result['classification'].upper()}** "
        f"(conf={result['confidence']:.2f}) tags={result['tags']} — {result['summary']}\n"
    )
    with index_path.open("a", encoding="utf-8") as f:
        f.write(line)

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it as a GitHub Actions secret.")

    index_path = get_index_path()
    ensure_dirs(index_path)

    files = sorted(INBOX.glob("*.md"))
    if not files:
        print("No .md files in inbox/. Nothing to do.")
        return

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        result = classify_text(text)

        if result["classification"] == "archived":
            dest = ARCHIVED_DIR / path.name
        else:
            dest = ACTIVE_DIR / path.name

        shutil.move(str(path), str(dest))

        dest_rel = f"processed/{result['classification']}/{dest.name}"
        print(f"{path.name} => {result['classification']} tags={result['tags']} conf={result['confidence']:.2f}")

        append_log(index_path, dest.name, result, dest_rel)

if __name__ == "__main__":
    main()
