#!/usr/bin/env python3
"""
Tight output validation for StegOps state engine.

Validates ONLY the current issue directory based on GITHUB_EVENT_PATH:
  leads/issue-<N>/

Checks:
- Only allowed paths changed (default: leads/issue-<N>/...)
- state.json exists, valid JSON, required keys present
- schema_version present + correct
- state is known + does not regress compared to state.prev.json (if present)
- service is monthly|audit only
- STATUS.md exists, non-empty, references issue + correct state marker
- private_workspace link exists IFF state is deliverables_ready|deliverables_pushed
- verify-payment is two-factor: label verify-payment present AND comment intent from authorized actor
  (validator enforces label requirement; comment/auth enforced by state engine)
"""

from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_ORDER = [
    "new","replied","qualified","sow_generated","accepted","invoice_generated",
    "payment_claimed","verify_payment","payment_verified",
    "deliverables_ready","deliverables_pushed",
    "closed_no_response","closed",
]
STATE_RANK = {s: i for i, s in enumerate(STATE_ORDER)}

REQUIRED_KEYS = ["schema_version","issue","customer","state","updated_utc","service","labels","reasons"]

ALLOWED_SERVICES = {"monthly","audit"}

ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/issues/\d+/?$")
WORKSPACE_RE = re.compile(r"^https://github\.com/StegVerse-Labs/StegOps-Deliverables/tree/main/clients/issue-\d+/?$")

ALLOWED_EXTRA_PATH_PREFIXES: List[str] = []

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
        fail("Event payload missing issue.number")
    try:
        return int(n)
    except Exception:
        fail("issue.number is not an int")

def git_changed_files() -> List[str]:
    try:
        out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    except Exception as e:
        fail(f"Unable to run git status: {e}")
    files = []
    for line in out.splitlines():
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

    if int(data.get("schema_version")) != 1:
        fail(f"{state_path} schema_version must be 1")

    if int(data.get("issue")) != int(issue_num):
        fail(f"{state_path} issue mismatch: expected {issue_num}, got {data.get('issue')}")

    st = str(data.get("state") or "")
    if st not in STATE_RANK:
        fail(f"{state_path} has unknown state: {st}")

    svc = str(data.get("service") or "")
    if svc not in ALLOWED_SERVICES:
        fail(f"{state_path} service must be one of {sorted(ALLOWED_SERVICES)} (got {svc})")

    updated = str(data.get("updated_utc") or "")
    if "T" not in updated or not updated.endswith("Z"):
        fail(f"{state_path} updated_utc not in expected Zulu-ish ISO format: {updated}")

    issue_url = data.get("issue_url")
    if isinstance(issue_url, str) and issue_url.strip():
        u = issue_url.strip()
        if not ISSUE_URL_RE.match(u):
            fail(f"{state_path} issue_url does not look like a GitHub issue URL: {u}")

    labels = data.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        fail(f"{state_path} labels must be a list[str]")

    reasons = data.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(x, str) and x.strip() for x in reasons):
        fail(f"{state_path} reasons must be a non-empty list[str]")

    # Workspace link rule
    pw = data.get("private_workspace")
    if st in {"deliverables_ready","deliverables_pushed"}:
        if not isinstance(pw, str) or not WORKSPACE_RE.match(pw.strip()):
            fail(f"{state_path} private_workspace must be a valid Deliverables link when state={st}")
    else:
        if pw is not None:
            fail(f"{state_path} private_workspace must be null unless state is deliverables_ready|deliverables_pushed")

    # Two-factor verify-payment: if state indicates verified or beyond, label must include verify-payment
    if st in {"payment_verified","deliverables_ready","deliverables_pushed"}:
        if "verify-payment" not in set(labels):
            fail(f"{state_path} state={st} requires label 'verify-payment' (two-factor verify)")

    return data

def validate_status_md(issue_dir: Path, issue_num: int, state: str) -> None:
    status_path = issue_dir / "STATUS.md"
    if not status_path.exists():
        fail(f"Missing {status_path}")

    txt = status_path.read_text(encoding="utf-8").strip()
    if len(txt) < 60:
        fail(f"{status_path} is too short/empty")

    if f"#{issue_num}" not in txt:
        fail(f"{status_path} does not reference issue #{issue_num}")

    if f"**State:** `{state}`" not in txt:
        fail(f"{status_path} does not contain expected state marker for `{state}`")

def validate_no_regression(issue_dir: Path, current: Dict[str, Any]) -> None:
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

    validate_only_allowed_paths(str(issue_dir))

    # If it didn't produce outputs, treat as OK no-op (e.g., missing stegops label).
    if not issue_dir.exists():
        ok(f"No-op: {issue_dir} does not exist")

    data = validate_state_json(issue_dir, issue_num)
    validate_status_md(issue_dir, issue_num, str(data.get("state")))
    validate_no_regression(issue_dir, data)

    ok(f"Validated outputs for {issue_dir}")

if __name__ == "__main__":
    main()
