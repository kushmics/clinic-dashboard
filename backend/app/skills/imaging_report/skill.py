"""Track B — Imaging prelim report: scan -> structured report + ROI."""
import base64
import json
import mimetypes
from pathlib import Path

from app.config import settings
from app.skills.base import Skill, SkillInput, SkillResult


class ImagingReportSkill(Skill):
    name = "imaging_report"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        if settings.openai_api_key and data.image_path:
            try:
                return SkillResult(skill=self.name, draft=self._run_openai_vision(data))
            except Exception as exc:
                fallback = self._empty_draft()
                fallback["generation_note"] = f"OpenAI vision unavailable; no AI read returned ({exc.__class__.__name__})."
                return SkillResult(skill=self.name, draft=fallback)

        fallback = self._empty_draft()
        if not data.image_path:
            fallback["generation_note"] = "Upload a scan to generate an imaging draft."
        return SkillResult(skill=self.name, draft=fallback)

    def _run_openai_vision(self, data: SkillInput) -> dict:
        from openai import OpenAI

        image_path = Path(data.image_path)
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        image_url = f"data:{mime_type};base64,{encoded}"

        client = OpenAI(api_key=settings.openai_api_key)
        schema = self.load_schema()
        payload = {
            "case_text": data.text,
            "context": data.context,
            "schema": schema,
        }
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.load_prompt()},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Produce a preliminary imaging report for clinician review. "
                                "Return only JSON matching this payload schema and include uncertainty.\n\n"
                                + json.dumps(payload, indent=2)
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                    ],
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        return _normalize_draft(json.loads(content))

    def _empty_draft(self) -> dict:
        return {
            "modality": "",
            "findings": [],
            "regions_of_interest": [],
            "possible_diagnoses": [],
            "limitations": [],
            "impression": "",
            "urgency": "routine",
        }


def _normalize_draft(draft: dict) -> dict:
    def list_of_strings(value):
        if isinstance(value, list):
            return [str(item) for item in value]
        if value:
            return [str(value)]
        return []

    possible_diagnoses = draft.get("possible_diagnoses", [])
    if not isinstance(possible_diagnoses, list):
        possible_diagnoses = []

    return {
        "modality": str(draft.get("modality", "Chest X-ray")),
        "findings": list_of_strings(draft.get("findings", [])),
        "regions_of_interest": draft.get("regions_of_interest", []) if isinstance(draft.get("regions_of_interest", []), list) else [],
        "possible_diagnoses": [
            {
                "condition": str(item.get("condition", "")),
                "rationale": str(item.get("rationale", "")),
                "confidence": str(item.get("confidence", "low")),
            }
            for item in possible_diagnoses
            if isinstance(item, dict)
        ],
        "limitations": list_of_strings(draft.get("limitations", [])),
        "impression": str(draft.get("impression", "")),
        "urgency": draft.get("urgency") if draft.get("urgency") in {"routine", "soon", "urgent"} else "routine",
    }
