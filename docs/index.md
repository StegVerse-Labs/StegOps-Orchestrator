# StegOps / StegVerse Operator Index

This is the internal index for operating the StegOps revenue automation and continuity pipeline.

---

## Public-facing pages

- `site/index.md` — StegVerse landing page
- `site/services.md` — Services
- `site/pricing.md` — Pricing

---

## Lead intake (GitHub-native funnel)

### Issue intake
- Issue template: `.github/ISSUE_TEMPLATE/stegops-lead.yml`
- Expected labels on creation: `stegops`, `inbound`

### Auto-reply (on issue opened)
- Workflow: `.github/workflows/stegops-auto-reply.yml`
- Reply template: `templates/lead_autoreply.md`

### Qualification (on YES)
- Workflow: `.github/workflows/stegops-qualify-on-yes.yml`
- Template: `templates/lead_qualified_reply.md`
- Labels: `qualified`, `lead-logged`, `next-steps-sent`

### Reopen (YES on a closed StegOps issue)
- Workflow: `.github/workflows/stegops-reopen-on-yes.yml`
- Template: `templates/lead_reopened_reply.md`
- Labels: `qualified`, `lead-logged`, `next-steps-sent`

### Auto-close stale leads (7+ days inactivity)
- Workflow: `.github/workflows/stegops-auto-close-stale-leads.yml`
- Template: `templates/lead_autoclose.md`
- Labels: `no-response`, optional `do-not-close`

---

## Lead workspaces (per-qualified issue)

- Workflow: `.github/workflows/stegops-create-lead-folder.yml`
- Folder pattern: `leads/issue-<number>/`
- Contents:
  - `README.md` (templated)
  - `metadata.json`
  - `checklist.md`

Template:
- `templates/lead_folder_README.md`

---

## Invoices (drafts)

- Workflow: `.github/workflows/stegops-invoice-on-command.yml`
- Template: `templates/invoice_draft.md`
- Output folder: `invoices/`
- Trigger: comment **invoice** on a qualified StegOps issue

---

## Dashboards

- Workflow: `.github/workflows/stegops-monthly-dashboard.yml`
- Outputs:
  - `dashboards/DASHBOARD.md` (latest)
  - `dashboards/monthly-YYYY-MM.md` (snapshot)

---

## Continuity & archive engine (StegOps-Orchestrator core)

- Inbox processing: `script/archive_classifier.py`
- AI entity: `script/archive_ai_entity.py`
- Status writer: `script/archive_status.py`

Primary outputs:
- `apps/routers/ARCHIVE/STATUS.md`
- `apps/routers/ARCHIVE/run_state.json`
- `apps/routers/ARCHIVE/COMBINED_ARCHIVE_LIST.md`

Inbox paths:
- `inbox/` (drop `.md` files here)
- `processed/active/`
- `processed/archived/`

---

## CRM-lite files

- `LEADS.md` — lead ledger (auto-updated)
- `SERVICES.md` — service definition (for invoicing legitimacy)

---

## Operational commands (what to comment on issues)

- **YES** → qualify (and/or reopen if closed)
- **invoice** → generate a draft invoice
- Add label `do-not-close` → prevent auto-close

---

## Repo hygiene

- `.gitignore` must include:
  - `__pycache__/`
  - `*.pyc`
  - virtual env folders

---

## Status checks (quick)

If something “isn’t working”, verify in this order:
1) Issue template appears in **Issues → New Issue**
2) New issue receives auto-reply comment
3) Comment YES adds `qualified`
4) `LEADS.md` gets a line item
5) `leads/issue-#/` workspace appears
6) Comment invoice generates `invoices/INV-...md`
7) Dashboard workflow runs and writes `dashboards/`

This order isolates failures immediately.
