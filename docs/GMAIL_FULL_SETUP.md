# Full Gmail Setup (Workspace) — StegOps

## 1) Create Google Cloud Project
- Enable APIs: Gmail API, Pub/Sub API

## 2) OAuth Consent Screen
- Add scopes:
  - gmail.readonly
  - gmail.send
  - gmail.modify

## 3) Create OAuth Client (Web)
Set redirect URI to match:
`GOOGLE_OAUTH_REDIRECT_URI`
Example:
`https://<your-stegops-domain>/v1/auth/google/callback`

## 4) Connect mailbox
Open:
`/v1/auth/google/start`
Sign in to `rigel@stegverse.org` (or desired mailbox) and grant consent.
You should receive JSON confirming the connected email.

## 5) Configure Pub/Sub
- Create topic: `projects/<proj>/topics/<topic>`
- Create push subscription pointing to:
  `https://<your-stegops-domain>/v1/webhooks/gmail/push`
- Add push header:
  `X-StegOps-Token: <PUBSUB_VERIFICATION_TOKEN>`

## 6) Start watch
Call:
POST `/v1/gmail/watch/start?email=<yourmailbox>`
Body:
{
  "topic_name": "projects/<proj>/topics/<topic>",
  "label_ids": ["INBOX"]
}

This stores the baseline historyId.

## 7) Test flow
- Send a test email to your mailbox.
- Pub/Sub should POST to StegOps.
- StegOps will ingest the message, log it, and (if AUTO_CREATE_DRAFTS=true) create a draft reply.
- To send a draft (manual approval):
POST `/v1/gmail/drafts/send?email=<yourmailbox>`
Body: { "draft_id": "<id>" }
