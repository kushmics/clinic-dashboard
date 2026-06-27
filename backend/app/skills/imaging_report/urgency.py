"""Deterministic urgency scoring for imaging findings.

Uses the Manchester Triage System (MTS) five-tier color-coded scale:

    Level 1  Red     Immediate     — life-threatening, immediate intervention
    Level 2  Orange  Emergency     — high-risk, could become life-threatening
    Level 3  Yellow  Urgent        — serious but not immediately life-threatening
    Level 4  Green   Semi-Urgent   — needs treatment when time permits
    Level 5  Blue    Non-Urgent    — minor / stable / normal

Base score (per finding, max wins):
    5  immediate  — active life-threat keywords
    4  emergency  — critical but not yet life-threatening
    3  urgent     — significant abnormality
    2  semi-urgent — minor abnormality
    1  non-urgent — explicitly normal / no finding

Modifiers (additive decimals, on top of base):
    +0.3  age >= 70           elderly patients warrant faster review
    +0.2  age >= 50           middle-age risk factor
    +0.1  multiple findings   >= 3 non-normal findings compound risk
    +0.2  multiple ROIs       >= 3 regions flagged
    +0.2  high-risk history   keywords in patient history

Final composite = ceil(base + sum(modifiers)), capped at 5.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Triage tier definitions
# ═══════════════════════════════════════════════════════════════════════════

TRIAGE_TIERS = {
    5: {"level": 1, "label": "Immediate",    "color": "red",    "target_minutes": 0},
    4: {"level": 2, "label": "Emergency",    "color": "orange", "target_minutes": 10},
    3: {"level": 3, "label": "Urgent",       "color": "yellow", "target_minutes": 60},
    2: {"level": 4, "label": "Semi-Urgent",  "color": "green",  "target_minutes": 120},
    1: {"level": 5, "label": "Non-Urgent",   "color": "blue",   "target_minutes": 240},
}


# ═══════════════════════════════════════════════════════════════════════════
# Keyword tiers (5 = immediate, 4 = emergency, 3 = urgent)
# Findings scoring 2 (semi-urgent) or 1 (non-urgent) use the fallback.
# ═══════════════════════════════════════════════════════════════════════════

_IMMEDIATE_PATTERNS: list[str] = [
    r"tension\s+pneumothorax",
    r"aortic\s+dissection",
    r"cardiac\s+arrest",
    r"pericardial\s+tamponade",
    r"active\s+(bleed|hemorrhag)",
    r"ruptured?\s+aneurysm",
    r"midline\s+shift",
    r"cerebral\s+hernia",
    r"acute\s+(stroke|infarct)",
    r"(subdural|epidural|subarachnoid)\s+(hemat|hemorrhag)",
    r"spinal\s+cord\s+compress",
    r"bowel\s+perforation",
    r"ruptured?\s+(spleen|liver|kidney)",
    r"life[\s-]*threaten",
]

_EMERGENCY_PATTERNS: list[str] = [
    r"pneumothorax",
    r"pulmonary\s+embol",
    r"intracranial\s+hemorrhag",
    r"mass\s+effect",
    r"mediastinal\s+(widening|shift)",
    r"unstable\s+fractur",
    r"cervical\s+fractur",
    r"(flail|multiple.*rib)\s+fractur",
    r"bowel\s+obstruction",
    r"free\s+(air|gas)",
    r"torsion",
    r"acute\s+ischem",
    r"septic",
    r"critical",
    r"emergent",
    r"stat\b",
]

_URGENT_PATTERNS: list[str] = [
    r"(suspicious|indeterminate)\s+(mass|lesion|nodule)",
    r"malignant",
    r"metasta",
    r"\bmass\b",
    r"\bnodule",
    r"\btumou?r\b",
    r"neoplasm",
    r"lymphadenopath",
    r"pneumonia",
    r"\babscess\b",
    r"empyema",
    r"osteomyelitis",
    r"pleural\s+effusion",
    r"pericardial\s+effusion",
    r"ascites",
    r"cardiomegal",
    r"heart\s+failure",
    r"congesti",
    r"pulmonary\s+edema",
    r"(aortic|mitral|tricuspid)\s+(stenosis|regurgit)",
    r"fractur",
    r"disloc",
    r"aneurysm",
    r"(deep\s+vein|dvt)\s*thrombo",
    r"stenosis",
    r"occlusion",
    r"(renal|kidney)\s+(calcul|stone)",
    r"hydronephrosis",
    r"consolidat",
    r"infiltrat",
    r"atelectasis",
    r"(bowel\s+)?wall\s+thicken",
    r"white\s+matter\s+(lesion|disease|change)",
    r"demyelinat",
    r"encephalit",
]

_NORMAL_PATTERNS: list[str] = [
    r"no\s+(acute|significant|obvious)\s+(abnormalit|patholog|finding)",
    r"(within|appears?\s+within)\s+normal\s+limit",
    r"unremarkable",
    r"no\s+(evidence|sign)\s+of",
    r"normal\s+(morpholog|appearance|anatomy|size|study|cardiac|brain|lung|bowel|liver|kidney|spleen)",
    r"no\s+(acute\s+)?(intracranial|pulmonary|abdominal)\s+patholog",
    r"clear\s+(lung|cardiac|chest|abdomen|brain|bowel)",
    r"well[\s-]?positioned",
    r"intact\b",
    r"no\s+fractur",
    r"negative\s+(for|study)",
    r"normal\b.*\b(silhouette|contour|caliber|volume)",
    r"stable\b",
    r"benign",
]

_IMMEDIATE_RE = [re.compile(p, re.IGNORECASE) for p in _IMMEDIATE_PATTERNS]
_EMERGENCY_RE = [re.compile(p, re.IGNORECASE) for p in _EMERGENCY_PATTERNS]
_URGENT_RE = [re.compile(p, re.IGNORECASE) for p in _URGENT_PATTERNS]
_NORMAL_RE = [re.compile(p, re.IGNORECASE) for p in _NORMAL_PATTERNS]

_NEGATION_RE = re.compile(
    r"\b(no|not|without|absent|negative|ruled?\s+out|unremarkable|deny|denies|denied"
    r"|no\s+evidence|no\s+sign|no\s+significant|no\s+acute|no\s+obvious)\b",
    re.IGNORECASE,
)
_NEGATION_WINDOW = 60

_HIGH_RISK_HISTORY = re.compile(
    r"(cancer|malignan|chemother|immunocompromis|immunosuppress|transplant"
    r"|anticoagul|warfarin|heparin|dialysis|copd|chf|heart\s+failure"
    r"|cirrhosis|hiv|aids|sickle\s+cell|stroke\s+history|mi\s+history"
    r"|recent\s+surger|icu|ventilat|sepsis|trauma)",
    re.IGNORECASE,
)

MAX_COMPOSITE = 5.0


def _is_negated(text: str, match: re.Match) -> bool:
    start = max(0, match.start() - _NEGATION_WINDOW)
    prefix = text[start:match.start()]
    return bool(_NEGATION_RE.search(prefix))


def _parse_age(context: dict | None) -> int | None:
    if not context:
        return None
    age = context.get("age")
    if isinstance(age, (int, float)):
        return int(age)
    if isinstance(age, str):
        digits = re.search(r"\d+", age)
        if digits:
            return int(digits.group())
    return None


def _match_tier(text: str, patterns: list[re.Pattern], tier_name: str, score: float,
                triggers: list[dict]) -> tuple[float, str, str | None]:
    for pattern in patterns:
        match = pattern.search(text)
        if match and not _is_negated(text, match):
            triggers.append({
                "finding": text,
                "matched_pattern": pattern.pattern,
                "tier": tier_name,
            })
            return score, tier_name, pattern.pattern
    return 0.0, "", None


@dataclass(frozen=True)
class UrgencyScore:
    triage_level: int       # 1-5 (Manchester scale)
    triage_label: str       # "Immediate", "Emergency", "Urgent", "Semi-Urgent", "Non-Urgent"
    triage_color: str       # "red", "orange", "yellow", "green", "blue"
    target_minutes: int     # recommended max wait time
    base_score: float       # raw max finding score (1-5)
    composite: float        # base + modifiers, rounded up to nearest int
    modifiers: dict[str, float]
    triggers: list[dict[str, str]]
    finding_scores: list[dict[str, Any]]


def score_urgency(
    findings: list[str],
    impression: str = "",
    regions_of_interest: list[dict] | None = None,
    context: dict | None = None,
) -> UrgencyScore:
    """Score urgency using Manchester Triage System tiers.

    Formula:
        base = max(score(finding) for each finding)
        raw_composite = base + age_mod + count_mod + roi_mod + history_mod
        composite = min(ceil(raw_composite), 5)
        triage_level = 6 - composite   (so composite 5 = level 1 Immediate)
    """
    all_texts = list(findings)
    if impression:
        all_texts.append(impression)
    if regions_of_interest:
        all_texts.extend(roi.get("label", "") for roi in regions_of_interest)

    triggers: list[dict[str, str]] = []
    finding_scores: list[dict[str, Any]] = []
    base_score = 0.0
    n_abnormal = 0

    for text in all_texts:
        if not text.strip():
            continue

        entry_score = 2.0  # default: semi-urgent
        entry_tier = "semi-urgent"
        matched_pattern = None

        # Try each tier top-down
        for patterns, tier_name, tier_score in [
            (_IMMEDIATE_RE, "immediate", 5.0),
            (_EMERGENCY_RE, "emergency", 4.0),
            (_URGENT_RE,    "urgent",    3.0),
        ]:
            s, t, p = _match_tier(text, patterns, tier_name, tier_score, triggers)
            if s > 0:
                entry_score, entry_tier, matched_pattern = s, t, p
                break

        # Check if explicitly normal
        if entry_score <= 2.0:
            for pattern in _NORMAL_RE:
                if pattern.search(text):
                    entry_score = 1.0
                    entry_tier = "non-urgent"
                    matched_pattern = pattern.pattern
                    break

        if entry_score >= 2.0:
            n_abnormal += 1

        finding_scores.append({
            "text": text,
            "score": entry_score,
            "tier": entry_tier,
            "matched_pattern": matched_pattern,
        })

        base_score = max(base_score, entry_score)

    # ── Modifiers ───────────────────────────────────────────────────
    modifiers: dict[str, float] = {}

    age = _parse_age(context)
    if age is not None:
        if age >= 70:
            modifiers["age_>=70"] = 0.3
        elif age >= 50:
            modifiers["age_>=50"] = 0.2

    if n_abnormal >= 3:
        modifiers["multiple_findings"] = 0.1

    n_rois = len(regions_of_interest) if regions_of_interest else 0
    if n_rois >= 3:
        modifiers["multiple_rois"] = 0.2

    history = context.get("history", "") if context else ""
    if history and _HIGH_RISK_HISTORY.search(history):
        modifiers["high_risk_history"] = 0.2

    modifier_total = sum(modifiers.values())
    raw_composite = base_score + modifier_total
    composite = min(math.ceil(raw_composite), 5)

    # Map composite to triage tier (higher composite = more urgent = lower level number)
    tier_info = TRIAGE_TIERS.get(composite, TRIAGE_TIERS[1])

    return UrgencyScore(
        triage_level=tier_info["level"],
        triage_label=tier_info["label"],
        triage_color=tier_info["color"],
        target_minutes=tier_info["target_minutes"],
        base_score=round(base_score, 1),
        composite=round(raw_composite, 2),
        modifiers=modifiers,
        triggers=triggers,
        finding_scores=finding_scores,
    )
