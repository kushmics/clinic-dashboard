# Clinic Dashboard

AI-native clinic dashboard that handles the **first pass** on clinical work so
doctors can focus on decisions. Staff upload lab results, scans, or a case
description; the AI flags abnormals and ranks urgency, drafts a structured
preliminary imaging report, suggests differential diagnoses with next steps, and
generates referral letters in one click.

**Decision-support only.** The AI drafts; a clinician reviews and signs. Every
step is auditable. The human is never taken out of the decision.

## Decision pending: AI approach

The interpretation layer (image, text, medical-term understanding) is stubbed.
Choose one before wiring it up — it determines which requirements you install:

| Approach | Install | Notes |
|----------|---------|-------|
| **API-first (Claude)** | `requirements.txt` only | Lightest, fastest. Claude vision + text for reports, flags, differentials, letters. |
| **Local ML** | `+ requirements-ml.txt` | Multi-GB (torch, transformers, scispaCy). Runs offline, no PHI leaves the box. |
| **Hybrid** | base `+` parts of ML | Claude for reasoning, local libs for DICOM/OCR/NER. |

Service stubs marked `AI APPROACH PENDING`:
`backend/app/services/{image_processing,text_processing,medical_nlp}.py`

## Capabilities → libraries

- **Image processing** — Pillow, OpenCV, pydicom (DICOM), PyMuPDF/pdf2image, pytesseract (OCR)
- **Text processing** — pypdf, python-docx, pandas, spaCy
- **Medical terms** — rapidfuzz (now); scispaCy + UMLS linker or Claude (when chosen)

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
cp ../.env.example ../.env   # fill in if using the Claude API
uvicorn app.main:app --reload   # http://localhost:8000  (/docs for Swagger)
```
System packages for full image/text support: `tesseract` (OCR) and `poppler`
(`brew install tesseract poppler` on macOS).

**Frontend**
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173  (proxies /api -> :8000)
```

## ⚠️ PHI / safety

Never commit patient data. `data/`, `*.dcm`, and `.env` are gitignored. This is a
prototype for authorized hackathon/clinical-pilot use — not a medical device.
