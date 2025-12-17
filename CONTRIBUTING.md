# Contributing to StegOps-Orchestrator

## Non-negotiable boundary
This repo is the **control plane** (intake + automation + audit trail).  
Paid deliverables must go to: **StegVerse-Labs/StegOps-Deliverables** (private).

### Do not commit to this repo
- `REPORT.md` under any `leads/issue-*/`
- any `ARTIFACTS/` folder under `leads/issue-*/`
- any screenshots, PDFs, logs, or zips under `leads/`
- any `clients/` folder

These changes will be blocked by CI guardrails.

---

## What is OK to commit here
- Workflows (`.github/workflows/`)
- Automation scripts (`script/`)
- Templates (`templates/`)
- Public pages (`site/`)
- Invoices (`invoices/`)
- Dashboards (`dashboards/`)
- Engagement process state only:
  - `leads/issue-*/state.json`
  - `leads/issue-*/STATUS.md`

---

## If you need to attach evidence or findings
Put it in the private repo:
`StegOps-Deliverables/clients/issue-<n>/ARTIFACTS/`

Put the report in:
`StegOps-Deliverables/clients/issue-<n>/REPORT.md`
