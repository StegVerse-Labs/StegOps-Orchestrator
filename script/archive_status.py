#!/usr/bin/env python3
import subprocess
from pathlib import Path
from datetime import datetime, timezone

def _run(cmd, cwd: Path) -> str:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()

def _git_last_commit_epoch(repo: Path, rel_path: str) -> int | None:
    p = repo / rel_path
    if not p.exists():
        return None
    # unix epoch seconds for last commit touching this path
    out = _run(["git", "log", "-1", "--format=%ct", "--", rel_path], cwd=repo)
    if not out:
        return None
    return int(out)

def _read_watchlist(repo: Path, watchlist_path: Path) -> list[str]:
    if not watchlist_path.exists():
        return []
    lines = watchlist_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    items = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s)
    return items

def write_status_md(repo: Path, status_md: Path, watchlist_path: Path, last_archive_epoch: int | None):
    items = _read_watchlist(repo, watchlist_path)

    status_md.parent.mkdir(parents=True, exist_ok=True)

    if last_archive_epoch is None:
        last_archive_str = "None (no archive event yet)"
    else:
        dt = datetime.fromtimestamp(last_archive_epoch, tz=timezone.utc)
        last_archive_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    rows = []
    for rel in items:
        ts = _git_last_commit_epoch(repo, rel)
        if ts is None:
            rows.append((rel, "❓ MISSING", "—"))
            continue

        dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if last_archive_epoch is None:
            rows.append((rel, "✅ UP TO DATE", dt))
        else:
            if ts >= last_archive_epoch:
                rows.append((rel, "✅ UP TO DATE", dt))
            else:
                rows.append((rel, "⚠️ STALE", dt))

    # Render markdown
    md = []
    md.append("# StegArchive Status")
    md.append("")
    md.append(f"- Last archive event: **{last_archive_str}**")
    md.append("")
    md.append("## Watched files")
    md.append("")
    md.append("| File | Status | Last change (git) |")
    md.append("|---|---:|---|")
    for rel, st, dt in rows:
        md.append(f"| `{rel}` | {st} | {dt} |")
    md.append("")
    md.append("> Tip: Edit `apps/routers/ARCHIVE/watchlist.txt` to add/remove tracked files.")
    md.append("")

    status_md.write_text("\n".join(md), encoding="utf-8")
