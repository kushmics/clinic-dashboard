"""Track D — One-click referral letter draft."""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult


class ReferralLetterSkill(Skill):
    name = "referral_letter"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        # TODO(Track D): compose a referral letter from the case + prior skill
        # outputs (triage/imaging/differentials) passed in via data.context.
        return SkillResult(
            skill=self.name,
            draft={"recipient_specialty": "", "reason_for_referral": "", "letter_markdown": ""},
        )
