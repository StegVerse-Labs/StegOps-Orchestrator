#!/usr/bin/env python3
"""
Tight output validation for StegOps state engine.

Validates ONLY the current issue directory based on GITHUB_EVENT_PATH:
  leads/issue-<N>/

Checks:
- Only allowed paths changed (default: leads/issue-<N>/...)
- state.json exists, valid JSON, required keys present
- state.json.issue matches issue number
- state.json.issue_url (if present) looks like an issue URL
- STATUS.md exists, non-empty, and references the issue number and state
- State does not regress compared to previous state.json (if previous exists)

Exit codes:
0 = ok
1 = validation failed
"""

from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Keep aligned with scripts/state_engine.py
STATE_ORDER = [
    "new","replied","qualified","sow_generated","accepted","invoice_generated",
    "payment_claimed","verify_payment","payment_verified",
    "deliverables_ready","deliverables_pushed",
    "closed_no_response","closed",
]
STATE_RANK = {s: i for i, s in enumerate(STATE_ORDER)}

REQUIRED_KEYS = ["issue", "customer", "state", "updated_utc", "service"]

# By default, ONLY allow changes within the current issue directory.
# You can extend this allowlist later if needed.
ALLOWED_EXTRA_PATH_PREFIXES: List[str] = [
    # ".github/",  # uncomment only if you intentionally want workflow files to change at runtime (rare)
]

ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/issues/\d+/?$")

def fail(msg: str) -> None:
    print("STATE OUTPUT VALIDATION: FAILED")
    print(msg)
    sys.exit(1)

def ok(msg: str) -> None:
    print("STATE OUTPUT VALIDATION: OK")
    print(msg)
    sys.exit(0)

def load_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def get_issue_number_from_event() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        fail("GITHUB_EVENT_PATH not set")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"Unable to read event payload: {e}")

    issue = event.get("issue") or {}
    n = issue.get("number")
    if not n:
        # Some events use github.event.number; but our triggers are issues & issue_comment.
        fail("Event payload missing issue.number")
    try:
        return int(n)
    except Exception:
        fail("issue.number is not an int")

def git_changed_files() -> List[str]:
    # Porcelain is stable for parsing
    try:
        out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    except Exception as e:
        fail(f"Unable to run git status: {e}")
    files = []
    for line in out.splitlines():
        # Format: XY <path>
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if path:
            files.append(path)
    return files

def state_rank(s: str) -> int:
    return STATE_RANK.get(s, -1)

def validate_only_allowed_paths(issue_dir: str) -> None:
    changed = git_changed_files()
    if not changed:
        # It's okay to have no changes: engine may no-op.
        return

    allowed_prefix = issue_dir.rstrip("/") + "/"
    for p in changed:
        if p.startswith(allowed_prefix):
            continue
        if any(p.startswith(pref) for pref in ALLOWED_EXTRA_PATH_PREFIXES):
            continue
        fail(
            "Unexpected file changes outside the current issue directory.\n"
            f"Allowed: {allowed_prefix}*\n"
            f"Changed: {changed}"
        )

def validate_state_json(issue_dir: Path, issue_num: int) -> Dict[str, Any]:
    state_path = issue_dir / "state.json"
    if not state_path.exists():
        fail(f"Missing {state_path}")

    data = load_json(state_path)
    if data is None:
        fail(f"{state_path} is not valid JSON")

    for k in REQUIRED_KEYS:
        if k not in data:
            fail(f"{state_path} missing required key: {k}")

    # Issue number must match folder and event
    if int(data.get("issue")) != int(issue_num):
        fail(f"{state_path} issue mismatch: expected {issue_num}, got {data.get('issue')}")

    # State must be known
    st = str(data.get("state") or "")
    if st not in STATE_RANK:
        fail(f"{state_path} has unknown state: {st}")

    # updated_utc should look ISO-ish (very loose check)
    updated = str(data.get("updated_utc") or "")
    if "T" not in updated or not updated.endswith("Z"):
        fail(f"{state_path} updated_utc not in expected Zulu-ish ISO format: {updated}")

    # Optional: issue_url sanity
    issue_url = data.get("issue_url")
    if isinstance(issue_url, str) and issue_url.strip():
        u = issue_url.strip()
        if not ISSUE_URL_RE.match(u):
            fail(f"{state_path} issue_url does not look like a GitHub issue URL: {u}")

    return data

def validate_status_md(issue_dir: Path, issue_num: int, state: str) -> None:
    status_path = issue_dir / "STATUS.md"
    if not status_path.exists():
        fail(f"Missing {status_path}")

    txt = status_path.read_text(encoding="utf-8").strip()
    if len(txt) < 40:
        fail(f"{status_path} is too short/empty")

    # Must mention issue number
    if f"#{issue_num}" not in txt:
        fail(f"{status_path} does not reference issue #{issue_num}")

    # Must contain a state line with the computed state
    # Your renderer uses: **State:** `<state>`
    if f"**State:** `{state}`" not in txt:
        fail(f"{status_path} does not contain expected state marker for `{state}`")

def validate_no_regression(issue_dir: Path, current: Dict[str, Any]) -> None:
    # Compare with previous if available in git history (HEAD~1) OR via working tree backup.
    # We'll do a simple local check: if a .prev_state.json exists, compare.
    # (Optional future: fetch from git show if needed.)
    prev_path = issue_dir / "state.prev.json"
    if not prev_path.exists():
        return

    prev = load_json(prev_path)
    if prev is None:
        fail(f"{prev_path} exists but is not valid JSON")

    prev_state = str(prev.get("state") or "")
    cur_state = str(current.get("state") or "")

    if prev_state in STATE_RANK and cur_state in STATE_RANK:
        if state_rank(cur_state) < state_rank(prev_state):
            fail(f"State regression detected: {prev_state} -> {cur_state}")

def main() -> None:
    issue_num = get_issue_number_from_event()
    issue_dir = Path("leads") / f"issue-{issue_num}"

    # Enforce that only this issue directory is dirtied
    validate_only_allowed_paths(str(issue_dir))

    # If directory doesn't exist, treat as OK no-op (engine may have early-returned)
    if not issue_dir.exists():
        ok(f"No-op: {issue_dir} does not exist (likely missing 'stegops' label or issue number)")

    data = validate_state_json(issue_dir, issue_num)
    validate_status_md(issue_dir, issue_num, str(data.get("state")))
    validate_no_regression(issue_dir, data)

    ok(f"Validated outputs for {issue_dir}")

if __name__ == "__main__":
    main()
