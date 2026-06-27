# Clinic Dashboard

AI-native clinic dashboard that handles the **first pass** on clinical work so
doctors can focus on decisions. Staff upload lab results, scans, or a case
description; the AI flags abnormals and ranks urgency, drafts a structured
preliminary imaging report, suggests differential diagnoses with next steps, and
generates referral letters in one click.

**Decision-support only.** The AI drafts; a clinician reviews and signs. Every
step is auditable. The human is never taken out of the decision.

## Try it instantly

Clone, then one command — sets up both halves, seeds **5 sample patients**, and
serves the whole app on a single URL:

```bash
./start.sh        # then open http://localhost:8000
```

On the sign-in screen the demo access is pre-filled — just press **Sign in**.
No API keys needed: lab triage, differentials, the imaging reads on the seeded
patients, and referral letters all work out of the box. Add an `OPENAI_API_KEY`
to `.env` only if you want live X-ray reads or the patient-ID scanner.

## AI model layer

The interpretation layer is **API-first on OpenAI**:

| Stage | Model | Env var |
|-------|-------|---------|
| Reasoning — triage, differentials, referral letters | `gpt-5.4` | `OPENAI_MODEL` |
| Chest X-ray vision reads + patient-ID scanner | `gpt-4o-mini` | `OPENAI_VISION_MODEL` |
| Differential evidence / guideline lookup | Exa semantic search | `EXA_API_KEY` |

The lab-triage and differential engines are **deterministic** (cited reference
tables + a curated knowledge base), so the seeded demo runs with **no API keys**.
Set `OPENAI_API_KEY` to unlock live X-ray reads and the ID scanner.

A local-ML path (`requirements-ml.txt`: torch, transformers, scispaCy/UMLS) stays
available for offline, no-PHI-leaves-the-box deployments — install it only if you
swap onto that path.

## Capabilities → libraries

- **Image processing** — Pillow, OpenCV, pydicom (DICOM), PyMuPDF/pdf2image, pytesseract (OCR)
- **Text processing** — pypdf, python-docx, pandas
- **Medical terms** — rapidfuzz; scispaCy + UMLS linker on the local-ML path

## Layout

```
backend/    FastAPI app (routers: ingestion, imaging, text; services: stubs)
frontend/   Vite + React dashboard
```

## Run it

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # add OPENAI_API_KEY for live vision (optional)
uvicorn app.main:app --reload   # http://localhost:8000  (/docs for Swagger)
```
System packages for full image/text support: `tesseract` (OCR) and `poppler`
(`brew install tesseract poppler` on macOS).

Protected API routes require a bearer token. For local demo use, the default
token is `clinic-demo-token`; change it with `AUTH_TOKEN=...` in `.env`, or set
`AUTH_ENABLED=false` to disable the gate during development.

**Frontend**
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173  (proxies /api -> :8000)
```
Sign in with the same access token configured for the backend.


## Deploy

The repo ships a production image and a Render blueprint. The multi-stage
`Dockerfile` builds the Vite frontend, installs `backend/requirements-deploy.txt`,
and serves the built UI **and** the API from one FastAPI process on `$PORT`.

- **Render** — point a Blueprint at `render.yaml` (health check `/health`). Set
  `AUTH_TOKEN` (required); add `OPENAI_API_KEY` / `EXA_API_KEY` for live AI.
- **Any Docker host** — `docker build -t clinic-dashboard . && docker run -p 8000:8000 -e AUTH_TOKEN=... clinic-dashboard`

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full env-var list and verification steps.

## ⚠️ PHI / safety

Never commit patient data. `data/`, `*.dcm`, and `.env` are gitignored. This is a
prototype for authorized hackathon/clinical-pilot use — not a medical device.
