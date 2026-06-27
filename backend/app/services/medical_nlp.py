"""Medical terms understanding: entity recognition + normalization.

Two interchangeable backends (pick when AI approach is decided):
  1. API:   Claude extracts & normalizes clinical entities from free text.
  2. Local: scispaCy pipeline + UMLS linker (see requirements-ml.txt).
"""
from __future__ import annotations


def extract_medical_terms(content: str) -> list[dict]:
    """Return recognized clinical terms with optional codes (SNOMED/ICD/UMLS).

    Stub until backend is chosen. Each item should look like:
      {"text": ..., "category": ..., "code": ..., "system": ...}
    """
    return []
