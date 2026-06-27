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

## The one decision still open: AI approach

The interpretation layer is deliberately **stubbed**. Every `Skill.run()` and the `services/*` modules are marked `AI APPROACH PENDING`. Before implementing them, the team picks one path, which determines dependencies:
- **API-first (Claude)** — `requirements.txt` only. Lightest; Claude vision + text.
- **Local ML** — also `requirements-ml.txt` (torch, transformers, scispaCy/UMLS; multi-GB, offline).
- **Hybrid** — Claude for reasoning, local libs for DICOM/OCR/NER.

When implementing, build the I/O shape against the existing stubs first; the model call drops in behind the same interface.

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
