"""Upload endpoint: staff drop a lab result, scan, or case description here."""
from pathlib import Path

from fastapi import APIRouter, UploadFile

from app.config import settings

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload")
async def upload(file: UploadFile) -> dict:
    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or "upload.bin")
    dest.write_bytes(await file.read())
    # TODO: route to imaging vs text pipeline by content type, then flag/rank.
    return {"filename": dest.name, "content_type": file.content_type, "stored": True}
