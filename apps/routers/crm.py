from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from ..db import get_db

router = APIRouter()

class LeadIn(BaseModel):
    email: EmailStr
    name: str | None = None
    company: str | None = None
    source: str | None = "manual"

@router.post("/leads")
def create_lead(payload: LeadIn, db: Session = Depends(get_db)):
    # Minimal stub (phase 1): return what we'd store.
    return {"email": str(payload.email), "name": payload.name, "company": payload.company, "source": payload.source}
