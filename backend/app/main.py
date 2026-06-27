"""FastAPI entrypoint for the AI-native clinic dashboard.

First-pass, decision-support only: the AI drafts, a clinician reviews & signs.
Run locally with:  uvicorn app.main:app --reload
"""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.auth import require_auth
from app.config import settings
from app.routers import engine, imaging, ingestion, patients, text

app = FastAPI(title=settings.app_name, version="0.1.0")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Create + seed the shared patient store on startup.
db.init_db()

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
app.include_router(patients.router, dependencies=[Depends(require_auth)])
app.include_router(text.router, dependencies=[Depends(require_auth)])
app.include_router(ingestion.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(engine.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(imaging.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(patients.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(text.router, prefix="/api", dependencies=[Depends(require_auth)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/auth/status")
def auth_status() -> dict:
    return {"enabled": settings.auth_enabled}


@app.get("/api/health")
def api_health() -> dict:
    return health()


@app.get("/api/auth/status")
def api_auth_status() -> dict:
    return auth_status()


if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_app(path: str) -> FileResponse:
        requested = FRONTEND_DIST / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
