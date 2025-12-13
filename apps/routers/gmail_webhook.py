import base64
import json
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from ..settings import settings
from ..db import get_db
from .gmail_ops import _process_history

router = APIRouter()

def _verify(token: str | None):
    if not settings.PUBSUB_VERIFICATION_TOKEN:
        return
    if token != settings.PUBSUB_VERIFICATION_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid verification token")

@router.post("/push")
async def gmail_pubsub_push(request: Request, x_stegops_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Pub/Sub push endpoint.
    Pub/Sub data is base64 JSON: { emailAddress, historyId }.
    We process history synchronously (OK for low volume). For higher volume, move to a worker queue.
    """
    _verify(x_stegops_token)

    body = await request.json()
    msg = body.get("message") or {}
    data_b64 = msg.get("data")
    if not data_b64:
        return {"ok": True, "note": "No data"}

    data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    email = data.get("emailAddress")
    history_id = str(data.get("historyId") or "")

    if not email or not history_id:
        return {"ok": True, "note": "Missing emailAddress/historyId", "data": data}

    # Process new messages since this historyId
    result = _process_history(email=email, incoming_history_id=history_id, db=db)
    return {"ok": True, "data": data, "result": result}
