"""Stage 2 — triage: deterministic flag + never-miss sort + facts-only summary.

Pure table lookups against the cited SGH/NUH data. No LLM, no clinical judgement,
no severity decided here. We surface and order; differential_dx interprets.

Pipeline per measurement:
  critical (SGH) ?  ->  out of range (report's printed range, else NUH) ?  ->
  no range on file / unit mismatch  ->  unassessed (never dropped, never guessed)
"""
from __future__ import annotations

from . import reference as ref
from .extraction import Extraction, Measurement


def triage(extraction: Extraction, context: dict | None = None) -> dict:
    """Build the lab_triage draft (validates against schema.json)."""
    context = {**extraction.context, **(context or {})}  # caller context wins
    sex, sex_source = _resolve_field(context, "sex")
    age, age_source = _resolve_field(context, "age")
    priors: dict = context.get("priors") or {}

    assumptions: list[str] = []
    if sex is None:
        assumptions.append("Sex not supplied — sex-partitioned ranges assessed "
                           "against the narrowest adult envelope (flags are provisional).")
    if age is None:
        assumptions.append("Age not supplied — assumed adult (≥18).")

    abnormals, normals, unassessed = [], [], []
    for m in extraction.measurements:
        bucket, record = _classify(m, sex, age, priors)
        if bucket == "abnormal":
            abnormals.append(record)
        elif bucket == "normal":
            normals.append(record)
        else:
            unassessed.append(record)

    abnormals.sort(key=_sort_key)
    # Map onto the 5-level acuity scale: a critical value is immediately
    # actionable (L1), any other out-of-range value is urgent (L3), all-clear
    # is non-urgent (L5).
    urgency = ("immediate" if any(a["flag"] == "critical" for a in abnormals)
               else "urgent" if abnormals else "non-urgent")

    return {
        "abnormals": abnormals,
        "unassessed": unassessed,
        "normals": normals,
        "assumptions": assumptions,
        "context_used": {
            "sex": sex, "sex_source": sex_source,
            "age": age, "age_source": age_source,
            "priors_available": bool(priors),
        },
        "urgency": urgency,
        "summary": _summary(abnormals, normals, unassessed, urgency, assumptions),
    }


def _resolve_field(context: dict, field: str) -> tuple:
    """Return (value, source) where source is provided|report|assumed|None."""
    val = context.get(field)
    if val is None:
        return None, None
    src = context.get(f"{field}_source", "provided")
    return val, src


# --------------------------------------------------------------- classification
def _classify(m: Measurement, sex, age, priors) -> tuple[str, dict]:
    key, loinc = ref.resolve(m.label)

    if m.value is None:
        return "unassessed", _unassessed(m, "non-numeric value")

    crit = ref.critical_for(key) if key else None

    # Reference range: prefer the report's own printed range, else NUH.
    range_low = range_high = None
    range_source = range_unit = range_str = None
    provisional = False
    if m.printed_low is not None and m.printed_high is not None:
        range_low, range_high = m.printed_low, m.printed_high
        range_source, range_unit = "report", m.unit
        range_str = m.printed_range
    elif key:
        nuh = ref.range_for(key, sex, age)
        if nuh:
            range_low, range_high = nuh["low"], nuh["high"]
            range_source, range_unit = "NUH", nuh["unit"]
            range_str = f"{nuh['low']}–{nuh['high']} {nuh['unit']}".strip()
            provisional = nuh["provisional"]

    # 1) Critical screen (SGH) — always first, overrides range, never provisional.
    if crit:
        if not ref.units_compatible(m.unit, crit["unit"]):
            return "unassessed", _unassessed(
                m, f"unit mismatch: reported '{m.unit}', SGH critical table uses "
                   f"'{crit['unit']}' — not assessed (no magnitude conversion guessed)")
        if crit.get("high") is not None and m.value > crit["high"]:
            return "abnormal", _abnormal(m, key, loinc, "critical", "high",
                                         crit["high"], "SGH", crit["url"],
                                         range_str, False, priors)
        if crit.get("low") is not None and m.value < crit["low"]:
            return "abnormal", _abnormal(m, key, loinc, "critical", "low",
                                         crit["low"], "SGH", crit["url"],
                                         range_str, False, priors)

    # 2) Reference-range screen.
    if range_low is not None and range_high is not None:
        if not ref.units_compatible(m.unit, range_unit):
            return "unassessed", _unassessed(
                m, f"unit mismatch: reported '{m.unit}', reference range in "
                   f"'{range_unit}' — not assessed")
        url = ref.sources()["ranges"]["url"] if range_source == "NUH" else None
        if m.value > range_high:
            return "abnormal", _abnormal(m, key, loinc, "high", "high",
                                         range_high, range_source, url,
                                         range_str, provisional, priors)
        if m.value < range_low:
            return "abnormal", _abnormal(m, key, loinc, "low", "low",
                                         range_low, range_source, url,
                                         range_str, provisional, priors)
        return "normal", {
            "analyte": _title(key, m.label), "loinc": loinc,
            "value": m.value, "unit": m.unit,
            "reference_range": range_str, "range_source": range_source,
        }

    # 3) Nothing to assess against.
    if crit:
        return "unassessed", _unassessed(
            m, "screened against SGH critical table (not critical); no reference "
               "range on file to confirm normal vs mildly abnormal")
    return "unassessed", _unassessed(
        m, "no reference range on file (report printed none; analyte not in NUH catalog)")


def _abnormal(m, key, loinc, flag, direction, threshold, table, url,
              range_str, provisional, priors) -> dict:
    sym = "≥" if direction == "high" else "≤"
    tier = {"critical": "Critical", "high": "High", "low": "Low"}[flag]
    if table == "SGH":
        note = f"{tier} {direction} — SGH critical {sym} {threshold} {m.unit or ''}".strip() + "."
    elif table == "report":
        note = f"{tier} — outside the report's printed range {range_str}."
    else:
        note = f"{tier} — outside NUH adult range {range_str}."
        if provisional:
            note += " Provisional (sex/age assumed)."
    return {
        "analyte": _title(key, m.label),
        "loinc": loinc,
        "value": m.value,
        "unit": m.unit,
        "flag": flag,
        "direction": direction,
        "reference_range": range_str,
        "threshold_source": {"table": table, "rule": direction,
                             "threshold": threshold, "url": url},
        "provisional": provisional,
        "delta": _delta(key, m.value, priors),
        "note": note,
        "_dev": _deviation(m.value, direction, threshold, range_str),  # sort only
    }


def _unassessed(m: Measurement, reason: str) -> dict:
    return {"analyte": m.label, "value": (m.value if m.value is not None else m.raw_value),
            "unit": m.unit, "reason": reason, "source_text": m.source_text or None}


def _delta(key, value, priors) -> dict | None:
    if not key or key not in priors:
        return None
    try:
        prior = float(priors[key])
    except (TypeError, ValueError):
        return None
    change = round(value - prior, 4)
    pct = round((change / prior) * 100, 1) if prior else None
    arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
    return {"prior": prior, "change": change, "pct": pct,
            "note": f"{arrow} from prior {prior} (Δ {change}"
                    + (f", {pct}%)" if pct is not None else ")")}


# ------------------------------------------------------------------- sort + text
def _deviation(value, direction, threshold, range_str) -> float:
    """Magnitude of deviation for ordering only — NOT a clinical severity score."""
    try:
        if direction == "high":
            return float(value) - float(threshold)
        return float(threshold) - float(value)
    except (TypeError, ValueError):
        return 0.0


def _sort_key(a: dict):
    # critical before non-critical; then larger deviation first.
    return (0 if a["flag"] == "critical" else 1, -abs(a.get("_dev", 0.0)))


def _title(key: str | None, fallback: str) -> str:
    if not key:
        return fallback.strip()
    return key.replace("_", " ").title()


def _summary(abnormals, normals, unassessed, urgency, assumptions) -> str:
    total = len(abnormals) + len(normals) + len(unassessed)
    crit = [a for a in abnormals if a["flag"] == "critical"]
    out = [a for a in abnormals if a["flag"] != "critical"]
    parts = [f"{len(abnormals)} of {total} result(s) outside reference."]
    if crit:
        items = "; ".join(f"{a['analyte']} {a['value']} {a['unit'] or ''}".strip()
                          + f" ({a['note'].rstrip('.')})" for a in crit[:3])
        parts.append(f"{len(crit)} critical: {items}.")
    if out:
        items = "; ".join(f"{a['analyte']} {a['value']} {a['unit'] or ''}".strip()
                          + f" {a['direction']}" for a in out[:3])
        parts.append(f"{len(out)} out-of-range: {items}"
                     + ("…" if len(out) > 3 else "") + ".")
    parts.append(f"{len(normals)} within range.")
    if unassessed:
        parts.append(f"{len(unassessed)} not assessed (see list).")
    if any(a.get("provisional") for a in abnormals):
        parts.append("Some flags provisional pending sex/age confirmation.")
    parts.append(f"Urgency: {urgency}.")
    return " ".join(parts)


def strip_internal(draft: dict) -> dict:
    """Drop sort-only private fields before the draft leaves the skill."""
    for a in draft.get("abnormals", []):
        a.pop("_dev", None)
    return draft
