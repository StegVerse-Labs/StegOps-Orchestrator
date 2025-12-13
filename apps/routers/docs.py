from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path

from ..db import get_db
from ..models import Deal, Lead, Document, AuditLog
from ..util import safe_fill_template

router = APIRouter()

def _load_doc(name: str) -> str:
    p = Path(__file__).resolve().parent.parent.parent / "docs" / name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Missing template {name}")
    return p.read_text()

@router.post("/render/proposal")
def render_proposal(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    lead = db.query(Lead).filter(Lead.id == deal.lead_id).one_or_none()

    tpl = _load_doc("proposal_template.md") if (Path(__file__).resolve().parent.parent.parent / "docs" / "proposal_template.md").exists() else _load_doc("SOW_TEMPLATE.md")
    mapping = {
        "Client Name": lead.company or "Client",
        "Stakeholder Names": lead.name or "",
        "Date": "",
    }
    content = safe_fill_template(tpl, mapping)
    doc = Document(deal_id=deal_id, doc_type="proposal", status="draft", content=content)
    db.add(doc); db.flush()
    db.add(AuditLog(actor="system", action="render_proposal", object_type="document", object_id=str(doc.id)))
    db.commit()
    return {"ok": True, "document_id": doc.id, "content": content}

@router.post("/render/sow")
def render_sow(deal_id: int, tier: str = "2", db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    tpl = _load_doc("SOW_TEMPLATE.md")
    content = tpl.replace("[CLIENT]", str(deal.lead.company if hasattr(deal, "lead") else "Client")).replace("[1 | 2 | 3]", tier)
    doc = Document(deal_id=deal_id, doc_type="sow", status="draft", content=content)
    db.add(doc); db.flush()
    db.add(AuditLog(actor="system", action="render_sow", object_type="document", object_id=str(doc.id)))
    db.commit()
    return {"ok": True, "document_id": doc.id, "content": content}
