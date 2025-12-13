# StegOps Orchestrator — Full Gmail Send/Receive (Workspace)

This repo provides:
- Gmail OAuth connect (store refresh token)
- Gmail Push (Pub/Sub → webhook) + history processing
- Ingest inbound messages into CRM-Lite
- Call OpenAI (Responses API + Structured Outputs) to classify + draft replies
- Create Gmail draft replies (human approval by default)
- Optional auto-send for low-risk replies (disabled by default)

## Key endpoints
### OAuth
- `GET /v1/auth/google/start`
- `GET /v1/auth/google/callback`

### Gmail
- `POST /v1/gmail/watch/start?email=<mailbox>`
- `POST /v1/gmail/history/poll?email=<mailbox>`
- `POST /v1/webhooks/gmail/push` (Pub/Sub push)
- `POST /v1/gmail/drafts/send?email=<mailbox>`

### Health
- `GET /health`

## Local run
1) Install deps:
```bash
pip install -r requirements.txt
```

2) Configure `.env` (copy from `.env.example`)

3) Init DB:
```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
```

4) Run:
```bash
uvicorn app.main:app --reload --port 8080
```

## Setup guide
See: `docs/GMAIL_FULL_SETUP.md`
