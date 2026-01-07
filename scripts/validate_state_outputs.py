#!/usr/bin/env python3
"""
Validate state engine outputs before allowing external effects.

Checks:
- leads/issue-*/state.json is valid JSON
- STATUS.md exists and is non-empty
- (optional) ensure required keys exist in state.json

Exit codes:
0 = ok
1 = validation failed
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


REQUIRED_KEYS = ["issue", "customer", "state", "updated_utc", "service"]


def load_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_issue_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith("issue-")])


def validate_issue_dir(d: Path) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    state_path = d / "state.json"
    status_path = d / "STATUS.md"

    if not state_path.exists():
        errs.append(f"{d}: missing state.json")
        return False, errs

    data = load_json(state_path)
    if not data:
        errs.append(f"{d}: state.json is not valid JSON or is empty")
        return False, errs

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        errs.append(f"{d}: state.json missing required keys: {missing}")

    if not status_path.exists():
        errs.append(f"{d}: missing STATUS.md")
    else:
        txt = status_path.read_text(encoding="utf-8").strip()
        if len(txt) < 10:
            errs.append(f"{d}: STATUS.md is too short/empty")

    return len(errs) == 0, errs


def main() -> int:
    leads = Path("leads")
    issue_dirs = find_issue_dirs(leads)

    # If nothing exists yet, that's not catastrophic; treat as OK (no-op run).
    if not issue_dirs:
        print("STATE OUTPUT VALIDATION: OK (no leads/issue-* directories found)")
        return 0

    all_errs: List[str] = []
    ok_any = False

    for d in issue_dirs:
        ok, errs = validate_issue_dir(d)
        if ok:
            ok_any = True
        else:
            all_errs.extend(errs)

    # Require that at least one issue dir validates OR there are no errors.
    # (prevents a situation where everything is broken silently)
    if all_errs:
        print("STATE OUTPUT VALIDATION: FAILED")
        for e in all_errs:
            print(f"- {e}")
        return 1

    if not ok_any:
        print("STATE OUTPUT VALIDATION: FAILED (no valid issue dirs)")
        return 1

    print("STATE OUTPUT VALIDATION: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
