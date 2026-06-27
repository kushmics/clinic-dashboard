"""Track D — One-click referral letter draft."""
from pathlib import Path

from app.skills.base import Skill, SkillInput, SkillResult


class ReferralLetterSkill(Skill):
    name = "referral_letter"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        patient = data.context.get("patient", {})
        lab = data.context.get("lab_triage", {})
        imaging = data.context.get("imaging_report", {})
        dx = data.context.get("differential_dx", {})

        patient_name = patient.get("name", "the patient")
        specialty = data.context.get("recipient_specialty", "Internal Medicine")
        reason = data.context.get("reason_for_referral") or lab.get("summary") or "Further specialist assessment"

        relevant_findings = []
        for item in lab.get("abnormals", []):
            name = item.get("name", "Finding")
            value = item.get("value", "")
            unit = item.get("unit", "")
            flag = item.get("flag", "abnormal")
            relevant_findings.append(f"{name}: {value} {unit} ({flag})".strip())
        relevant_findings.extend(imaging.get("findings", []))
        relevant_findings.extend(dx.get("red_flags", []))

        clinical_summary = data.text.strip() or patient.get("summary", "")
        if not clinical_summary:
            clinical_summary = "Clinical summary pending clinician review."

        findings_markdown = "\n".join(f"- {finding}" for finding in relevant_findings[:6])
        if not findings_markdown:
            findings_markdown = "- No structured findings attached yet."

        letter = f"""Dear {specialty} Team,

Re: {patient_name}

I am referring {patient_name} for {reason.lower()}.

Clinical summary:
{clinical_summary}

Relevant findings:
{findings_markdown}

Provisional considerations:
{_format_differentials(dx)}

Please assess and advise on further management.

Regards,
Clinician reviewer"""

        return SkillResult(
            skill=self.name,
            draft={
                "recipient_specialty": specialty,
                "reason_for_referral": reason,
                "clinical_summary": clinical_summary,
                "relevant_findings": relevant_findings,
                "letter_markdown": letter,
            },
        )


def _format_differentials(draft: dict) -> str:
    differentials = draft.get("differentials", [])
    if not differentials:
        return "- Pending differential diagnosis draft."
    lines = []
    for item in differentials[:4]:
        if isinstance(item, str):
            lines.append(f"- {item}")
        else:
            label = item.get("condition") or item.get("name") or "Consideration"
            rationale = item.get("rationale") or item.get("reason") or ""
            lines.append(f"- {label}: {rationale}" if rationale else f"- {label}")
    return "\n".join(lines)
