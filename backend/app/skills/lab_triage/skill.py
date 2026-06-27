"""Track A — Lab-results triage.

Two stages with a checkable artifact between them (auditability):
  1. extraction  — messy input -> normalized measurements (deterministic, or
                   OpenAI vision/text for photos/scans). LLM only reads.
  2. triage      — deterministic flag + never-miss sort + facts-only summary
                   against cited SGH/NUH tables. No LLM, no severity judgement.

Output is a DRAFT for a clinician to review and sign. `signed` is never set here.
"""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult

from .extraction import extract
from .reference import sources
from .triage import strip_internal, triage


class LabTriageSkill(Skill):
    name = "lab_triage"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        prefer_openai = bool(data.context.get("prefer_openai"))
        extraction = extract(
            text=data.text or "",
            image_path=data.image_path,
            prefer_openai=prefer_openai,
        )
        draft = triage(extraction, context=data.context)
        draft = strip_internal(draft)
        # Provenance for the audit trail / UI footer.
        draft["meta"] = {
            "extraction_method": extraction.method,
            "extraction_notes": extraction.notes,
            "sources": sources(),
        }
        return SkillResult(skill=self.name, draft=draft, urgency=draft["urgency"])
