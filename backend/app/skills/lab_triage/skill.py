"""Track A — Lab-results triage: flag abnormals, rank urgency, summarize."""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult


class LabTriageSkill(Skill):
    name = "lab_triage"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        # TODO(Track A): parse analytes + reference ranges, flag, rank urgency.
        # AI APPROACH PENDING — Claude structured extraction or local rules.
        return SkillResult(skill=self.name, draft={"abnormals": [], "urgency": None, "summary": ""})
