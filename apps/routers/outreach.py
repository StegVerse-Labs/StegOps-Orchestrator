import csv
import io
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Lead, Deal, Message, AuditLog
from ..agent import draft_outbound_email
from ..settings import settings
from ..gmail import gmail_service, make_raw_email

router = APIRouter()

def _get_or_create_lead(db: Session, email: str, name: str | None, company: str | None, source: str = "outreach"):
    lead = db.query(Lead).filter(Lead.email == email).one_or_none()
    if not lead:
        lead = Lead(email=email, name=name, company=company, source=source, status="new")
        db.add(lead); db.flush()
        db.add(AuditLog(actor="system", action="lead_created_outreach", object_type="lead", object_id=str(lead.id)))
        db.commit()
    return lead

def _get_or_create_deal(db: Session, lead_id: int, tier: str = "2"):
    deal = db.query(Deal).filter(Deal.lead_id == lead_id).order_by(Deal.id.desc()).first()
    if not deal:
        deal = Deal(lead_id=lead_id, tier=tier, stage="scoping", probability=40)
        db.add(deal); db.flush()
        db.add(AuditLog(actor="system", action="deal_created_outreach", object_type="deal", object_id=str(deal.id)))
        db.commit()
    return deal

@router.post("/draft_from_csv")
async def draft_from_csv(
    email: str,
    file: UploadFile = File(...),
    default_tier: str = "2",
    db: Session = Depends(get_db),
):
    """Upload CSV with columns: email,name,company,role,context
    Creates Gmail drafts for each row and stores Message rows for approval.
    """
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream"):
        # iOS sometimes uploads as octet-stream; allow.
        pass

    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    required = {"email"}
    if not reader.fieldnames or not required.issubset(set([h.strip().lower() for h in reader.fieldnames])):
        raise HTTPException(status_code=400, detail="CSV must include at least: email (recommended: name, company, role, context)")

    svc = gmail_service(db, email)

    created = []
    for row in reader:
        to_email = (row.get("email") or row.get("Email") or "").strip()
        if not to_email:
            continue
        name = (row.get("name") or row.get("Name") or "").strip() or None
        company = (row.get("company") or row.get("Company") or "").strip() or None
        role = (row.get("role") or row.get("Role") or "").strip() or ""
        context = (row.get("context") or row.get("Context") or "").strip() or ""

        lead = _get_or_create_lead(db, to_email, name, company, source="outreach")
        deal = _get_or_create_deal(db, lead.id, tier=default_tier)

        agent_resp = await draft_outbound_email(company=company or "", contact_name=name or "", role=role, context=context)
        drafted = _extract_json(agent_resp)
        if not drafted:
            db.add(AuditLog(actor="system", action="agent_failed_outbound", object_type="lead", object_id=str(lead.id)))
            db.commit()
            continue

        subject = drafted["subject"]
        body = drafted["body"] + "\n\n" + drafted["cta"]
        requires_approval = bool(drafted.get("requires_approval", True))

        # Create Gmail draft
        raw_msg = make_raw_email(to_email=to_email, subject=subject, body=body)
        d = svc.users().drafts().create(userId="me", body={"message": {"raw": raw_msg}}).execute()
        draft_id = d.get("id")

        m = Message(
            deal_id=deal.id,
            direction="outbound",
            channel="email",
            subject=subject,
            from_email=email,
            to_email=to_email,
            content=body,
            requires_approval=True if requires_approval else True,  # outbound always approval initially
            gmail_draft_id=draft_id,
        )
        db.add(m); db.flush()
        db.add(AuditLog(actor="ai", action="gmail_outbound_draft_created", object_type="draft", object_id=str(draft_id), detail_json=str(m.id)))
        db.commit()

        created.append({"to": to_email, "draft_id": draft_id, "message_id": m.id, "requires_approval": m.requires_approval})

    return {"ok": True, "created": created, "count": len(created)}

def _extract_json(resp: dict) -> dict | None:
    import json as _json
    # mirror logic from gmail_ops
    ot = resp.get("output_text")
    if isinstance(ot, list) and ot:
        txt = ot[0]
        if isinstance(txt, dict) and "text" in txt:
            txt = txt["text"]
        if isinstance(txt, str):
            try:
                return _json.loads(txt)
            except Exception:
                return None
    if isinstance(ot, str):
        try:
            return _json.loads(ot)
        except Exception:
            return None
    out = resp.get("output")
    if isinstance(out, list):
        for part in out:
            content = part.get("content") if isinstance(part, dict) else None
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") in ("output_text","text") and isinstance(c.get("text"), str):
                        try:
                            return _json.loads(c["text"])
                        except Exception:
                            continue
    return None
