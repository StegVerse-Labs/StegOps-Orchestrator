from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from ..db import get_db
from ..models import Lead, Deal, AuditLog

router = APIRouter()

class LeadIn(BaseModel):
    email: EmailStr
    name: str | None = None
    company: str | None = None
    source: str | None = "manual"

@router.post("/leads")
def create_lead(payload: LeadIn, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.email == str(payload.email)).one_or_none()
    if not lead:
        lead = Lead(email=str(payload.email), name=payload.name, company=payload.company, source=payload.source, status="new")
        db.add(lead)
        db.flush()
        db.add(AuditLog(actor="human", action="create_lead", object_type="lead", object_id=str(lead.id)))
        db.commit()
    return {"id": lead.id, "email": lead.email, "status": lead.status}

@router.post("/leads/{lead_id}/deals")
def create_deal(lead_id: int, tier: str = "2", db: Session = Depends(get_db)):
    deal = Deal(lead_id=lead_id, tier=tier, stage="scoping", probability=50)
    db.add(deal)
    db.flush()
    db.add(AuditLog(actor="human", action="create_deal", object_type="deal", object_id=str(deal.id)))
    db.commit()
    return {"id": deal.id, "lead_id": deal.lead_id, "tier": deal.tier, "stage": deal.stage}
