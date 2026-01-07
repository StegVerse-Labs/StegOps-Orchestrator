#!/usr/bin/env python3
"""
StegOps State Engine
- locking
- payment verification
- deliverables states
- private workspace link (read-only, no secrets)
"""

from __future__ import annotations
import json, os, re, shutil, time
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
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def safe_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def norm_labels(labels: List[Dict[str, Any]]) -> List[str]:
    return sorted({(l.get("name") or "").strip() for l in labels or [] if l.get("name")})

def first_line(s: str, max_len: int = 160) -> str:
    s = (s or "").strip().splitlines()[0] if s else ""
    return s if len(s) <= max_len else s[: max_len - 1] + "…"

def parse_service_from_issue_body(body: str) -> Optional[str]:
    b = (body or "").lower()
    if "monthly ops support" in b: return "monthly"
    if "one-time ai ops audit" in b: return "audit"
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
    order = [
        "new","replied","qualified","sow_generated","accepted","invoice_generated",
        "payment_claimed","verify_payment","payment_verified",
        "deliverables_ready","deliverables_pushed",
        "closed_no_response","closed",
    ]
    return order.index(s) if s in order else 0

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
        if self.d.exists(): shutil.rmtree(self.d, ignore_errors=True)

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
    s = prev.get("state") or "new"

    service = prev.get("service") or parse_service_from_issue_body(ctx.body) or "audit"
    if "monthly" in ctx.labels: service = "monthly"
    if "audit" in ctx.labels: service = "audit"

    out = dict(prev) if prev else {}
    out.update({
        "issue": ctx.number,
        "customer": ctx.author,
        "issue_url": ctx.url,
        "issue_title": ctx.title,
        "service": service,
        "labels": ctx.labels,
        "updated_utc": now,
    })

    ts = out.setdefault("timestamps", {})
    yes, accept, paid, verify = (False, False, False, False)
    if ctx.comment:
        yes, accept, paid, verify = parse_comment_intents(ctx.comment)

    observed = "new"
    if ctx.comment: observed = max_state(observed, "replied")
    if "qualified" in ctx.labels or yes: observed = max_state(observed, "qualified")
    if "sow-generated" in ctx.labels: observed = max_state(observed, "sow_generated")
    if accept: observed = max_state(observed, "accepted")
    if "invoice-generated" in ctx.labels: observed = max_state(observed, "invoice_generated")
    if paid or "payment-claimed" in ctx.labels:
        observed = max_state(observed, "payment_claimed")
        observed = max_state(observed, "verify_payment")
    if verify and is_authorized_assoc(ctx.assoc):
        observed = max_state(observed, "payment_verified")
        observed = max_state(observed, "deliverables_ready")
    if "deliverables-pushed" in ctx.labels:
        observed = max_state(observed, "deliverables_pushed")

    out["state"] = max_state(s, observed)

    def mark(k, cond):
        if cond and k not in ts: ts[k] = now

    mark("qualified", "qualified" in ctx.labels or yes)
    mark("accepted", accept)
    mark("invoice_generated", "invoice-generated" in ctx.labels)
    mark("payment_claimed", paid or "payment-claimed" in ctx.labels)
    mark("payment_verified", verify and is_authorized_assoc(ctx.assoc))
    mark("deliverables_pushed", "deliverables-pushed" in ctx.labels)

    out.setdefault("pricing_defaults", {})["suggested_amount"] = choose_amount_default(service)
    out["private_workspace"] = (
        f"https://github.com/StegVerse-Labs/StegOps-Deliverables/tree/main/clients/issue-{ctx.number}"
        if out["state"] in {"deliverables_ready","deliverables_pushed"}
        else None
    )
    return out

# ---------------------------
# STATUS renderer
# ---------------------------

def render_status(s: Dict[str, Any]) -> str:
    pw = s.get("private_workspace")
    link = f"\n🔒 **Private Workspace:** {pw}\n" if pw else ""
    return f"""# Engagement Status

**Issue:** #{s.get('issue')} — {first_line(s.get('issue_title'))}
**Customer:** @{s.get('customer')}
**State:** `{s.get('state')}`
**Service:** {'Monthly Ops Support' if s.get('service')=='monthly' else 'One-time AI Ops Audit'}
**Default Amount:** {s.get('pricing_defaults',{}).get('suggested_amount')}

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
    ctx = extract_ctx(event)
    if "stegops" not in ctx.labels or ctx.number <= 0:
        return

    base = Path("leads") / f"issue-{ctx.number}"
    lock = IssueLock(base / ".lock")
    if not lock.acquire():
        return

    try:
        state_path = base / "state.json"
        prev = safe_read_json(state_path)

        # Snapshot previous state for validator / audit (only if it existed)
        if state_path.exists():
            safe_write_text(base / "state.prev.json", state_path.read_text(encoding="utf-8"))

        nxt = compute_state(ctx, prev)
        safe_write_json(state_path, nxt)
        safe_write_text(base / "STATUS.md", render_status(nxt))
    finally:
        lock.release()

if __name__ == "__main__":
    main()
