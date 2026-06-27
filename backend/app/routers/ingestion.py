"""Upload endpoint: staff drop a lab result, scan, or case description here.

One call does the whole first pass for labs: store -> extract text (or route a
photo/scan to vision) -> run the lab_triage skill -> return the draft. The draft
is for clinician review; nothing is signed here.
"""
import base64
import json
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.config import settings
from app.services.text_processing import route_file
from app.skills import REGISTRY
from app.skills.base import SkillInput

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

MAX_PATIENT_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PATIENT_DOCUMENT_PDF_PAGES = 2
PATIENT_DOCUMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
PATIENT_DOCUMENT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

PATIENT_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "patient_name": {"type": "string"},
        "patient_id": {"type": "string"},
        "patient_id_type": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "age": {"type": ["integer", "null"]},
        "sex": {"type": "string"},
        "source_quality": {"type": "string", "enum": ["clear", "partial", "poor"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "field_confidence": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string", "enum": ["low", "medium", "high"]},
                "patient_id": {"type": "string", "enum": ["low", "medium", "high"]},
                "date_of_birth": {"type": "string", "enum": ["low", "medium", "high"]},
                "age": {"type": "string", "enum": ["low", "medium", "high"]},
                "sex": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "extraction_evidence": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string"},
                "patient_id": {"type": "string"},
                "date_of_birth": {"type": "string"},
                "age": {"type": "string"},
                "sex": {"type": "string"},
            },
        },
        "needs_review": {"type": "boolean"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "document_type",
        "patient_name",
        "patient_id",
        "patient_id_type",
        "date_of_birth",
        "age",
        "sex",
        "source_quality",
        "confidence",
        "field_confidence",
        "extraction_evidence",
        "needs_review",
        "warnings",
    ],
}


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


@router.post("/patient-document")
async def patient_document(file: UploadFile) -> dict:
    """Extract patient identity fields from a document image for staff review.

    This is CV/OCR-assisted intake, not identity verification. Staff must review
    extracted fields before applying them to the active case.
    """
    file_bytes = await file.read()
    original_name = Path(file.filename or "patient-document").name
    suffix = Path(original_name).suffix.lower()
    content_type = file.content_type or mimetypes.guess_type(original_name)[0] or ""
    _validate_patient_document(original_name, content_type, file_bytes)

    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"patient-document-{uuid.uuid4().hex}{suffix or '.bin'}"
    dest.write_bytes(file_bytes)

    return {
        "filename": dest.name,
        "content_type": content_type,
        "stored": True,
        "draft": _extract_patient_identity(dest, content_type),
    }


def _validate_patient_document(filename: str, content_type: str, file_bytes: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    is_supported_extension = suffix in PATIENT_DOCUMENT_EXTENSIONS
    is_supported_mime = content_type in PATIENT_DOCUMENT_MIME_TYPES or content_type.startswith("image/")
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty patient document upload")
    if len(file_bytes) > MAX_PATIENT_DOCUMENT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="patient document is larger than 10 MB")
    if not is_supported_extension or not is_supported_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patient document must be a JPG, PNG, WebP, or PDF",
        )


def _extract_patient_identity(path: Path, content_type: str) -> dict:
    if not settings.openai_api_key:
        return _empty_identity("OPENAI_API_KEY is not configured.")

    try:
        from openai import OpenAI

        vision_parts = _vision_parts_for_patient_document(path, content_type)

        client = OpenAI(api_key=settings.openai_api_key)
        completion = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=900,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract patient identity fields from clinic intake documents. "
                        "Return JSON only. Extract only details visible in the document. "
                        "Do not infer, repair, or invent unclear fields. If a field is unreadable, "
                        "return an empty string or null, mark that field low confidence, and add a warning. "
                        "If multiple pages or repeated labels disagree, keep the clearest visible value and warn. "
                        "This is CV/OCR-assisted intake for staff review, not automatic identity verification."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract patient identity details from this image. "
                                "Possible document types include identity card, clinic report, lab report, "
                                "health booklet, referral form, or unknown. "
                                "For extraction_evidence, describe the visible label/region used in short phrases; "
                                "do not add long excerpts. Match this schema:\n"
                                + json.dumps(PATIENT_ID_SCHEMA, indent=2)
                            ),
                        },
                        *vision_parts,
                    ],
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        return _normalize_identity(_parse_json_object(content))
    except Exception as exc:
        return _empty_identity(f"Patient document extraction failed ({exc.__class__.__name__}).")


def _vision_parts_for_patient_document(path: Path, content_type: str) -> list[dict]:
    if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        return _pdf_page_parts(path)

    mime_type = content_type if content_type.startswith("image/") else mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return [{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}", "detail": "high"}}]


def _pdf_page_parts(path: Path) -> list[dict]:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required to read patient document PDFs") from exc

    parts: list[dict] = []
    with fitz.open(path) as document:
        if document.page_count == 0:
            raise ValueError("PDF has no pages")
        for page_index in range(min(document.page_count, MAX_PATIENT_DOCUMENT_PDF_PAGES)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            encoded = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"},
                }
            )
    return parts


def _parse_json_object(content: str) -> dict:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("patient identity response was not an object")
    return loaded


def _empty_identity(note: str) -> dict:
    return {
        "document_type": "unknown",
        "patient_name": "",
        "patient_id": "",
        "patient_id_type": "",
        "date_of_birth": "",
        "age": None,
        "sex": "",
        "source_quality": "poor",
        "confidence": "low",
        "field_confidence": _empty_field_confidence(),
        "extraction_evidence": _empty_extraction_evidence(),
        "needs_review": True,
        "warnings": [note],
    }


def _normalize_identity(draft: dict) -> dict:
    warnings = draft.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    age = draft.get("age")
    if isinstance(age, bool):
        age = None
    elif isinstance(age, int):
        pass
    elif isinstance(age, float) and age.is_integer():
        age = int(age)
    elif isinstance(age, str) and age.strip().isdigit():
        age = int(age.strip())
    else:
        age = None

    source_quality = draft.get("source_quality")
    if source_quality not in {"clear", "partial", "poor"}:
        source_quality = "partial"

    confidence = draft.get("confidence")
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    field_confidence = _normalize_confidence_map(draft.get("field_confidence"))
    extraction_evidence = _normalize_evidence_map(draft.get("extraction_evidence"))
    needs_review = bool(draft.get("needs_review", False))
    if confidence != "high" or source_quality != "clear" or warnings:
        needs_review = True

    return {
        "document_type": str(draft.get("document_type", "unknown")),
        "patient_name": str(draft.get("patient_name", "")),
        "patient_id": str(draft.get("patient_id", "")),
        "patient_id_type": str(draft.get("patient_id_type", "")),
        "date_of_birth": str(draft.get("date_of_birth", "")),
        "age": age,
        "sex": str(draft.get("sex", "")),
        "source_quality": source_quality,
        "confidence": confidence,
        "field_confidence": field_confidence,
        "extraction_evidence": extraction_evidence,
        "needs_review": needs_review,
        "warnings": [str(item) for item in warnings],
    }


def _empty_field_confidence() -> dict:
    return {field: "low" for field in ("patient_name", "patient_id", "date_of_birth", "age", "sex")}


def _empty_extraction_evidence() -> dict:
    return {field: "" for field in ("patient_name", "patient_id", "date_of_birth", "age", "sex")}


def _normalize_confidence_map(value: object) -> dict:
    if not isinstance(value, dict):
        return _empty_field_confidence()
    result = _empty_field_confidence()
    for field in result:
        confidence = value.get(field)
        result[field] = confidence if confidence in {"low", "medium", "high"} else "low"
    return result


def _normalize_evidence_map(value: object) -> dict:
    if not isinstance(value, dict):
        return _empty_extraction_evidence()
    result = _empty_extraction_evidence()
    for field in result:
        result[field] = str(value.get(field, ""))[:160]
    return result
