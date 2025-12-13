import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow

from ..db import get_db
from ..settings import settings
from ..models import GoogleToken, AuditLog

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

def _flow() -> Flow:
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET and settings.GOOGLE_OAUTH_REDIRECT_URI):
        raise HTTPException(status_code=500, detail="Google OAuth env vars not set")
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI)

@router.get("/google/start")
def google_start():
    flow = _flow()
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return RedirectResponse(auth_url)

@router.get("/google/callback")
def google_callback(request: Request, db: Session = Depends(get_db)):
    flow = _flow()
    # Reconstruct full URL the provider redirected to
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    creds = flow.credentials
    if not creds:
        raise HTTPException(status_code=400, detail="No credentials returned")

    # We need the authorized user's email. Gmail profile gives it.
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    if not email:
        raise HTTPException(status_code=400, detail="Could not resolve authorized email")

    token_json = creds.to_json()
    row = db.query(GoogleToken).filter(GoogleToken.email == email).one_or_none()
    if not row:
        row = GoogleToken(email=email, token_json=token_json)
    else:
        row.token_json = token_json
    db.add(row)
    db.add(AuditLog(actor="human", action="google_oauth_connected", object_type="google_token", object_id=email))
    db.commit()

    return {"ok": True, "email": email, "message": "OAuth connected. Next: call /v1/gmail/watch/start to enable push."}
