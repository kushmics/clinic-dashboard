"""Checks for CV-assisted patient document intake.

No network or patient data. These verify the safety rails around model output:
unknown fields stay low-confidence, warnings force review, and unsupported
uploads are rejected before any CV/OCR call.
"""
import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.ingestion import _normalize_identity, _validate_patient_document


def test_normalize_identity_requires_review_for_uncertain_fields():
    draft = _normalize_identity(
        {
            "document_type": "health booklet",
            "patient_name": "Example Patient",
            "patient_id": "",
            "age": "58",
            "sex": "female",
            "source_quality": "partial",
            "confidence": "medium",
            "field_confidence": {"patient_name": "high", "patient_id": "low"},
            "warnings": ["Patient ID was unreadable."],
        }
    )

    assert draft["patient_name"] == "Example Patient"
    assert draft["patient_id"] == ""
    assert draft["age"] == 58
    assert draft["field_confidence"]["patient_name"] == "high"
    assert draft["field_confidence"]["patient_id"] == "low"
    assert draft["needs_review"] is True
    print("✓ uncertain patient document fields remain review-only")


def test_validate_patient_document_rejects_unsupported_upload():
    try:
        _validate_patient_document("notes.txt", "text/plain", b"patient")
    except HTTPException as exc:
        assert exc.status_code == 400
        print("✓ unsupported patient document upload rejected")
        return
    raise AssertionError("Unsupported upload was accepted")


def test_validate_patient_document_accepts_image_upload():
    _validate_patient_document("id-card.png", "image/png", b"fake image bytes")
    print("✓ supported patient document image accepted")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} patient_document_intake checks passed.")
