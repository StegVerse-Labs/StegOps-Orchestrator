# StegArchive (AI-enabled)

Drop conversation exports into `inbox/` as `.md` files.

GitHub Actions runs an AI Entity that:
- classifies each file as `active` vs `archived`
- adds tags + a short summary
- moves files into `processed/active/` or `processed/archived/`
- appends a log entry into `ARCHIVE/COMBINED_ARCHIVE_LIST.md`

## Setup
- Add repo secret: OPENAI_API_KEY
- Run Actions workflow: "StegArchive Manager"

## Folders
- inbox/                (drop new exports here)
- processed/active/
- processed/archived/
- ARCHIVE/              (human-readable index)
- scripts/              (AI entity logic)
