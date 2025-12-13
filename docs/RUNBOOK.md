# StegOps Runbook (Phase 1)

## Connect Gmail
1) Set env vars (Google OAuth + Pub/Sub token)
2) Visit `GET /v1/auth/google/start` and complete consent
3) Configure Pub/Sub push → `POST /v1/webhooks/gmail/push`
4) Start watch:
   `POST /v1/gmail/watch/start?email=<mailbox>`

## Inbound email flow
- Pub/Sub push triggers history processing
- StegOps ingests inbound message → creates AI reply draft (if enabled)
- Pending drafts are listed at:
  `GET /v1/approval/drafts/pending?email=<mailbox>`
- Send by message id:
  `POST /v1/approval/drafts/send_by_message?email=<mailbox>`

## Outbound outreach
Upload a CSV (columns: email,name,company,role,context):
`POST /v1/outreach/draft_from_csv?email=<mailbox>` (multipart form with file)

This creates Gmail drafts for each row + logs them in CRM-Lite.

## Billing (Stripe)
Set `STRIPE_API_KEY` then:
`POST /v1/billing/stripe/invoice/create`

## Docs rendering
- `POST /v1/docs/render/proposal?deal_id=<id>`
- `POST /v1/docs/render/sow?deal_id=<id>&tier=2`
