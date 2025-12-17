# Boundaries Policy (StegOps-Orchestrator vs StegOps-Deliverables)

## Rule of thumb
**If it exists because money was paid, it belongs in StegOps-Deliverables (private).**  
**If it exists to automate or record the process, it belongs in StegOps-Orchestrator.**

---

## StegOps-Orchestrator (this repo)
Allowed:
- `.github/workflows/*`
- `script/*` automation logic
- `templates/*` (SOW/invoice/autoreply templates)
- `site/*` public positioning pages
- `invoices/*` invoice markdown
- `dashboards/*` aggregate operational summaries
- `leads/issue-*/state.json` and `leads/issue-*/STATUS.md` (process-only, non-sensitive)

Forbidden:
- Any paid findings or client evidence
- `leads/**/REPORT.md`
- `leads/**/ARTIFACTS/`
- Any `clients/` folder (belongs in Deliverables)
- Screenshots/log dumps under `leads/`

---

## StegOps-Deliverables (private repo)
Expected:
- `clients/issue-<n>/REPORT.md` (paid output)
- `clients/issue-<n>/ARTIFACTS/` (evidence, screenshots, logs)
- `clients/issue-<n>/STATUS.md` and `STATE.json` (copied snapshots)

---

## Why this matters
- Prevents accidental leakage of paid/confidential content
- Keeps public repo defensible (process transparency, clean audit trail)
- Keeps private repo focused on delivery only
