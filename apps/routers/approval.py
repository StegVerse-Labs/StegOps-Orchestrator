from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db
from ..models import Message, AuditLog
from ..gmail import gmail_service

router = APIRouter()

@router.get("/drafts/pending")
def list_pending_drafts(email: str, db: Session = Depends(get_db), limit: int = 50):
    q = (
        db.query(Message)
        .filter(Message.gmail_draft_id.isnot(None))
        .filter(Message.requires_approval == True)  # noqa: E712
        .order_by(Message.id.desc())
        .limit(limit)
    )
    rows = q.all()
    return {
        "ok": True,
        "pending": [
            {
                "message_id": r.id,
                "direction": r.direction,
                "to": r.to_email,
                "subject": r.subject,
                "draft_id": r.gmail_draft_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }

class SendByMessageIn(BaseModel):
    message_id: int

@router.post("/drafts/send_by_message")
def send_by_message(payload: SendByMessageIn, email: str, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == payload.message_id).one_or_none()
    if not msg or not msg.gmail_draft_id:
        raise HTTPException(status_code=404, detail="Message/draft not found")
    svc = gmail_service(db, email)
    svc.users().drafts().send(userId="me", body={"id": msg.gmail_draft_id}).execute()
    msg.requires_approval = False
    db.add(msg)
    db.add(AuditLog(actor="human", action="gmail_draft_sent_by_message", object_type="message", object_id=str(msg.id), detail_json=msg.gmail_draft_id))
    db.commit()
    return {"ok": True, "message_id": msg.id, "draft_id": msg.gmail_draft_id}
