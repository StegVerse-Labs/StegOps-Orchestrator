import json
from pathlib import Path
from .openai_client import responses_create
from .settings import settings

SYSTEM = """You are StegOps Agent. You draft and classify email and sales ops actions for StegVerse.
You must return JSON that matches the provided schema. Be concise and professional.
Never promise outcomes. Never provide legal advice. Prefer scheduling a short scoping call.
"""

def _load_schema(name: str) -> dict:
    p = Path(__file__).resolve().parent.parent / "schemas" / f"{name}.json"
    return json.loads(p.read_text())

async def classify_and_draft_reply(email_subject: str, email_body: str) -> dict:
    schema = _load_schema("inbound_email_response")
    payload = {
        "model": settings.OPENAI_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Subject: {email_subject}\n\nBody:\n{email_body}"},
        ],
        "text": {"format": {"type": "json_schema", "json_schema": schema}},
    }
    return await responses_create(payload)

async def draft_outbound_email(company: str, contact_name: str, role: str, context: str) -> dict:
    schema = _load_schema("outbound_email_draft")
    payload = {
        "model": settings.OPENAI_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Company: {company}\nContact: {contact_name}\nRole: {role}\nContext:\n{context}"},
        ],
        "text": {"format": {"type": "json_schema", "json_schema": schema}},
    }
    return await responses_create(payload)
