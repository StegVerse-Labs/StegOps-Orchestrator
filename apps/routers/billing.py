import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Invoice, Deal, AuditLog, Lead
from ..settings import settings

router = APIRouter()

class StripeInvoiceIn(BaseModel):
    deal_id: int
    amount_usd: float
    description: str | None = None
    customer_email: str | None = None

@router.post("/stripe/invoice/create")
async def stripe_create_invoice(payload: StripeInvoiceIn, db: Session = Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(status_code=400, detail="STRIPE_API_KEY not set")

    deal = db.query(Deal).filter(Deal.id == payload.deal_id).one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    lead = db.query(Lead).filter(Lead.id == deal.lead_id).one_or_none()

    customer_email = payload.customer_email or (lead.email if lead else None)
    if not customer_email:
        raise HTTPException(status_code=400, detail="customer_email required")

    # Stripe flow: create customer, create invoice item, create invoice, finalize+send (optional)
    headers = {"Authorization": f"Bearer {settings.STRIPE_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        cust = await client.post("https://api.stripe.com/v1/customers", headers=headers, data={"email": customer_email})
        cust.raise_for_status()
        cust_id = cust.json()["id"]

        # amount in cents
        cents = int(round(float(payload.amount_usd) * 100))
        item = await client.post("https://api.stripe.com/v1/invoiceitems", headers=headers, data={
            "customer": cust_id,
            "amount": cents,
            "currency": "usd",
            "description": payload.description or "StegVerse services",
        })
        item.raise_for_status()

        inv = await client.post("https://api.stripe.com/v1/invoices", headers=headers, data={
            "customer": cust_id,
            "collection_method": "send_invoice",
            "days_until_due": 15,
            "auto_advance": "true",
        })
        inv.raise_for_status()
        inv_id = inv.json()["id"]

        # finalize
        fin = await client.post(f"https://api.stripe.com/v1/invoices/{inv_id}/finalize", headers=headers)
        fin.raise_for_status()
        # send
        snd = await client.post(f"https://api.stripe.com/v1/invoices/{inv_id}/send", headers=headers)
        snd.raise_for_status()

    row = Invoice(deal_id=payload.deal_id, amount_usd=payload.amount_usd, status="sent", external_id=inv_id)
    db.add(row); db.flush()
    db.add(AuditLog(actor="system", action="stripe_invoice_sent", object_type="invoice", object_id=str(row.id), detail_json=inv_id))
    db.commit()

    return {"ok": True, "invoice_id": row.id, "stripe_invoice_id": inv_id}

