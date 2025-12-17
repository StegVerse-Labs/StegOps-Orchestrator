#!/usr/bin/env python3
"""
StegOps State Engine (with locking + payment verification + deliverables states)

Writes:
- leads/issue-<n>/state.json
- leads/issue-<n>/STATUS.md

Locking:
- Atomic mkdir lock: leads/issue-<n>/.lock/
- Prevents concurrent writes / retry races

State improvements:
- payment_claimed (client said PAID)
- verify_payment (internal action needed)
- payment_verified (operator verified payment)
- deliverables_ready (post-verify, pre-push)
- deliverables_pushed (pushed to private deliverables repo)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
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
    body = (issue_body or "").lower()
    if "monthly ops support" in body:
        return "monthly"
    if "one-time ai ops audit" in body:
        return "audit"
    return None


def parse_comment_intents(comment_body: str) -> Tuple[bool, bool, bool, bool]:
    """
    Returns (is_yes, is_accept, is_paid_claim, is_verify_payment)
    """
    c = (comment_body or "").strip().lower()
    is_yes = bool(re.match(r"^(yes|y|yep|yeah|sure|ok|okay|lets do it|let’s do it)\b", c))
    is_accept = bool(re.match(r"^(accept|accepted|i accept)\b", c))
    is_paid_claim = bool(re.match(r"^(paid|payment sent|sent payment)\b", c))
    is_verify_payment = bool(re.match(r"^verify payment\b", c))
    return is_yes, is_accept, is_paid_claim, is_verify_payment


def choose_amount_default(service: str) -> str:
    return "$99 / month" if service == "monthly" else "$2,500 USD"


def state_rank(state: str) -> int:
    # Monotonic progression. States later in the list "win".
    order = [
        "new",
        "replied",
        "qualified",
        "sow_generated",
        "accepted",
        "invoice_generated",
        "payment_claimed",
        "verify_payment",
        "payment_verified",
        "deliverables_ready",
        "deliverables_pushed",
        "closed_no_response",
        "closed",
    ]
    try:
        return order.index(state)
    except ValueError:
        return 0


def max_state(a: str, b: str) -> str:
    return a if state_rank(a) >= state_rank(b) else b


def is_authorized_assoc(author_association: str) -> bool:
    a = (author_association or "").strip().upper()
    return a in {"OWNER", "MEMBER", "COLLABORATOR"}


# ---------------------------
# Locking (atomic mkdir)
# ---------------------------

class IssueLock:
    """
    Atomic lock via mkdir.
    - acquire() creates lock dir
    - release() removes it
    """

    def __init__(self, lock_dir: Path, timeout_sec: int = 30, poll_ms: int = 200) -> None:
        self.lock_dir = lock_dir
        self.timeout_sec = timeout_sec
        self.poll_ms = poll_ms

    def acquire(self) -> bool:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            try:
                self.lock_dir.mkdir(parents=True, exist_ok=False)
                marker = self.lock_dir / "lock.json"
                safe_write_json(marker, {
                    "acquired_utc": utc_now_iso(),
                    "runner": os.getenv("GITHUB_RUN_ID", "local"),
                    "event": os.getenv("GITHUB_EVENT_NAME", "unknown"),
                })
                return True
            except FileExistsError:
                time.sleep(self.poll_ms / 1000.0)
        return False

    def release(self) -> None:
        if self.lock_dir.exists():
            shutil.rmtree(self.lock_dir, ignore_errors=True)


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
    last_comment_author_assoc: Optional[str]


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
    last_comment_author_assoc = comment.get("author_association") if comment else None

    return IssueContext(
        number=number,
        author=author,
        title=title,
        url=url,
        state=state,
        labels=labels,
        body=body,
        last_comment_body=last_comment_body,
        last_comment_author_assoc=last_comment_author_assoc,
    )


# ---------------------------
# State Engine
# ---------------------------

def compute_next_state(ctx: IssueContext, prev: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now_iso()
    current_state = prev.get("state") or "new"

    # Service inference
    service = prev.get("service") or parse_service_from_issue_body(ctx.body) or "audit"
    if "monthly" in ctx.labels:
        service = "monthly"
    if "audit" in ctx.labels:
        service = "audit"

    out: Dict[str, Any] = dict(prev) if prev else {}
    out.setdefault("issue", ctx.number)
    out.setdefault("customer", ctx.author)
    out.setdefault("issue_url", ctx.url)
    out.setdefault("issue_title", ctx.title)

    out["service"] = service
    out["open_state"] = ctx.state
    out["labels"] = sorted(set(ctx.labels))
    out["updated_utc"] = now

    ts = out.get("timestamps") or {}
    if not isinstance(ts, dict):
        ts = {}
    out["timestamps"] = ts

    # Comment intents
    is_yes = is_accept = is_paid_claim = is_verify_payment = False
    verify_authorized = False

    if ctx.last_comment_body is not None:
        is_yes, is_accept, is_paid_claim, is_verify_payment = parse_comment_intents(ctx.last_comment_body)
        if is_verify_payment:
            verify_authorized = is_authorized_assoc(ctx.last_comment_author_assoc or "")

    # Observed state from facts (labels + intents)
    observed = "new"

    if ctx.last_comment_body is not None:
        observed = max_state(observed, "replied")

    if "qualified" in ctx.labels or is_yes:
        observed = max_state(observed, "qualified")

    if "sow-generated" in ctx.labels:
        observed = max_state(observed, "sow_generated")

    if is_accept:
        observed = max_state(observed, "accepted")

    if "invoice-generated" in ctx.labels:
        observed = max_state(observed, "invoice_generated")

    # Payment claim (client)
    if "payment-claimed" in ctx.labels or is_paid_claim:
        observed = max_state(observed, "payment_claimed")
        observed = max_state(observed, "verify_payment")  # internal action needed after claim

    # Payment verification (operator)
    if is_verify_payment and verify_authorized:
        observed = max_state(observed, "payment_verified")
        observed = max_state(observed, "deliverables_ready")

    # Deliverables pushed (private repo)
    if "deliverables-pushed" in ctx.labels:
        observed = max_state(observed, "deliverables_pushed")

    # Closing states
    if ctx.state == "closed":
        if "no-response" in ctx.labels:
            observed = max_state(observed, "closed_no_response")
        else:
            observed = max_state(observed, "closed")

    # Monotonic overall state
    out["state"] = max_state(current_state, observed)

    # Milestone timestamps (first time reached)
    def mark(milestone: str, condition: bool) -> None:
        if condition and milestone not in ts:
            ts[milestone] = now

    mark("replied", ctx.last_comment_body is not None)
    mark("qualified", ("qualified" in ctx.labels) or is_yes)
    mark("sow_generated", "sow-generated" in ctx.labels)
    mark("accepted", is_accept)
    mark("invoice_generated", "invoice-generated" in ctx.labels)

    mark("payment_claimed", ("payment-claimed" in ctx.labels) or is_paid_claim)
    mark("verify_payment", (("payment-claimed" in ctx.labels) or is_paid_claim))
    mark("payment_verified", is_verify_payment and verify_authorized)
    mark("deliverables_ready", is_verify_payment and verify_authorized)
    mark("deliverables_pushed", "deliverables-pushed" in ctx.labels)

    if is_verify_payment and not verify_authorized:
        # Track unauthorized attempts without advancing state
        out.setdefault("security_events", [])
        if isinstance(out["security_events"], list):
            out["security_events"].append({
                "utc": now,
                "type": "verify_payment_denied",
                "author_association": (ctx.last_comment_author_assoc or "UNKNOWN"),
            })

    if ctx.state == "closed" and "no-response" in ctx.labels:
        mark("closed_no_response", True)
    if ctx.state == "closed" and "no-response" not in ctx.labels:
        mark("closed", True)

    # Default pricing hints (display only; invoice workflows decide actual)
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

    # Next step guidance
    if s in ("new", "replied"):
        next_step = "Reply **YES** to proceed and include repo link(s)."
    elif s == "qualified":
        next_step = "Provide repo link(s) + scope. We’ll generate a draft SOW."
    elif s == "sow_generated":
        next_step = "Reply **ACCEPT** to confirm scope and generate invoice."
    elif s == "accepted":
        next_step = "Invoice should be generated automatically."
    elif s == "invoice_generated":
        next_step = "When payment is sent, reply **PAID**."
    elif s in ("payment_claimed", "verify_payment"):
        next_step = "Internal: comment **VERIFY PAYMENT** once payment is confirmed."
    elif s == "payment_verified":
        next_step = "Payment verified. Deliverables workspace is being prepared."
    elif s == "deliverables_ready":
        next_step = "Deliverables are ready; pushing to the private deliverables repo."
    elif s == "deliverables_pushed":
        next_step = "Private deliverables workspace is live. Work proceeds asynchronously there."
    else:
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

- Payment Claimed: {fmt("payment_claimed")}
- Verify Payment (requested): {fmt("verify_payment")}
- Payment Verified: {fmt("payment_verified")}
- Deliverables Ready: {fmt("deliverables_ready")}
- Deliverables Pushed: {fmt("deliverables_pushed")}

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

    # Only operate on StegOps issues
    if "stegops" not in ctx.labels:
        print("Not a stegops issue; skipping.")
        return 0

    if ctx.number <= 0:
        print("No issue number detected; skipping.")
        return 0

    lead_dir = Path("leads") / f"issue-{ctx.number}"
    state_path = lead_dir / "state.json"
    status_path = lead_dir / "STATUS.md"

    lock = IssueLock(lead_dir / ".lock", timeout_sec=45, poll_ms=250)
    if not lock.acquire():
        print("Could not acquire lock in time; exiting safely.")
        return 0

    try:
        prev = safe_read_json(state_path)
        next_state_obj = compute_next_state(ctx, prev)
        safe_write_json(state_path, next_state_obj)
        safe_write_text(status_path, render_status_md(next_state_obj))
        print(f"Updated {state_path} and {status_path}")
    finally:
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
