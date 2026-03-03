# StegArchive

StegArchive is the **central archive manager** for StegVerse conversations, specs, and threads.

## Goals

- Separate **active** vs **archived** conversation dumps.
- Maintain a **single source of truth** for what’s archived.
- Provide an **AI Entity** that:
  - Classifies new conversation exports.
  - Suggests which ones to archive.
  - Maintains a human-readable index.

## How It Works

1. You (or an AI agent) drop raw conversation exports into `inbox/` as `.md` files.
2. The **Archive Manager workflow** runs:
   - Reads files in `inbox/`
   - Classifies each as `active` or `archived`
   - Moves them to `processed/active/` or `processed/archived/`
   - Updates `ARCHIVE/COMBINED_ARCHIVE_LIST.md`
3. An optional **AI layer** (`archive_ai_entity.py`) can be enabled with `OPENAI_API_KEY`
   to give smarter tagging and descriptions.

## Folders

- `ARCHIVE/` — human-friendly archive index and topic files
- `inbox/` — drop new conversation dumps here (source of truth)
- `processed/active/` — still-relevant conversations
- `processed/archived/` — archived conversations
- `scripts/` — classifier and AI Entity logic
- `.github/workflows/` — automation

## Usage

- To run locally:

```bash
python scripts/archive_classifier.py

	•	To run via GitHub Actions, trigger the Archive Manager workflow.

---

## 3️⃣ `ARCHIVE/COMBINED_ARCHIVE_LIST.md`

This is your **current** archive list, encoded as Markdown so it can grow over time.

```markdown
# StegVerse Combined Archive List

_Last updated: 2025-12-10 (America/Chicago)_

This document tracks **conversations and threads that are considered archived** — no longer active drivers of StegVerse infrastructure, revenue, or priority workflows.

---

## A. Older AI Entity Bundles & Superseded Deployment Packages

- Early “AI Entity Deployment Bundles” superseded by newer designs
- Legacy Phase 1/2/3 ZIP bundles that have been regenerated
- Deprecated SCW automation bundles replaced by SCW v4 tightening
- Any bundle you explicitly requested to “regenerate” and overwrite

---

## B. Outdated NCAAF Week-by-Week Simulations

These are archived **simulations**, not the ingestion engine:

- Past Week 12–13 CFP ranking simulations
- Chaos bracket scenarios
- Nightmare bracket expansions
- Historical “if TTU does X this weekend” trees tied to specific weeks

> Note: The **NCAA ingestion/dev threads** are ACTIVE and live elsewhere.

---

## C. Meta Quest 3 / XR / Headset Usage

- Questions about using Meta Quest 3 while driving or in a truck
- XR safety + headset AI assistant availability
- Whether Meta AI is standard on the headset

These are interesting but not part of core StegVerse infra.

---

## D. Bash Privilege Escalation / Kali Linux Notes

- `bash -p` discussions
- `sudo chmod -s /bin/bash` questions
- Generic Kali privilege escalation chats not tied to StegVerse design

---

## E. Emoji / Unicode Steganography Explorations

- “What kind of data can be contained within an emoji?”
- Differences between iPhone vs Android emoji data handling
- Unicode or hidden-character injection via emoji

> Could be revived later as an EMOJI-STEG module, but currently archived.

---

## F. Early The_Rige1 Speculation Threads

- “Can I interact with The_Rige1 now?” style exploratory chats
- Early non-binding speculation about behavior and powers

> The **formal The_Rige1 design spec** and system docs are ACTIVE and not archived.

---

## G. Geopolitical Scenario Threads (Russia–Ukraine–Taiwan)

- Breadbasket region analysis
- China–Russia alignments
- Artifact / missile-tube relic speculation

These are out-of-scope for current StegVerse infra builds.

---

## H. Gun Law Relaxation / Expansion Lists for Facebook

- 2016–2024 Trump-era gun law summary lists
- Facebook-ready headline content
- Combined status lists (proposed vs in-effect vs challenged)

> The **SocialUpdater repo concept** remains ACTIVE; the political content itself is archived.

---

## I. Declassified Document Thread – Verification Portion Only

- Sections specifically asking “Which parts can be verified?”
- Meta-conversation about verification logistics

> The **memoir narrative content** is ACTIVE in the Memoir Reflections thread and not archived.

---

## J. Miscellaneous Single-Use Q&A

- Meta Quest “can I use this in a vehicle?” style questions
- “Is Meta AI standard?” device questions
- Other isolated, non-infra Q&A with no ongoing impact

---

## How To Add New Items

1. Add a bullet under the appropriate section above, or
2. Add a new section (e.g., `K. <Category Name>`), then
3. Let `archive_classifier.py` update topic files in `ARCHIVE/topics/`.

This index is the human-readable front door for everything the Archive Manager AI Entity has decided is “moot” or historical.
