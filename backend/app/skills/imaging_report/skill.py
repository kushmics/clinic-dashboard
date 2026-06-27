"""Track B — Imaging prelim report: scan -> structured report + ROI."""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult


class ImagingReportSkill(Skill):
    name = "imaging_report"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        # TODO(Track B): preprocess via services.image_processing, then draft a
        # structured prelim report + regions of interest.
        # NOTE: general-purpose vision for demo only — swap a cleared model in prod.
        return SkillResult(
            skill=self.name,
            draft={"findings": [], "regions_of_interest": [], "impression": "", "urgency": None},
        )
