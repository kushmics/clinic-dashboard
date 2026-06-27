"""Text pipeline: flag abnormal labs, rank urgency, suggest differentials."""
from fastapi import APIRouter

from app.services import medical_nlp, text_processing

router = APIRouter(prefix="/text", tags=["text"])


@router.post("/analyze")
def analyze(content: str) -> dict:
    """Extract findings from a report/case note and surface medical terms."""
    findings = text_processing.extract_findings(content)
    terms = medical_nlp.extract_medical_terms(content)
    return {"findings": findings, "terms": terms}
