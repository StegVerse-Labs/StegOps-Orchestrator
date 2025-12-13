import base64
from email.message import EmailMessage
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

from .models import GoogleToken, GmailState
from .settings import settings

SCOPES_READ_SEND = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

def _load_creds(db: Session, email: str) -> Optional[Credentials]:
    row = db.query(GoogleToken).filter(GoogleToken.email == email).one_or_none()
    if not row:
        return None
    data = row.token_json
    creds = Credentials.from_authorized_user_info(__import__("json").loads(data), SCOPES_READ_SEND)
    # Refresh if needed
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        row.token_json = creds.to_json()
        db.add(row)
        db.commit()
    return creds

def gmail_service(db: Session, email: str):
    creds = _load_creds(db, email)
    if not creds:
        raise RuntimeError("No Gmail OAuth token stored for this email. Complete /v1/auth/google/start first.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def make_raw_email(to_email: str, subject: str, body: str, from_email: Optional[str] = None, in_reply_to: Optional[str] = None, references: Optional[str] = None) -> str:
    msg = EmailMessage()
    msg["To"] = to_email
    if from_email:
        msg["From"] = from_email
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw

def set_last_history_id(db: Session, email: str, history_id: str):
    row = db.query(GmailState).filter(GmailState.email == email).one_or_none()
    if not row:
        row = GmailState(email=email, last_history_id=history_id)
    else:
        row.last_history_id = history_id
    db.add(row)
    db.commit()

def get_last_history_id(db: Session, email: str) -> Optional[str]:
    row = db.query(GmailState).filter(GmailState.email == email).one_or_none()
    return row.last_history_id if row else None
