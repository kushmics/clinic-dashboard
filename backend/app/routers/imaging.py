"""Imaging pipeline: draft a structured preliminary report on a scan."""
from fastapi import APIRouter

from app.services import image_processing

router = APIRouter(prefix="/imaging", tags=["imaging"])


@router.post("/report")
def draft_report(filename: str) -> dict:
    """Return a structured preliminary report draft for clinician review."""
    return image_processing.draft_preliminary_report(filename)
