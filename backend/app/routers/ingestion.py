"""Upload endpoint: staff drop a lab result, scan, or case description here.

One call does the whole first pass for labs: store -> extract text (or route a
photo/scan to vision) -> run the lab_triage skill -> return the draft. The draft
is for clinician review; nothing is signed here.
"""
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile

from app.config import settings
from app.services.text_processing import route_file
from app.skills import REGISTRY
from app.skills.base import SkillInput

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload")
async def upload(
    file: UploadFile,
    skill: str = Form("lab_triage"),
    sex: str | None = Form(None),
    age: int | None = Form(None),
) -> dict:
    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or "upload.bin")
    dest.write_bytes(await file.read())

    # Clinician-supplied context (decision 5: prompt when not in the report).
    context: dict = {}
    if sex:
        context["sex"], context["sex_source"] = sex.lower(), "provided"
    if age is not None:
        context["age"], context["age_source"] = age, "provided"

    # Route: text-layer files -> deterministic text; photos & scanned PDFs -> vision.
    kind, payload = route_file(str(dest))
    if kind == "image":
        skill_input = SkillInput(image_path=payload, context=context)
    else:
        skill_input = SkillInput(text=payload, context=context)

    result = None
    engine = REGISTRY.get(skill)
    if engine is not None:
        out = engine.run(skill_input)
        result = {"skill": out.skill, "draft": out.draft,
                  "urgency": out.urgency, "signed": out.signed}

    return {
        "filename": dest.name,
        "content_type": file.content_type,
        "stored": True,
        "result": result,
    }
