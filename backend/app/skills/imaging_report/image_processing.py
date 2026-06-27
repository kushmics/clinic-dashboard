##backend/app/skills/imaging_report/image_processing.py

"""Compatibility wrapper for imaging_report preprocessing.

The canonical implementation lives in app.services.image_processing so the
shared ingestion and imaging routes can use the same DICOM/OCR code.
"""
from app.services.image_processing import annotate_image, load_image, ocr, prepare_image

__all__ = ["annotate_image", "load_image", "ocr", "prepare_image"]
