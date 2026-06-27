"""FastAPI entrypoint for the AI-native clinic dashboard.

First-pass, decision-support only: the AI drafts, a clinician reviews & signs.
Run locally with:  uvicorn app.main:app --reload
"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_auth
from app.config import settings
from app.routers import engine, imaging, ingestion, text

app = FastAPI(title=settings.app_name, version="0.1.0")

# Allow the Vite dev server to call the API during the hackathon.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(ingestion.router, dependencies=[Depends(require_auth)])
app.include_router(engine.router, dependencies=[Depends(require_auth)])
app.include_router(imaging.router, dependencies=[Depends(require_auth)])
app.include_router(text.router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/auth/status")
def auth_status() -> dict:
    return {"enabled": settings.auth_enabled}
