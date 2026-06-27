"""Canonical 5-level clinical acuity scale, shared across skills and frontend.

  Level 1  immediate    (Red)    Life-threatening; immediate resuscitation/intervention.
  Level 2  emergency    (Orange) High-risk; could deteriorate. Target wait <= 10 min.
  Level 3  urgent       (Yellow) Serious, not immediately life-threatening. ~60 min.
  Level 4  semi-urgent  (Green)  Needs treatment when time permits; less acute.
  Level 5  non-urgent   (Blue)   Minor or stable, non-acute issues.

The string slug is the wire value (schema enums, draft["urgency"]); the frontend
maps each slug to its level number, label, and colour.
"""
from __future__ import annotations

# Ordered most-acute -> least-acute. Index + 1 is the level number.
LEVELS = ["immediate", "emergency", "urgent", "semi-urgent", "non-urgent"]

_RANK = {slug: i + 1 for i, slug in enumerate(LEVELS)}

# Legacy 3-tier imaging urgency -> acuity slug (product mapping).
_LEGACY = {"urgent": "emergency", "soon": "urgent", "routine": "non-urgent"}


def from_legacy(value: str | None) -> str:
    """Map an old routine/soon/urgent value (e.g. from the vision model) to a slug."""
    v = (value or "").lower()
    if v in _RANK:
        return v
    return _LEGACY.get(v, "non-urgent")


def rank(slug: str | None) -> int:
    """Lower = more acute. Unknown slugs sort last."""
    return _RANK.get((slug or "").lower(), 99)


def most_acute(slugs) -> str | None:
    """Return the most-acute (lowest level number) slug from an iterable, or None."""
    best = None
    for s in slugs:
        if s and (best is None or rank(s) < rank(best)):
            best = s
    return best
