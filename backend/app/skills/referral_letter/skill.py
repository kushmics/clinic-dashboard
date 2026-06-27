"""Track D — One-click referral letter draft."""
import json
from pathlib import Path

from app.config import settings
from app.skills.base import Skill, SkillInput, SkillResult


class ReferralLetterSkill(Skill):
    name = "referral_letter"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        if settings.openai_api_key:
            try:
                draft = self._run_openai(data)
                return SkillResult(skill=self.name, draft=draft)
            except Exception as exc:
                # Keep the demo usable if the API key/model/network is not ready.
                fallback = self._compose_template(data)
                fallback["generation_note"] = f"OpenAI generation unavailable; template fallback used ({exc.__class__.__name__})."
                return SkillResult(skill=self.name, draft=fallback)

        return SkillResult(skill=self.name, draft=self._compose_template(data))

    def _run_openai(self, data: SkillInput) -> dict:
        from openai import OpenAI

        schema = self.load_schema()
        prompt = self.load_prompt()
        client = OpenAI(api_key=settings.openai_api_key)
        payload = {
            "case_text": data.text,
            "context": data.context,
            "schema": schema,
        }
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Draft the referral letter from this JSON payload. "
                        "Return only valid JSON matching the schema.\n\n"
                        + json.dumps(payload, indent=2)
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        draft = json.loads(content)
        return _normalize_draft(draft)

    def _compose_template(self, data: SkillInput) -> dict:
        patient = data.context.get("patient", {})
        lab = data.context.get("lab_triage", {})
        imaging = data.context.get("imaging_report", {})
        dx = data.context.get("differential_dx", {})

        patient_name = patient.get("name", "the patient")
        specialty = data.context.get("recipient_specialty", "Internal Medicine")
        reason = data.context.get("reason_for_referral") or lab.get("summary") or "Further specialist assessment"

        relevant_findings = []
        for item in lab.get("abnormals", []):
            name = item.get("analyte") or item.get("name") or "Finding"
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

        return {
            "recipient_specialty": specialty,
            "reason_for_referral": reason,
            "clinical_summary": clinical_summary,
            "relevant_findings": relevant_findings,
            "letter_markdown": letter,
        }


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
            rationale = item.get("rationale") or item.get("reason") or "; ".join(item.get("supporting", [])[:3])
            lines.append(f"- {label}: {rationale}" if rationale else f"- {label}")
    return "\n".join(lines)


def _normalize_draft(draft: dict) -> dict:
    relevant_findings = draft.get("relevant_findings", [])
    if not isinstance(relevant_findings, list):
        relevant_findings = [str(relevant_findings)]

    return {
        "recipient_specialty": str(draft.get("recipient_specialty", "")),
        "reason_for_referral": str(draft.get("reason_for_referral", "")),
        "clinical_summary": str(draft.get("clinical_summary", "")),
        "relevant_findings": [str(item) for item in relevant_findings],
        "letter_markdown": str(draft.get("letter_markdown", "")),
    }
