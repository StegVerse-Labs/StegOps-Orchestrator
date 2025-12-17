#!/usr/bin/env python3
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path for CI + direct execution
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from script.archive_ai_entity import classify_text
from script.archive_status import write_status_md

INBOX = REPO / "inbox"
ACTIVE_DIR = REPO / "processed" / "active"
ARCHIVED_DIR = REPO / "processed" / "archived"

INDEX_PRIMARY = REPO / "apps" / "routers" / "ARCHIVE" / "COMBINED_ARCHIVE_LIST.md"
INDEX_FALLBACK = REPO / "ARCHIVE" / "COMBINED_ARCHIVE_LIST.md"

WATCHLIST = REPO / "apps" / "routers" / "ARCHIVE" / "watchlist.txt"
STATUS_MD = REPO / "apps" / "routers" / "ARCHIVE" / "STATUS.md"
STATE_JSON = REPO / "apps" / "routers" / "ARCHIVE" / "run_state.json"

def get_index_path() -> Path:
    if INDEX_PRIMARY.exists() or INDEX_PRIMARY.parent.exists():
        return INDEX_PRIMARY
    return INDEX_FALLBACK

def ensure_dirs(index_path: Path):
    INBOX.mkdir(parents=True, exist_ok=True)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)

    if not index_path.exists():
        index_path.write_text("# StegVerse Combined Archive List\n\n## Auto-log\n", encoding="utf-8")

def append_log(index_path: Path, result: dict, dest_rel: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = (
        f"- `{ts}` — `{dest_rel}` → **{result['classification'].upper()}** "
        f"(conf={result['confidence']:.2f}) tags={result['tags']} — {result['summary']}\n"
    )
    with index_path.open("a", encoding="utf-8") as f:
        f.write(line)

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it as a GitHub Actions secret.")

    this_run_epoch = int(datetime.now(timezone.utc).timestamp())
    index_path = get_index_path()
    ensure_dirs(index_path)

    files = sorted(INBOX.glob("*.md"))
    counts = {"processed": 0, "archived": 0, "active": 0}
    summary_lines: list[str] = []

    if not files:
        print("No .md files in inbox/. Nothing to do.")
        write_status_md(REPO, STATUS_MD, WATCHLIST, STATE_JSON, this_run_epoch, counts, summary_lines)
        print(f"Wrote status: {STATUS_MD}")
        return

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        result = classify_text(text)

        counts["processed"] += 1
        if result["classification"] == "archived":
            counts["archived"] += 1
            dest = ARCHIVED_DIR / path.name
        else:
            counts["active"] += 1
            dest = ACTIVE_DIR / path.name

        shutil.move(str(path), str(dest))
        dest_rel = f"processed/{result['classification']}/{dest.name}"

        tags = ",".join(result.get("tags", [])[:4])
        sline = (result.get("summary") or "").strip()
        if tags and sline:
            sline = f"{sline} (tags: {tags})"
        if sline:
            summary_lines.append(sline)

        print(f"{path.name} => {result['classification']} tags={result['tags']} conf={result['confidence']:.2f}")

        append_log(index_path, result, dest_rel)

    write_status_md(REPO, STATUS_MD, WATCHLIST, STATE_JSON, this_run_epoch, counts, summary_lines)
    print(f"Wrote status: {STATUS_MD}")

if __name__ == "__main__":
    main()
