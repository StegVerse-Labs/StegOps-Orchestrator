#!/usr/bin/env python3
"""
StegOps State Engine
- locking
- payment verification (two-factor: label + authorized comment intent)
- deliverables states
- private workspace link (read-only, no secrets)
- schema_version + reasons for long-term auditability
- idempotent writes to avoid noisy commits
"""

from __future__ import annotations
import hashlib
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
# Label constants (single source of truth)
# ---------------------------

LABEL_STEGOPS = "stegops"
LABEL_MONTHLY = "monthly"
LABEL_AUDIT = "audit"
LABEL_QUALIFIED = "qualified"
LABEL_SOW = "sow-generated"
LABEL_INVOICE = "invoice-generated"
LABEL_PAYMENT_CLAIMED = "payment-claimed"
LABEL_DELIVERABLES_PUSHED = "deliverables-pushed"

# Two-factor verify payment: requires this label PLUS authorized comment intent
LABEL_VERIFY_PAYMENT = "verify-payment"

# ---------------------------
# State model
# ---------------------------

STATE_ORDER = [
    "new","replied","qualified","sow_generated","accepted","invoice_generated",
    "payment_claimed","verify_payment","payment_verified",
    "deliverables_ready","deliverables_pushed",
    "closed_no_response","closed",
]
STATE_RANK = {s: i for i, s in enumerate(STATE_ORDER)}

SCHEMA_VERSION = 1

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

def canonical_hash(obj: Dict[str, Any]) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def norm_labels(labels: List[Dict[str, Any]]) -> List[str]:
    return sorted({(l.get("name") or "").strip() for l in labels or [] if l.get("name")})

def first_line(s: str, max_len: int = 160) -> str:
    s = (s or "").strip().splitlines()[0] if s else ""
    return s if len(s) <= max_len else s[: max_len - 1] + "…"

def parse_service_from_issue_body(body: str) -> Optional[str]:
    b = (body or "").lower()
    if "monthly ops support" in b:
        return "monthly"
    if "one-time ai ops audit" in b:
        return "audit"
    return None

def parse_comment_intents(body: str) -> Tuple[bool, bool, bool, bool]:
    c = (body or "").strip().lower()
    return (
        bool(re.match(r"^(yes|y|sure|ok|let’s do it|lets do it)\b", c)),
        bool(re.match(r"^(accept|accepted|i accept)\b", c)),
        bool(re.match(r"^(paid|payment sent|sent payment)\b", c)),
        bool(re.match(r"^verify payment\b", c)),
    )

def choose_amount_default(service: str) -> str:
    return "$99 / month" if service == "monthly" else "$2,500 USD"

def is_authorized_assoc(a: str) -> bool:
    return (a or "").upper() in {"OWNER", "MEMBER", "COLLABORATOR"}

def state_rank(s: str) -> int:
    return STATE_RANK.get(s, 0)

def max_state(a: str, b: str) -> str:
    return a if state_rank(a) >= state_rank(b) else b

# ---------------------------
# Lock
# ---------------------------

class IssueLock:
    def __init__(self, d: Path, timeout=45, poll=250):
        self.d, self.timeout, self.poll = d, timeout, poll

    def acquire(self) -> bool:
        end = time.time() + self.timeout
        while time.time() < end:
            try:
                self.d.mkdir(parents=True, exist_ok=False)
                safe_write_json(self.d / "lock.json", {"utc": utc_now_iso()})
                return True
            except FileExistsError:
                time.sleep(self.poll / 1000)
        return False

    def release(self):
        if self.d.exists():
            shutil.rmtree(self.d, ignore_errors=True)

# ---------------------------
# Context
# ---------------------------

@dataclass
class IssueContext:
    number: int
    author: str
    title: str
    url: str
    state: str          # open / closed
    labels: List[str]
    body: str
    comment: Optional[str]
    assoc: Optional[str]

def extract_ctx(event: Dict[str, Any]) -> IssueContext:
    i, c = event.get("issue") or {}, event.get("comment") or {}
    return IssueContext(
        number=int(i.get("number") or 0),
        author=(i.get("user") or {}).get("login") or "unknown",
        title=i.get("title") or "",
        url=i.get("html_url") or "",
        state=i.get("state") or "open",
        labels=norm_labels(i.get("labels") or []),
        body=i.get("body") or "",
        comment=c.get("body"),
        assoc=c.get("author_association"),
    )

# ---------------------------
# State computation
# ---------------------------

def compute_state(ctx: IssueContext, prev: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now_iso()
    reasons: List[str] = []
    prev_state = (prev.get("state") or "new") if prev else "new"

    # Source of truth: labels > previous > body inference (only as fallback)
    service = prev.get("service") or parse_service_from_issue_body(ctx.body) or "audit"
    if LABEL_MONTHLY in ctx.labels:
        service = "monthly"
        reasons.append("service_labeled_monthly")
    if LABEL_AUDIT in ctx.labels:
        service = "audit"
        reasons.append("service_labeled_audit")

    out = dict(prev) if prev else {}
    out.update({
        "schema_version": SCHEMA_VERSION,
        "issue": ctx.number,
        "customer": ctx.author,
        "issue_url": ctx.url,
        "issue_title": ctx.title,
        "service": service,
        "labels": ctx.labels,
        "updated_utc": now,
    })

    ts = out.setdefault("timestamps", {})
    yes = accept = paid = verify_intent = False
    if ctx.comment:
        yes, accept, paid, verify_intent = parse_comment_intents(ctx.comment)
        reasons.append("comment_detected")

    observed = "new"

    if ctx.comment:
        observed = max_state(observed, "replied")
        reasons.append("observed_replied")

    if LABEL_QUALIFIED in ctx.labels or yes:
        observed = max_state(observed, "qualified")
        reasons.append("observed_qualified")

    if LABEL_SOW in ctx.labels:
        observed = max_state(observed, "sow_generated")
        reasons.append("observed_sow_generated")

    if accept:
        observed = max_state(observed, "accepted")
        reasons.append("observed_accepted")

    if LABEL_INVOICE in ctx.labels:
        observed = max_state(observed, "invoice_generated")
        reasons.append("observed_invoice_generated")

    if paid or LABEL_PAYMENT_CLAIMED in ctx.labels:
        observed = max_state(observed, "payment_claimed")
        observed = max_state(observed, "verify_payment")
        reasons.append("observed_payment_claimed")

    # Two-factor verify payment:
    #  1) authorized association
    #  2) comment intent "verify payment"
    #  3) label "verify-payment" present
    verify_authorized = verify_intent and is_authorized_assoc(ctx.assoc) and (LABEL_VERIFY_PAYMENT in ctx.labels)
    if verify_authorized:
        observed = max_state(observed, "payment_verified")
        observed = max_state(observed, "deliverables_ready")
        reasons.append("observed_payment_verified_two_factor")

    if LABEL_DELIVERABLES_PUSHED in ctx.labels:
        observed = max_state(observed, "deliverables_pushed")
        reasons.append("observed_deliverables_pushed")

    # Explicit close handling
    if (ctx.state or "").lower() == "closed":
        # If they never made it past replied/qualified/etc., you can decide to mark no-response.
        # Conservative rule: if still early, mark closed_no_response; else closed.
        early_threshold = state_rank("qualified")
        if state_rank(prev_state) <= early_threshold and state_rank(observed) <= early_threshold:
            observed = max_state(observed, "closed_no_response")
            reasons.append("observed_closed_no_response")
        else:
            observed = max_state(observed, "closed")
            reasons.append("observed_closed")

    out["state"] = max_state(prev_state, observed)

    def mark(k: str, cond: bool):
        if cond and k not in ts:
            ts[k] = now

    mark("qualified", (LABEL_QUALIFIED in ctx.labels) or yes)
    mark("accepted", accept)
    mark("invoice_generated", LABEL_INVOICE in ctx.labels)
    mark("payment_claimed", paid or (LABEL_PAYMENT_CLAIMED in ctx.labels))
    mark("payment_verified", verify_authorized)
    mark("deliverables_pushed", LABEL_DELIVERABLES_PUSHED in ctx.labels)

    out.setdefault("pricing_defaults", {})["suggested_amount"] = choose_amount_default(service)

    # Workspace link rule: only when ready/pushed
    out["private_workspace"] = (
        f"https://github.com/StegVerse-Labs/StegOps-Deliverables/tree/main/clients/issue-{ctx.number}"
        if out["state"] in {"deliverables_ready", "deliverables_pushed"}
        else None
    )

    # Reasons for auditability
    # Keep unique + stable ordering
    out["reasons"] = sorted(set(reasons))

    return out

# ---------------------------
# STATUS renderer
# ---------------------------

def render_status(s: Dict[str, Any]) -> str:
    pw = s.get("private_workspace")
    link = f"\n🔒 **Private Workspace:** {pw}\n" if pw else ""
    reasons = s.get("reasons") or []
    reasons_block = ""
    if reasons:
        reasons_block = "\n**Reasons:**\n" + "\n".join([f"- {r}" for r in reasons]) + "\n"

    return f"""# Engagement Status

**Issue:** #{s.get('issue')} — {first_line(s.get('issue_title'))}
**Customer:** @{s.get('customer')}
**State:** `{s.get('state')}`
**Service:** {'Monthly Ops Support' if s.get('service')=='monthly' else 'One-time AI Ops Audit'}
**Default Amount:** {s.get('pricing_defaults',{}).get('suggested_amount')}

{link}{reasons_block}

_Last updated: {s.get('updated_utc')}_
"""

# ---------------------------
# Main
# ---------------------------

def main():
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        return

    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    ctx = extract_ctx(event)

    # Fast no-op guard
    if LABEL_STEGOPS not in ctx.labels or ctx.number <= 0:
        return

    base = Path("leads") / f"issue-{ctx.number}"
    lock = IssueLock(base / ".lock")
    if not lock.acquire():
        return

    try:
        state_path = base / "state.json"
        prev = safe_read_json(state_path)

        nxt = compute_state(ctx, prev)

        # Idempotent write: only write files if meaningful state object changes
        prev_hash = canonical_hash(prev) if prev else ""
        nxt_hash = canonical_hash(nxt)

        if prev_hash == nxt_hash:
            return

        # Snapshot previous state for validation / audit (only if existed)
        if state_path.exists():
            safe_write_text(base / "state.prev.json", state_path.read_text(encoding="utf-8"))

        safe_write_json(state_path, nxt)
        safe_write_text(base / "STATUS.md", render_status(nxt))

    finally:
        lock.release()

if __name__ == "__main__":
    main()
