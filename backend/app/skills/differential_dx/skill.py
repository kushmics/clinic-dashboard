"""Track C — Differential diagnosis: ranked differentials + next steps."""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult


class DifferentialDxSkill(Skill):
    name = "differential_dx"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        # TODO(Track C): pull recognized terms from services.medical_nlp + the
        # curated knowledge base (RAG-lite), then draft ranked differentials.
        return SkillResult(skill=self.name, draft={"differentials": [], "red_flags": []})
