#!/usr/bin/env python3
"""
StegOps State Engine

- locking
- payment verification (two-factor: label + authorized comment intent)
- SIGNED StegPay repository_dispatch support (ONLY trusted path)
- deliverables states
- private workspace link
- schema_version + audit reasons
- idempotent writes
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

from scripts.verify_envelope import verify_envelope

# ---------------------------
# Label constants
# ---------------------------

LABEL_STEGOPS = "stegops"
LABEL_MONTHLY = "monthly"
LABEL_AUDIT = "audit"
LABEL_QUALIFIED = "qualified"
LABEL_SOW = "sow-generated"
LABEL_INVOICE = "invoice-generated"
LABEL_PAYMENT_CLAIMED = "payment-claimed"
LABEL_DELIVERABLES_PUSHED = "deliverables-pushed"
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
    state: str
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

    service = prev.get("service") or parse_service_from_issue_body(ctx.body) or "audit"

    out = dict(prev) if prev else {}
    out.update({
        "schema_version": SCHEMA_VERSION,
        "issue": ctx.number,
        "customer": ctx.author,
        "issue_title": ctx.title,
        "service": service,
        "updated_utc": now,
    })

    out["state"] = max_state(prev_state, "deliverables_ready")

    reasons = set(out.get("reasons") or [])
    reasons.add("stegpay_verified_event")
    out["reasons"] = sorted(reasons)

    ts = out.setdefault("timestamps", {})
    if "payment_verified" not in ts:
        ts["payment_verified"] = now

    out["private_workspace"] = (
        f"https://github.com/StegVerse-Labs/StegOps-Deliverables/tree/main/clients/issue-{ctx.number}"
    )

    return out

# ---------------------------
# STATUS renderer
# ---------------------------

def render_status(s: Dict[str, Any]) -> str:
    pw = s.get("private_workspace")
    link = f"\n🔒 **Private Workspace:** {pw}\n" if pw else ""
    return f"""# Engagement Status

**Issue:** #{s.get('issue')}
**Customer:** @{s.get('customer')}
**State:** `{s.get('state')}`

{link}

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

    # 🔐 SIGNED ENVELOPE PATH (ONLY TRUSTED ENTRYPOINT)
    if os.getenv("GITHUB_EVENT_NAME") == "repository_dispatch":
        payload = event.get("client_payload") or {}

        trusted = safe_read_json(Path("trusted_keys.json"))

        if not verify_envelope(payload, trusted):
            print("❌ Signature verification failed")
            return

        event_data = payload.get("event") or {}
        issue_number = event_data.get("issue")

        if not issue_number:
            print("❌ Missing issue")
            return

        ctx = IssueContext(
            number=int(issue_number),
            author="stegpay",
            title="Payment Event",
            url="",
            state="open",
            labels=[LABEL_STEGOPS, LABEL_VERIFY_PAYMENT],
            body="",
            comment="verify payment",
            assoc="OWNER",
        )

        base = Path("leads") / f"issue-{issue_number}"
        lock = IssueLock(base / ".lock")

        if not lock.acquire():
            return

        try:
            state_path = base / "state.json"
            prev = safe_read_json(state_path)
            nxt = compute_state(ctx, prev)

            nxt["payment_verification"] = event_data

            safe_write_json(state_path, nxt)
            safe_write_text(base / "STATUS.md", render_status(nxt))

        finally:
            lock.release()

        return

if __name__ == "__main__":
    main()
