"""Text extraction and lab-value flagging from reports / case descriptions."""
from __future__ import annotations


def extract_text(path: str) -> str:
    """Pull text from a PDF/DOCX report.

    Implementation note:
      - .pdf  -> pypdf or PyMuPDF (fitz)
      - .docx -> python-docx
    """
    raise NotImplementedError("wire up pypdf / python-docx")


def extract_findings(content: str) -> list[dict]:
    """Parse lab values and flag abnormals / rank urgency.

    AI APPROACH PENDING: rule-based parsing + reference ranges, or hand the
    text to Claude for structured extraction.
    """
    return []  # stub: list of {name, value, unit, flag, urgency}
