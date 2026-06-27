"""Imaging pipeline: draft a structured preliminary report on a scan."""
from pathlib import Path

from fastapi import APIRouter, UploadFile

from app.config import settings
from app.services import image_processing
from app.skills.imaging_report.skill import ImagingReportSkill
from app.skills.base import SkillInput

router = APIRouter(prefix="/imaging", tags=["imaging"])


@router.post("/report")
def draft_report(filename: str) -> dict:
    """Return a structured preliminary report draft for clinician review."""
    return image_processing.draft_preliminary_report(filename)


@router.post("/analyze-upload")
async def analyze_upload(file: UploadFile) -> dict:
    """Upload a scan and return an AI preliminary imaging report draft."""
    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or "scan.jpg")
    dest.write_bytes(await file.read())

    skill = ImagingReportSkill()
    result = skill.run(SkillInput(image_path=str(dest)))
    return {
        "filename": dest.name,
        "content_type": file.content_type,
        "skill": result.skill,
        "draft": result.draft,
        "signed": result.signed,
    }
