"""Cited reference tables + deterministic lookups for lab triage.

Two sources, no hand-tuning (see lab_context.md):
  - critical_values.json  (SGH)  -> never-miss critical thresholds, top of sort.
  - ranges.json           (NUH)  -> sex/age-partitioned adult reference ranges,
                                    LOINC, aliases. Fallback when a report prints
                                    no range of its own.

Everything here is a table lookup. No clinical judgement, no LLM.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "reference_data"


# ---------------------------------------------------------------- unit handling
# Map many printed spellings to one canonical token so we only ever compare like
# with like. We NEVER convert magnitudes — a true unit mismatch routes a value to
# the unassessed bucket rather than guessing a conversion.
_UNIT_SYNONYMS = {
    # ×10⁹/L cell counts. /uL and /µL forms are EXACT equivalents (10³/µL = 10⁹/L),
    # not magnitude conversions, so collapsing them is safe.
    "10^9/l": "10^9/l", "10*9/l": "10^9/l", "10e9/l": "10^9/l", "x10^9/l": "10^9/l",
    "10^9l": "10^9/l", "/nl": "10^9/l", "k/ul": "10^9/l", "k/µl": "10^9/l",
    "thou/ul": "10^9/l", "x10e9/l": "10^9/l", "10⁹/l": "10^9/l",
    "10^3/ul": "10^9/l", "10^3/µl": "10^9/l", "10*3/ul": "10^9/l", "cells/ul": "10^9/l",
    # ×10¹²/L red-cell counts. 10⁶/µL = 10¹²/L.
    "10^12/l": "10^12/l", "x10^12/l": "10^12/l", "m/ul": "10^12/l", "10¹²/l": "10^12/l",
    "10^6/ul": "10^12/l", "10^6/µl": "10^12/l", "10*6/ul": "10^12/l",
    "g/dl": "g/dl", "gm/dl": "g/dl",
    "g/l": "g/l",
    "mmol/l": "mmol/l",
    "umol/l": "umol/l", "µmol/l": "umol/l", "μmol/l": "umol/l",
    "u/l": "u/l", "iu/l": "u/l", "ui/l": "u/l",
    "mg/l": "mg/l", "mg/dl": "mg/dl",
    "ng/ml": "ng/ml", "ug/l": "ng/ml", "µg/l": "ng/ml",
    "pmol/l": "pmol/l", "miu/l": "miu/l", "mu/l": "miu/l",
    "%": "%",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "ratio": "ratio", "": "ratio",
    "fl": "fl", "pg": "pg",
}


def normalize_unit(unit: str | None) -> str:
    """Collapse a printed unit to a canonical token. Empty/None -> 'ratio'."""
    if unit is None:
        return ""
    u = unit.strip().lower()
    u = (u.replace(" ", "").replace("×", "x").replace("·", "")
           .replace("μ", "µ"))
    # superscripts -> ^n
    u = (u.replace("⁹", "^9").replace("¹²", "^12")
           .replace("⁶", "^6").replace("³", "^3"))
    u = u.lstrip("*")                                   # "*10^3/uL" -> "10^3/ul"
    u = u.replace("x10^", "10^").replace("x10", "10")
    return _UNIT_SYNONYMS.get(u, u)


def units_compatible(reported: str | None, expected: str | None) -> bool:
    """True if we may compare a reported value against a table threshold.

    A missing reported unit is treated as compatible (assumed to match) so a bare
    `Potassium 6.5` still triages; the assumption is surfaced upstream.
    """
    if reported is None or str(reported).strip() == "":
        return True
    if expected is None or str(expected).strip() == "":
        return True
    return normalize_unit(reported) == normalize_unit(expected)


# --------------------------------------------------------------- table loading
@lru_cache(maxsize=1)
def _load() -> dict:
    criticals = json.loads((_DATA_DIR / "critical_values.json").read_text())
    ranges = json.loads((_DATA_DIR / "ranges.json").read_text())

    # Build one alias -> canonical_key index across both tables.
    alias_index: dict[str, str] = {}
    for table in (criticals, ranges):
        for key, entry in table.get("analytes", {}).items():
            alias_index.setdefault(_norm_label(key), key)
            for alias in entry.get("aliases", []):
                alias_index.setdefault(_norm_label(alias), key)
    return {
        "criticals": criticals,
        "ranges": ranges,
        "alias_index": alias_index,
        "critical_url": criticals.get("source_url"),
        "range_url": ranges.get("source_url"),
    }


def _norm_label(label: str) -> str:
    """Lowercase, strip punctuation/qualifiers for alias matching."""
    s = label.lower().strip()
    # drop trailing qualifiers in brackets, e.g. "glucose (random)" -> "glucose"
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\b(serum|plasma|blood|total|random|fasting)\b", " ", s)
    s = re.sub(r"[^a-z0-9+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve(label: str) -> tuple[str | None, str | None]:
    """label -> (canonical_key, loinc). Tries exact alias, then token overlap."""
    tables = _load()
    norm = _norm_label(label)
    key = tables["alias_index"].get(norm)
    if key is None:
        # collapse internal spaces (e.g. "wbc count" -> try "wbc")
        first = norm.split(" ")[0]
        key = tables["alias_index"].get(first)
    if key is None:
        return None, None
    loinc = tables["ranges"].get("analytes", {}).get(key, {}).get("loinc")
    return key, loinc


# --------------------------------------------------------------- lookups
def critical_for(key: str) -> dict | None:
    entry = _load()["criticals"].get("analytes", {}).get(key)
    if entry is None:
        return None
    return {**entry, "url": _load()["critical_url"]}


def range_for(key: str, sex: str | None, age: float | None) -> dict | None:
    """Pick the NUH partition for this patient.

    Returns {low, high, unit, url, provisional, basis}. When sex is unknown and
    the analyte is sex-partitioned, we use the NARROWEST envelope (intersection)
    so borderline values surface for review — conservative, never-miss.
    """
    entry = _load()["ranges"].get("analytes", {}).get(key)
    if not entry or not entry.get("ranges"):
        return None
    url = _load()["range_url"]
    unit = entry.get("unit")
    age_adult = age if age is not None else 18  # decision 5: assume adult

    def age_ok(r: dict) -> bool:
        lo = r.get("age_min")
        hi = r.get("age_max")
        return (lo is None or age_adult >= lo) and (hi is None or age_adult <= hi)

    candidates = [r for r in entry["ranges"] if age_ok(r)] or entry["ranges"]

    # Exact sex match?
    if sex in ("male", "female"):
        exact = [r for r in candidates if r.get("sex") in (sex, "any")]
        if exact:
            r = exact[0]
            return {"low": r["low"], "high": r["high"], "unit": unit, "url": url,
                    "provisional": age is None, "basis": f"{sex} adult"}

    # Sex unknown: if a single 'any' range, use it; else intersect partitions.
    any_only = [r for r in candidates if r.get("sex") == "any"]
    if any_only and len(candidates) == len(any_only):
        r = any_only[0]
        return {"low": r["low"], "high": r["high"], "unit": unit, "url": url,
                "provisional": age is None, "basis": "all adults"}

    lows = [r["low"] for r in candidates]
    highs = [r["high"] for r in candidates]
    return {"low": max(lows), "high": min(highs), "unit": unit, "url": url,
            "provisional": True, "basis": "sex unknown — narrowest adult envelope"}


def sources() -> dict:
    """Citation metadata for the audit trail / UI footer."""
    t = _load()
    return {
        "critical": {"name": t["criticals"].get("source"), "url": t["critical_url"]},
        "ranges": {"name": t["ranges"].get("source"), "url": t["range_url"]},
    }
