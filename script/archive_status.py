#!/usr/bin/env python3
import json
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
    out = _run(["git", "log", "-1", "--format=%ct", "--", rel_path], cwd=repo)
    if not out:
        return None
    return int(out)

def _read_watchlist(watchlist_path: Path) -> list[str]:
    if not watchlist_path.exists():
        return []
    lines = watchlist_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    items: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s)
    return items

def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {
            "last_run_utc": None,
            "last_run_summary": "",
            "last_run_counts": {"processed": 0, "archived": 0, "active": 0}
        }
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_run_utc": None,
            "last_run_summary": "",
            "last_run_counts": {"processed": 0, "archived": 0, "active": 0}
        }

def _save_state(state_path: Path, state: dict):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

def _fmt_utc(epoch: int | None) -> str:
    if epoch is None:
        return "None"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def write_status_md(
    repo: Path,
    status_md: Path,
    watchlist_path: Path,
    state_path: Path,
    this_run_epoch: int,
    this_run_counts: dict,
    this_run_summary_lines: list[str],
):
    items = _read_watchlist(watchlist_path)

    prev = _load_state(state_path)
    prev_run_epoch = prev.get("last_run_utc")
    prev_counts = prev.get("last_run_counts", {"processed": 0, "archived": 0, "active": 0})
    prev_summary = (prev.get("last_run_summary") or "").strip()

    def _get(d, k):
        try:
            return int(d.get(k, 0))
        except Exception:
            return 0

    rows = []
    for rel in items:
        ts = _git_last_commit_epoch(repo, rel)
        if ts is None:
            rows.append((rel, "❓ MISSING", "—"))
            continue
        dt = _fmt_utc(ts)
        if ts >= this_run_epoch:
            rows.append((rel, "✅ UP TO DATE", dt))
        else:
            rows.append((rel, "⚠️ STALE", dt))

    deltas = {
        "processed": _get(this_run_counts, "processed") - _get(prev_counts, "processed"),
        "archived": _get(this_run_counts, "archived") - _get(prev_counts, "archived"),
        "active": _get(this_run_counts, "active") - _get(prev_counts, "active"),
    }

    status_md.parent.mkdir(parents=True, exist_ok=True)

    md = []
    md.append("# StegOps-Orchestrator Status")
    md.append("")
    md.append(f"- **Last run (anchor):** {_fmt_utc(this_run_epoch)}")
    md.append(f"- Previous run: {_fmt_utc(prev_run_epoch) if prev_run_epoch else 'None'}")
    md.append("")
    md.append("## Since last run")
    md.append("")
    md.append(f"- Processed: **{_get(this_run_counts, 'processed')}** (Δ {deltas['processed']:+d})")
    md.append(f"- Archived: **{_get(this_run_counts, 'archived')}** (Δ {deltas['archived']:+d})")
    md.append(f"- Active: **{_get(this_run_counts, 'active')}** (Δ {deltas['active']:+d})")
    md.append("")
    md.append("## This run summary")
    md.append("")
    if this_run_summary_lines:
        for line in this_run_summary_lines[:2]:
            md.append(f"- {line}")
    else:
        md.append("- No new inbox items this run.")
    md.append("")

    if prev_summary:
        md.append("## Previous run summary (for continuity)")
        md.append("")
        md.append(f"- {prev_summary.splitlines()[0][:200]}")
        md.append("")

    md.append("## Watched files vs last run anchor")
    md.append("")
    md.append("| File | Status | Last change (git) |")
    md.append("|---|---:|---|")
    for rel, st, dt in rows:
        md.append(f"| `{rel}` | {st} | {dt} |")
    md.append("")
    md.append("> Tip: Edit `apps/routers/ARCHIVE/watchlist.txt` to add/remove tracked files.")
    md.append("")

    status_md.write_text("\n".join(md), encoding="utf-8")

    new_state = {
        "last_run_utc": this_run_epoch,
        "last_run_summary": "\n".join(this_run_summary_lines[:2]).strip(),
        "last_run_counts": {
            "processed": _get(this_run_counts, "processed"),
            "archived": _get(this_run_counts, "archived"),
            "active": _get(this_run_counts, "active"),
        },
    }
    _save_state(state_path, new_state)
