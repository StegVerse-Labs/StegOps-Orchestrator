#!/usr/bin/env python3
"""
StegOps State Engine

Writes a single source of truth per customer engagement:
- leads/issue-<n>/state.json
- leads/issue-<n>/STATUS.md

Runs from GitHub Actions using GITHUB_EVENT_PATH event payload.

Design goals:
- Idempotent (safe to run repeatedly)
- No secrets required
- GitHub-native (files + commits + labels)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------
# Helpers
# ---------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def norm_labels(labels: List[Dict[str, Any]]) -> List[str]:
    out = []
    for l in labels or []:
        name = (l.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def first_line(s: str, max_len: int = 160) -> str:
    s = (s or "").strip().splitlines()[0] if s else ""
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def parse_service_from_issue_body(issue_body: str) -> Optional[str]:
    """
    Looks for the Issue Template dropdown text. This is intentionally simple and robust.
    Returns: "monthly" | "audit" | None
    """
    body = (issue_body or "").lower()
    if "monthly ops support" in body:
        return "monthly"
    if "one-time ai ops audit" in body:
        return "audit"
    return None


def parse_intent_from_comment(comment_body: str) -> Tuple[bool, bool, bool]:
    """
    Returns (is_yes, is_accept, is_paid)
    """
    c = (comment_body or "").strip().lower()

    is_yes = bool(re.match(r"^(yes|y|yep|yeah|sure|ok|okay|lets do it|let’s do it)\b", c))
    is_accept = bool(re.match(r"^(accept|accepted|i accept)\b", c))
    is_paid = bool(re.match(r"^(paid|payment sent|sent payment)\b", c))

    return is_yes, is_accept, is_paid


def choose_amount_default(service: str) -> str:
    if service == "monthly":
        return "$99 / month"
    return "$2,500 USD"


def state_rank(state: str) -> int:
    order = [
        "new",
        "replied",
        "qualified",
        "sow_generated",
        "accepted",
        "invoice_generated",
        "paid",
        "closed_no_response",
        "closed",
    ]
    try:
        return order.index(state)
    except ValueError:
        return 0


def max_state(a: str, b: str) -> str:
    return a if state_rank(a) >= state_rank(b) else b


# ---------------------------
# Model
# ---------------------------

@dataclass
class IssueContext:
    number: int
    author: str
    title: str
    url: str
    state: str  # open/closed
    labels: List[str]
    body: str
    last_comment_body: Optional[str]
    event_name: str


def load_event(event_path: Path) -> Dict[str, Any]:
    return json.loads(event_path.read_text(encoding="utf-8"))


def extract_issue_context(event: Dict[str, Any]) -> IssueContext:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}

    number = int(issue.get("number") or 0)
    author = (issue.get("user") or {}).get("login") or "unknown"
    title = issue.get("title") or ""
    url = issue.get("html_url") or ""
    state = issue.get("state") or "open"
    labels = norm_labels(issue.get("labels") or [])
    body = issue.get("body") or ""
    last_comment_body = comment.get("body") if comment else None

    event_name = os.getenv("GITHUB_EVENT_NAME", "unknown")

    return IssueContext(
        number=number,
        author=author,
        title=title,
        url=url,
        state=state,
        labels=labels,
        body=body,
        last_comment_body=last_comment_body,
        event_name=event_name,
    )


# ---------------------------
# State Engine
# ---------------------------

def compute_next_state(ctx: IssueContext, prev: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute and persist a stable engagement state.
    - Only ever *advances* milestone timestamps when first observed.
    - Allows closing states for no-response/closed.
    """
    now = utc_now_iso()

    # Base state
    current_state = prev.get("state") or "new"

    # Service selection inference
    service = prev.get("service") or parse_service_from_issue_body(ctx.body) or "audit"

    # If we later add explicit labels "monthly" or "audit", honor them:
    if "monthly" in ctx.labels:
        service = "monthly"
    if "audit" in ctx.labels:
        service = "audit"

    # Track last seen metadata
    out: Dict[str, Any] = dict(prev) if prev else {}
    out.setdefault("issue", ctx.number)
    out.setdefault("customer", ctx.author)
    out.setdefault("issue_url", ctx.url)
    out.setdefault("issue_title", ctx.title)

    out["service"] = service
    out["open_state"] = ctx.state
    out["labels"] = sorted(set(ctx.labels))
    out["updated_utc"] = now

    # timestamps bucket
    ts = out.get("timestamps") or {}
    if not isinstance(ts, dict):
        ts = {}
    out["timestamps"] = ts

    # Comment intent
    is_yes = is_accept = is_paid = False
    if ctx.last_comment_body is not None:
        is_yes, is_accept, is_paid = parse_intent_from_comment(ctx.last_comment_body)

    # Determine milestone states from observed facts
    observed = "new"

    # "replied" if there is any comment payload and it's on a stegops issue
    if ctx.last_comment_body is not None:
        observed = max_state(observed, "replied")

    # qualified label OR YES implies qualified
    if "qualified" in ctx.labels or is_yes:
        observed = max_state(observed, "qualified")

    # sow-generated label implies sow_generated
    if "sow-generated" in ctx.labels:
        observed = max_state(observed, "sow_generated")

    # ACCEPT comment implies accepted
    if is_accept:
        observed = max_state(observed, "accepted")

    # invoice-generated label implies invoice_generated
    if "invoice-generated" in ctx.labels:
        observed = max_state(observed, "invoice_generated")

    # PAID comment implies paid
    if is_paid:
        observed = max_state(observed, "paid")

    # Closing states
    if ctx.state == "closed":
        # If it was auto-closed due to no response, mark explicitly
        if "no-response" in ctx.labels:
            observed = max_state(observed, "closed_no_response")
        else:
            observed = max_state(observed, "closed")

    # Advance overall state monotonically
    next_state = max_state(current_state, observed)
    out["state"] = next_state

    # Set milestone timestamps if newly reached
    def mark(milestone: str, condition: bool) -> None:
        if condition and milestone not in ts:
            ts[milestone] = now

    mark("replied", ctx.last_comment_body is not None)
    mark("qualified", ("qualified" in ctx.labels) or is_yes)
    mark("sow_generated", "sow-generated" in ctx.labels)
    mark("accepted", is_accept)
    mark("invoice_generated", "invoice-generated" in ctx.labels)
    mark("paid", is_paid)
    if ctx.state == "closed" and "no-response" in ctx.labels:
        mark("closed_no_response", True)
    if ctx.state == "closed" and "no-response" not in ctx.labels:
        mark("closed", True)

    # Default pricing (used for STATUS display; can be overridden by your invoice workflow)
    out.setdefault("pricing_defaults", {})
    if not isinstance(out["pricing_defaults"], dict):
        out["pricing_defaults"] = {}
    out["pricing_defaults"]["suggested_amount"] = choose_amount_default(service)

    return out


def render_status_md(state: Dict[str, Any]) -> str:
    issue = state.get("issue", "?")
    customer = state.get("customer", "unknown")
    issue_url = state.get("issue_url", "")
    title = state.get("issue_title", "")
    s = state.get("state", "new")
    service = state.get("service", "audit")
    amount = (state.get("pricing_defaults") or {}).get("suggested_amount", "")

    ts = state.get("timestamps") or {}
    def fmt(k: str) -> str:
        return ts.get(k, "—")

    pretty_service = "Monthly Ops Support" if service == "monthly" else "One-time AI Ops Audit"

    # next step guidance by state
    next_step = ""
    if s in ("new", "replied"):
        next_step = "Reply **YES** to proceed and include repo link(s)."
    elif s == "qualified":
        next_step = "Provide repo link(s) + scope. We’ll generate a draft SOW."
    elif s == "sow_generated":
        next_step = "Reply **ACCEPT** to confirm scope and generate invoice."
    elif s == "accepted":
        next_step = "Invoice should be generated automatically (or request `invoice`)."
    elif s == "invoice_generated":
        next_step = "Complete payment and reply **PAID**."
    elif s == "paid":
        next_step = "Engagement is active. Deliverables will be produced asynchronously."
    elif s in ("closed_no_response", "closed"):
        next_step = "Reply **YES** to reopen and continue."

    md = f"""# Engagement Status

**Issue:** #{issue} — {first_line(title)}
**Customer:** @{customer}
**Issue URL:** {issue_url}

---

## Current
- **State:** `{s}`
- **Service:** {pretty_service}
- **Default Amount:** {amount}

---

## Timeline (UTC)
- Replied: {fmt("replied")}
- Qualified: {fmt("qualified")}
- SOW Generated: {fmt("sow_generated")}
- Accepted: {fmt("accepted")}
- Invoice Generated: {fmt("invoice_generated")}
- Paid: {fmt("paid")}
- Closed (no response): {fmt("closed_no_response")}
- Closed: {fmt("closed")}

---

## Next Step
{next_step}
"""
    return md


def main() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH not set.")
        return 2

    event = load_event(Path(event_path))
    ctx = extract_issue_context(event)

    # Only operate when this is a StegOps issue
    if "stegops" not in ctx.labels:
        print("Not a stegops issue; skipping.")
        return 0

    if ctx.number <= 0:
        print("No issue number detected; skipping.")
        return 0

    lead_dir = Path("leads") / f"issue-{ctx.number}"
    state_path = lead_dir / "state.json"
    status_path = lead_dir / "STATUS.md"

    prev = safe_read_json(state_path)
    next_state_obj = compute_next_state(ctx, prev)

    safe_write_json(state_path, next_state_obj)
    safe_write_text(status_path, render_status_md(next_state_obj))

    print(f"Updated {state_path} and {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
