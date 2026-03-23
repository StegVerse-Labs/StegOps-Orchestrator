#!/usr/bin/env python3
"""
Event Ledger + Replay Protection
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

LEDGER_FILE = "ledger.jsonl"


def _ledger_path(base: Path) -> Path:
    return base / LEDGER_FILE


def has_event(base: Path, event_id: str) -> bool:
    path = _ledger_path(base)
    if not path.exists():
        return False

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get("event_id") == event_id:
                        return True
                except Exception:
                    continue
    except Exception:
        return False

    return False


def append_event(base: Path, record: Dict[str, Any]) -> None:
    path = _ledger_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
