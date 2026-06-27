"""Deterministic urgency scoring for imaging findings.

The vision model extracts findings; this module scores severity using
keyword-based rules derived from radiology triage standards (ACR, ESR).
The LLM's own urgency label is ignored — this is the source of truth.

Score mapping:
    3  urgent  — critical / life-threatening, needs immediate attention
    2  soon    — significant abnormality, expedited review
    1  routine — minor or normal, standard turnaround
    0  normal  — explicitly normal / no finding (subset of routine)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Keyword tiers — longest-match-first within each tier.
# Each entry is a regex pattern (case-insensitive).
# ═══════════════════════════════════════════════════════════════════════════

_URGENT_PATTERNS: list[str] = [
    # Vascular emergencies
    r"aortic\s+dissection",
    r"pulmonary\s+embol",
    r"ruptured?\s+aneurysm",
    r"active\s+(bleed|hemorrhag)",
    r"tension\s+pneumothorax",
    # Intracranial emergencies
    r"midline\s+shift",
    r"mass\s+effect",
    r"(subdural|epidural|subarachnoid)\s+(hemat|hemorrhag)",
    r"acute\s+(stroke|infarct|ischem)",
    r"cerebral\s+hernia",
    r"intracranial\s+hemorrhag",
    # Thoracic emergencies
    r"pneumothorax",
    r"(flail|multiple.*rib)\s+fractur",
    r"mediastinal\s+(widening|shift)",
    r"pericardial\s+tamponade",
    r"cardiac\s+arrest",
    # Abdominal emergencies
    r"free\s+(air|gas)",
    r"bowel\s+(perforation|obstruction)",
    r"ruptured?\s+(spleen|liver|kidney)",
    r"torsion",
    # Spine / trauma
    r"unstable\s+fractur",
    r"spinal\s+cord\s+compress",
    r"cervical\s+fractur",
    # General critical
    r"life[\s-]*threaten",
    r"critical",
    r"emergent",
    r"stat\b",
]

_SOON_PATTERNS: list[str] = [
    # Masses and nodules
    r"(suspicious|indeterminate)\s+(mass|lesion|nodule)",
    r"malignant",
    r"metasta",
    r"\bmass\b",
    r"\bnodule",
    r"\btumou?r\b",
    r"neoplasm",
    r"lymphadenopath",
    # Infections
    r"pneumonia",
    r"\babscess\b",
    r"empyema",
    r"osteomyelitis",
    r"septic",
    # Effusions and collections
    r"pleural\s+effusion",
    r"pericardial\s+effusion",
    r"ascites",
    # Cardiac
    r"cardiomegal",
    r"heart\s+failure",
    r"congesti",
    r"pulmonary\s+edema",
    r"(aortic|mitral|tricuspid)\s+(stenosis|regurgit)",
    # Fractures (non-critical)
    r"fractur",
    r"disloc",
    # Vascular (non-emergent)
    r"aneurysm",
    r"(deep\s+vein|dvt)\s*thrombo",
    r"stenosis",
    r"occlusion",
    # Renal
    r"(renal|kidney)\s+calcul",
    r"hydronephrosis",
    r"(renal|kidney)\s+stone",
    # Inflammatory
    r"consolidat",
    r"infiltrat",
    r"atelectasis",
    r"(bowel\s+)?wall\s+thicken",
    # Neuro
    r"white\s+matter\s+(lesion|disease|change)",
    r"demyelinat",
    r"encephalit",
]

_NORMAL_PATTERNS: list[str] = [
    r"no\s+(acute|significant|obvious)\s+(abnormalit|patholog|finding)",
    r"(within|appears?\s+within)\s+normal\s+limit",
    r"unremarkable",
    r"no\s+(evidence|sign)\s+of",
    r"normal\s+(morpholog|appearance|anatomy|size|study)",
    r"no\s+(acute\s+)?(intracranial|pulmonary|abdominal)\s+patholog",
    r"clear\s+lung",
    r"well[\s-]?positioned",
    r"intact\b",
    r"no\s+fractur",
    r"negative\s+(for|study)",
]

# Precompile for performance
_URGENT_RE = [re.compile(p, re.IGNORECASE) for p in _URGENT_PATTERNS]
_SOON_RE = [re.compile(p, re.IGNORECASE) for p in _SOON_PATTERNS]
_NORMAL_RE = [re.compile(p, re.IGNORECASE) for p in _NORMAL_PATTERNS]

# Negation window: if any of these appear within 6 words before the match, it's negated.
_NEGATION_RE = re.compile(
    r"\b(no|not|without|absent|negative|ruled?\s+out|unremarkable|deny|denies|denied"
    r"|no\s+evidence|no\s+sign|no\s+significant|no\s+acute|no\s+obvious)\b",
    re.IGNORECASE,
)
_NEGATION_WINDOW = 60  # characters before the match to scan for negation


def _is_negated(text: str, match: re.Match) -> bool:
    """Check if a pattern match is preceded by a negation phrase."""
    start = max(0, match.start() - _NEGATION_WINDOW)
    prefix = text[start:match.start()]
    return bool(_NEGATION_RE.search(prefix))


@dataclass(frozen=True)
class UrgencyScore:
    level: str          # "urgent", "soon", or "routine"
    score: int          # 3, 2, 1, or 0
    triggers: list[dict[str, str]]   # [{finding, matched_pattern, tier}, ...]
    finding_scores: list[dict[str, Any]]  # per-finding breakdown


def score_urgency(
    findings: list[str],
    impression: str = "",
    regions_of_interest: list[dict] | None = None,
) -> UrgencyScore:
    """Score urgency from extracted findings using deterministic keyword rules.

    Args:
        findings: List of finding strings from the vision model.
        impression: The impression/summary text.
        regions_of_interest: ROIs with labels (used for additional keyword signal).

    Returns:
        UrgencyScore with the final level, numeric score, and per-finding breakdown.
    """
    all_texts = list(findings)
    if impression:
        all_texts.append(impression)
    if regions_of_interest:
        all_texts.extend(roi.get("label", "") for roi in regions_of_interest)

    triggers: list[dict[str, str]] = []
    finding_scores: list[dict[str, Any]] = []
    max_score = 0

    for text in all_texts:
        if not text.strip():
            continue

        entry_score = 1  # default: routine
        entry_tier = "routine"
        matched_pattern = None

        # Check urgent first (highest priority)
        for pattern in _URGENT_RE:
            match = pattern.search(text)
            if match and not _is_negated(text, match):
                entry_score = 3
                entry_tier = "urgent"
                matched_pattern = pattern.pattern
                triggers.append({
                    "finding": text,
                    "matched_pattern": pattern.pattern,
                    "tier": "urgent",
                })
                break

        # Check soon (if not already urgent)
        if entry_score < 3:
            for pattern in _SOON_RE:
                match = pattern.search(text)
                if match and not _is_negated(text, match):
                    entry_score = 2
                    entry_tier = "soon"
                    matched_pattern = pattern.pattern
                    triggers.append({
                        "finding": text,
                        "matched_pattern": pattern.pattern,
                        "tier": "soon",
                    })
                    break

        # Check if explicitly normal
        if entry_score <= 1:
            for pattern in _NORMAL_RE:
                if pattern.search(text):
                    entry_score = 0
                    entry_tier = "normal"
                    matched_pattern = pattern.pattern
                    break

        finding_scores.append({
            "text": text,
            "score": entry_score,
            "tier": entry_tier,
            "matched_pattern": matched_pattern,
        })

        max_score = max(max_score, entry_score)

    level = {3: "urgent", 2: "soon"}.get(max_score, "routine")

    return UrgencyScore(
        level=level,
        score=max_score,
        triggers=triggers,
        finding_scores=finding_scores,
    )
