"""Pluggable first-pass skills. One per feature, all implement skills.base.Skill."""
from app.skills.differential_dx.skill import DifferentialDxSkill
from app.skills.imaging_report.skill import ImagingReportSkill
from app.skills.lab_triage.skill import LabTriageSkill
from app.skills.referral_letter.skill import ReferralLetterSkill

# Registry the engine dispatches against.
REGISTRY = {
    s.name: s
    for s in (LabTriageSkill(), ImagingReportSkill(), DifferentialDxSkill(), ReferralLetterSkill())
}
