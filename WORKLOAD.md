# Workload split — 4 tracks

Architecture stays **one unified first-pass engine**, NOT four apps. Each of the
4 features is a pluggable **skill** (`backend/app/skills/<name>/`) with a paired
frontend panel (`frontend/src/panels/`). Every track owns **one feature
end-to-end + one slice of the shared chassis**, so everyone ships a vertical
demo and nobody is stuck on pure plumbing.

## The shared contract (agree FIRST, change together)

Everything plugs into these — lock them down before splitting off:

- `backend/app/skills/base.py` — `Skill`, `SkillInput`, `SkillResult`. Drafts
  only; `signed` always starts `False`.
- `backend/app/routers/engine.py` — `GET /engine/skills`, `POST /engine/run/{skill}`.
- Each skill = `prompt.md` + `schema.json` + `skill.py`. Panels take a `draft` prop.
- **AI APPROACH still deferred** (API-first Claude vs local ML). All `run()` and
  the service stubs are marked `AI APPROACH PENDING`; tracks build the I/O shape
  now and drop the model in once it's chosen.

## Tracks

### Track A — Lab triage + ingestion spine
- **Feature:** `skills/lab_triage/` → flag abnormals, rank urgency, summary.
- **Shared slice:** `routers/ingestion.py` + `services/text_processing.py`
  (extract text, parse lab tables) — the front door the others depend on.
- **Frontend:** `panels/LabTriagePanel.jsx`.

### Track B — Imaging report + image pipeline
- **Feature:** `skills/imaging_report/` → structured prelim report + ROI.
- **Shared slice:** `services/image_processing.py` (DICOM read, OCR, deskew) —
  used by ingestion routing too.
- **Frontend:** `panels/ImagingReportPanel.jsx` (scan viewer + ROI overlay).

### Track C — Differential diagnosis + medical knowledge
- **Feature:** `skills/differential_dx/` → ranked differentials + next steps.
- **Shared slice:** `services/medical_nlp.py` (term recognition/normalization)
  + the curated-JSON knowledge base (RAG-lite) the differentials draw on.
- **Frontend:** `panels/DifferentialDxPanel.jsx`.

### Track D — Referral letters + app shell & sign-off
- **Feature:** `skills/referral_letter/` → one-click letter draft.
- **Shared slice:** frontend shell/layout in `App.jsx` (slots the 4 panels) +
  the clinician **review → sign → audit** flow every feature ends in.
- **Frontend:** `panels/ReferralLetterPanel.jsx` + shell.

## Dependency notes
- Everyone depends on **Track A's** ingestion and **Track D's** shell — build
  those interfaces first so the other tracks can stub against them.
- Track D's referral skill consumes the other three skills' drafts via
  `SkillInput.context`; it integrates last.
- Wire each skill against its `schema.json` immediately — that's the contract
  between backend `run()` and the frontend panel, so both sides move in parallel.

## Suggested order (hackathon)
1. **Together:** confirm `base.py` + `engine.py` + the 4 `schema.json` shapes,
   and pick the AI approach.
2. **Parallel:** each track builds feature + panel against the stubs.
3. **Integrate:** Track D wires the shell, sign-off, and referral chaining.
