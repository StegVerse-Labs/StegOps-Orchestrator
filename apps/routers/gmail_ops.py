import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..gmail import gmail_service, make_raw_email, get_last_history_id, set_last_history_id
from ..models import Message, AuditLog, Lead, Deal
from ..settings import settings
from ..agent import classify_and_draft_reply

router = APIRouter()

def _extract_email(addr: str | None) -> str | None:
    if not addr:
        return None
    m = re.search(r"<([^>]+)>", addr)
    return m.group(1).strip() if m else addr.strip()

def _get_header(headers, name: str):
    for h in headers or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value")
    return None

def _decode_payload(payload) -> str:
    # Prefer snippet. If payload has text/plain part, decode it.
    if not payload:
        return ""
    body = payload.get("body", {}) or {}
    data = body.get("data")
    if data:
        import base64
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    parts = payload.get("parts") or []
    for p in parts:
        mime = (p.get("mimeType") or "").lower()
        if mime == "text/plain":
            b = p.get("body", {}) or {}
            d = b.get("data")
            if d:
                import base64
                return base64.urlsafe_b64decode(d.encode("utf-8")).decode("utf-8", errors="ignore")
    return ""

class WatchIn(BaseModel):
    topic_name: str  # e.g. "projects/<proj>/topics/<topic>"
    label_ids: list[str] | None = None  # e.g. ["INBOX"]

@router.post("/watch/start")
def watch_start(payload: WatchIn, email: str, db: Session = Depends(get_db)):
    svc = gmail_service(db, email)
    body = {
        "topicName": payload.topic_name,
        "labelIds": payload.label_ids or ["INBOX"],
        "labelFilterAction": "include",
    }
    resp = svc.users().watch(userId="me", body=body).execute()
    history_id = resp.get("historyId")
    if history_id:
        set_last_history_id(db, email, history_id)
    db.add(AuditLog(actor="human", action="gmail_watch_started", object_type="gmail", object_id=email, detail_json=str(resp)))
    db.commit()
    return {"ok": True, "response": resp}

@router.post("/history/poll")
def history_poll(email: str, db: Session = Depends(get_db)):
    """Manual poll to process any messages since last_history_id (useful for debugging)."""
    return _process_history(email=email, incoming_history_id=None, db=db)

def _ensure_lead_deal(db: Session, from_email: str) -> tuple[int, int | None]:
    lead = db.query(Lead).filter(Lead.email == from_email).one_or_none()
    if not lead:
        lead = Lead(email=from_email, status="new", source="email")
        db.add(lead)
        db.flush()
        db.add(AuditLog(actor="system", action="lead_created_from_inbound_email", object_type="lead", object_id=str(lead.id)))
    # Create a deal if none exists
    deal_id = None
    if lead.deals:
        deal_id = lead.deals[0].id
    else:
        deal = Deal(lead_id=lead.id, tier="2", stage="scoping", probability=50)
        db.add(deal)
        db.flush()
        deal_id = deal.id
        db.add(AuditLog(actor="system", action="deal_created_from_inbound_email", object_type="deal", object_id=str(deal_id)))
    db.commit()
    return lead.id, deal_id

def _process_history(email: str, incoming_history_id: str | None, db: Session):
    svc = gmail_service(db, email)
    last = get_last_history_id(db, email)
    start_id = incoming_history_id or last
    if not start_id:
        # If we have no baseline, set to current profile historyId via watch first.
        raise HTTPException(status_code=400, detail="No history baseline. Run /v1/gmail/watch/start first.")

    # Pull history
    history = svc.users().history().list(userId="me", startHistoryId=start_id, historyTypes=["messageAdded"]).execute()
    histories = history.get("history") or []
    processed = 0
    created_drafts = 0

    for h in histories:
        for ma in (h.get("messagesAdded") or []):
            msg = ma.get("message") or {}
            msg_id = msg.get("id")
            thread_id = msg.get("threadId")
            if not msg_id:
                continue

            # Idempotency: skip if already stored
            exists = db.query(Message).filter(Message.message_id == msg_id).one_or_none()
            if exists:
                continue

            full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
            payload = full.get("payload") or {}
            headers = payload.get("headers") or []

            subject = _get_header(headers, "Subject") or ""
            from_h = _get_header(headers, "From")
            to_h = _get_header(headers, "To")
            from_email = _extract_email(from_h) or ""
            to_email = _extract_email(to_h) or ""

            snippet = full.get("snippet") or ""
            body_text = _decode_payload(payload) or snippet
            content = body_text.strip() or snippet.strip()

            # Create lead/deal linkage
            _, deal_id = _ensure_lead_deal(db, from_email) if from_email else (None, None)

            mrow = Message(
                deal_id=deal_id,
                direction="inbound",
                channel="email",
                thread_id=thread_id,
                message_id=msg_id,
                subject=subject,
                from_email=from_email,
                to_email=to_email,
                content=content,
                requires_approval=True,
            )
            db.add(mrow)
            db.flush()
            db.add(AuditLog(actor="system", action="gmail_message_ingested", object_type="message", object_id=str(mrow.id), detail_json=msg_id))
            db.commit()
            processed += 1

            # Ask agent to draft reply
            try:
                agent_resp = __import__("asyncio").get_event_loop().run_until_complete(
                    classify_and_draft_reply(email_subject=subject, email_body=content)
                )
                # Responses API returns a rich object; the JSON output is in output_text[0].text in many cases.
                # We'll be defensive and extract any top-level `output_text` JSON.
                drafted = _extract_json_from_responses(agent_resp)
            except Exception as e:
                drafted = None
                db.add(AuditLog(actor="system", action="agent_failed_inbound", object_type="message", object_id=str(mrow.id), detail_json=str(e)))
                db.commit()

            if drafted and settings.AUTO_CREATE_DRAFTS:
                # Create Gmail draft (reply)
                reply_subject = drafted.get("suggested_subject") or f"Re: {subject}"
                reply_body = drafted.get("suggested_reply") or ""
                requires_approval = bool(drafted.get("requires_approval", True))
                mrow.requires_approval = requires_approval
                mrow.confidence_score = drafted.get("confidence")
                db.add(mrow)
                db.commit()

                if from_email:
                    raw = make_raw_email(to_email=from_email, subject=reply_subject, body=reply_body)
                    draft = svc.users().drafts().create(userId="me", body={"message": {"raw": raw, "threadId": thread_id}}).execute()
                    draft_id = draft.get("id")
                    if draft_id:
                        mrow.gmail_draft_id = draft_id
                        db.add(mrow)
                        db.add(AuditLog(actor="ai", action="gmail_draft_created", object_type="draft", object_id=draft_id, detail_json=str(mrow.id)))
                        db.commit()
                        created_drafts += 1

                        if settings.AUTO_SEND_LOW_RISK and (not requires_approval) and (float(drafted.get("confidence") or 0) >= 0.85):
                            svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()
                            db.add(AuditLog(actor="system", action="gmail_draft_autosent", object_type="draft", object_id=draft_id))
                            db.commit()

    # Update last history to latest
    new_hist = history.get("historyId") or incoming_history_id or last
    if new_hist:
        set_last_history_id(db, email, str(new_hist))

    return {"ok": True, "processed": processed, "drafts_created": created_drafts, "history_id": new_hist}

def _extract_json_from_responses(resp: dict) -> dict | None:
    # Try multiple known shapes.
    # 1) resp["output_text"] might contain a JSON string
    if isinstance(resp, dict):
        ot = resp.get("output_text")
        if isinstance(ot, list) and ot:
            txt = ot[0]
            if isinstance(txt, dict) and "text" in txt:
                txt = txt["text"]
            if isinstance(txt, str):
                return __import__("json").loads(txt)
        if isinstance(ot, str):
            try:
                return __import__("json").loads(ot)
            except Exception:
                pass
        # 2) resp["output"] parts
        out = resp.get("output")
        if isinstance(out, list):
            for part in out:
                content = part.get("content") if isinstance(part, dict) else None
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") in ("output_text","text") and isinstance(c.get("text"), str):
                            t = c["text"]
                            try:
                                return __import__("json").loads(t)
                            except Exception:
                                continue
    return None

class DraftSendIn(BaseModel):
    draft_id: str

@router.post("/drafts/send")
def send_draft(payload: DraftSendIn, email: str, db: Session = Depends(get_db)):
    svc = gmail_service(db, email)
    svc.users().drafts().send(userId="me", body={"id": payload.draft_id}).execute()
    db.add(AuditLog(actor="human", action="gmail_draft_sent", object_type="draft", object_id=payload.draft_id))
    db.commit()
    return {"ok": True, "draft_id": payload.draft_id}
