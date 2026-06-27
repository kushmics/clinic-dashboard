"""Image processing for scans / photos of reports.

Preprocessing (deskew, OCR, DICOM read) is local and stack-agnostic.
The *interpretation* step is intentionally a stub until the AI approach is
chosen — see README "Decision pending".
"""
from __future__ import annotations


def load_image(path: str):
    """Open a scan as a numpy array. DICOM vs raster handled here.

    Implementation note (do when wiring up):
      - .dcm  -> pydicom.dcmread(path).pixel_array
      - else  -> cv2.imread / PIL.Image.open
    """
    raise NotImplementedError("wire up Pillow / OpenCV / pydicom")


def ocr(path: str) -> str:
    """OCR a scanned document to text (pytesseract + OpenCV preprocessing)."""
    raise NotImplementedError("wire up pytesseract")


def draft_preliminary_report(filename: str) -> dict:
    """Produce a structured preliminary imaging report for clinician sign-off.

    AI APPROACH PENDING: plug in Claude vision OR a local imaging model here.
    """
    return {
        "filename": filename,
        "status": "stub",
        "note": "AI interpretation pending — choose API vs local model.",
        "report": {"impression": None, "findings": [], "urgency": None},
    }
