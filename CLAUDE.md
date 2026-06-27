# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AI-native clinic dashboard for first-pass clinical work. Staff upload labs, scans, or case notes; the AI drafts findings (abnormal flags + urgency, prelim imaging reports, differentials, referral letters). **Decision-support only** — the AI drafts, a clinician reviews and signs. Nothing is ever auto-signed.

## Commands

Backend (from `backend/`):
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # base; add -r requirements-ml.txt only for local-ML path
uvicorn app.main:app --reload            # http://localhost:8000, Swagger at /docs
python3 -m compileall -q app             # fast syntax check, no deps needed
```
Full image/text extraction needs system binaries: `brew install tesseract poppler`.

Frontend (from `frontend/`):
```bash
npm install
npm run dev                              # http://localhost:5173, proxies /api -> :8000
```

No test suite or linter is configured yet.

## Sponsor stack (use these where they fit)

This is a hackathon project; prefer the sponsors' tools so the build qualifies for their tracks. Map each to a concrete role rather than bolting it on:

- **OpenAI / Codex** — the **AI model layer**. Use the OpenAI API (a vision-capable GPT model) for both stages: photo/PDF → structured extraction, and reasoning (triage, differentials, letters). This is now the default for the "API-first" path below — swap the `anthropic` SDK in `requirements.txt` for `openai`. "Codex" can also mean the OpenAI coding agent used to *write* the code (dev-time), distinct from the runtime API — use both senses where they help.
- **Exa** — **semantic retrieval** for the knowledge layer. Best fit is Track C's differential-diagnosis evidence / guideline lookup (the "RAG-lite knowledge base"): Exa search instead of, or feeding, a curated-JSON store. Could also enrich referral letters with current references.
- **Cursor** — the **editor/agent the team builds with** (dev-time tool, not a runtime dependency). No code change; just where development happens.
- **Zo** — **CONFIRM exact capability before relying on it.** Believed to be Zo Computer, an AI-native cloud computer/runtime — candidate use is hosting/deploying the live demo. Do not invent a specific integration until confirmed.

## The one decision still open: AI approach

The interpretation layer is deliberately **stubbed**. Every `Skill.run()` and the `services/*` modules are marked `AI APPROACH PENDING`. Default path given the sponsor stack: **API-first using OpenAI** (vision + text), with **Exa** for retrieval. Alternatives if needed:
- **API-first (OpenAI, default)** — `requirements.txt` only (swap `anthropic` → `openai`). Lightest; one provider for extraction + reasoning.
- **Local ML** — also `requirements-ml.txt` (torch, transformers, scispaCy/UMLS; multi-GB, offline).
- **Hybrid** — OpenAI for reasoning, local libs for DICOM/OCR/NER.

Keep extraction and triage as **two stages with a checkable artifact between them** (normalized values + source kept for clinician verification), not one opaque call — required for auditability. Build the I/O shape against the existing stubs first; the model call drops in behind the same interface.

## Architecture

One **unified first-pass engine**, NOT four separate apps. The pipeline is:
`ingest → structure → reason (a Skill) → score → human sign-off → audit`.

Each of the 4 features is a pluggable **Skill** living in `backend/app/skills/<name>/`, made of three files:
- `prompt.md` — the system prompt
- `schema.json` — the output JSON Schema (the contract between backend `run()` and the frontend panel)
- `skill.py` — a `Skill` subclass implementing `run(SkillInput) -> SkillResult`

The shared contract lives in `backend/app/skills/base.py` (`Skill`, `SkillInput`, `SkillResult`). `SkillResult.signed` always starts `False`. Skills self-register in `skills/__init__.py` as `REGISTRY`, dispatched generically by `routers/engine.py` (`GET /engine/skills`, `POST /engine/run/{skill_name}`). **Treat `base.py` + `engine.py` + the four `schema.json` files as a frozen interface — changing them ripples across all tracks and both backend/frontend, so change them deliberately.**

The four skills: `lab_triage`, `imaging_report`, `differential_dx`, `referral_letter`. `referral_letter` consumes the other three skills' drafts via `SkillInput.context` and integrates last. Each has a matching `frontend/src/panels/<Name>Panel.jsx` that takes a `draft` prop.

Stateless preprocessing (not feature-specific) lives in `backend/app/services/`: `image_processing` (DICOM/OCR/deskew), `text_processing` (PDF/DOCX extraction, lab-table parsing), `medical_nlp` (term recognition/normalization). Skills call into these.

## Working in parallel

Work is split into 4 tracks (see `WORKLOAD.md`), each owning one skill end-to-end plus one chassis slice (ingestion, imaging service, medical-NLP/knowledge base, or app shell + sign-off flow). Wire each skill against its `schema.json` immediately so backend and frontend can move independently.

## PHI / safety

Never commit patient data. `.env`, `data/`, and `*.dcm` are gitignored. Use synthetic data only — this is a prototype, not a cleared medical device; the general-purpose vision model is demo-only and would be swapped for a cleared model in production.
