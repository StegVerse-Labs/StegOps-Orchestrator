import base64, json
from fastapi import APIRouter, Header, HTTPException, Request
from ..settings import settings

router = APIRouter()

def verify(token: str | None):
    if settings.PUBSUB_VERIFICATION_TOKEN and token != settings.PUBSUB_VERIFICATION_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

@router.post("/push")
async def push(request: Request, x_stegops_token: str | None = Header(default=None)):
    verify(x_stegops_token)
    body = await request.json()
    msg = body.get("message") or {}
    data_b64 = msg.get("data")
    if not data_b64:
        return {"ok": True, "note": "no data"}
    data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    # Gmail push contains emailAddress + historyId. Use historyId with users.history.list to fetch new message IDs.
    return {"ok": True, "gmail": data}
