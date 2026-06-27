"""Track B — Imaging prelim report: scan -> structured report + annotated ROIs.

Pipeline:
    1. image_processing.prepare_image()  — convert upload to normalised PNG
    2. OpenAI vision model (gpt-4o-mini) — draft findings + bbox ROIs
    3. image_processing.annotate_image() — draw ROIs onto PNG for frontend
    4. Return SkillResult with draft + annotated_image_path injected into draft

NOTE: general-purpose vision for demo only — swap a cleared model in prod.
"""
from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from openai import OpenAI

from app import acuity
from app.config import settings
from app.skills.base import Skill, SkillInput, SkillResult
from app.services.image_processing import prepare_image, annotate_image


class ImagingReportSkill(Skill):
    name = "imaging_report"
    dir = Path(__file__).parent

    def __init__(self, model_override: str | None = None) -> None:
        self._client: OpenAI | None = None
        self.model_override = model_override

    @property
    def model(self) -> str:
        return self.model_override or settings.openai_vision_model

    @property
    def client(self) -> OpenAI:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def run(self, data: SkillInput) -> SkillResult:
        """
        Args:
            data.image_path  — raw upload path (PNG/JPG/DICOM/.nii.gz)
            data.text        — any OCR text already extracted upstream
            data.context     — patient context dict (age, history, prior labs...)
                               may carry "modality_hint": "xray"|"ct"|"mri"

        Returns:
            SkillResult whose draft matches schema.json, with two extra keys
            injected into draft for the frontend panel:
                draft["annotated_image_path"] — path to annotated PNG (or None)
                draft["prepared_image_path"]  — path to normalised PNG
        """

        # ── Step 1: preprocess ──────────────────────────────────────────
        prepared_path: str | None = None
        modality_label: str = "Unknown"
        prep_extra: dict = {}

        if data.image_path:
            modality_hint = data.context.get("modality_hint") if data.context else None
            out_dir = Path(data.context.get("output_dir", "")) if data.context and data.context.get("output_dir") else None
            if out_dir is None:
                out_dir = Path(tempfile.mkdtemp(prefix="imaging_"))
            prep = prepare_image(
                file_path=data.image_path,
                modality_hint=modality_hint,
                output_dir=out_dir,
            )
            prepared_path = prep["png_path"]
            modality_label = _friendly_modality(prep["modality"])
            prep_extra = prep.get("extra", {})

        # ── Step 2: build message ───────────────────────────────────────
        user_content: list[dict] = []

        if prepared_path:
            img_bytes = Path(prepared_path).read_bytes()
            b64 = base64.standard_b64encode(img_bytes).decode()
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                    "detail": "high",
                },
            })

        user_parts: list[str] = []

        if modality_label != "Unknown":
            user_parts.append(f"Modality: {modality_label}")

        if prep_extra:
            if "selected_slice" in prep_extra and "n_slices" in prep_extra:
                user_parts.append(
                    f"Displayed slice: {prep_extra['selected_slice']} "
                    f"of {prep_extra['n_slices']} total."
                )
            if "window" in prep_extra:
                user_parts.append(f"CT window preset: {prep_extra['window']}.")
            if "sequence" in prep_extra and prep_extra["sequence"] != "unknown":
                user_parts.append(f"MRI sequence: {prep_extra['sequence']}.")

        if data.text and data.text.strip():
            user_parts.append(f"\nExtracted report text:\n{data.text.strip()}")

        if data.context:
            ctx = {k: v for k, v in data.context.items()
                   if k not in ("modality_hint", "output_dir")}
            if ctx:
                user_parts.append(f"\nPatient context:\n{json.dumps(ctx, indent=2)}")

        user_text = "\n".join(user_parts) if user_parts else "No additional context."
        user_content.append({"type": "text", "text": user_text})

        # ── Step 3: call vision model ───────────────────────────────────
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self.load_prompt()},
                    {"role": "user",   "content": user_content},
                ],
            )
        except Exception as exc:
            return _fallback_result(self.name, modality_label, prepared_path, "_api_error", str(exc))

        raw = (response.choices[0].message.content or "").strip()

        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        try:
            draft: dict = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _fallback_result(self.name, modality_label, prepared_path, "_json_error", str(exc), raw)

        # ── Step 4: guarantee required schema fields ────────────────────
        draft.setdefault("modality", modality_label)
        draft.setdefault("findings", [])
        draft.setdefault("regions_of_interest", [])
        draft.setdefault("possible_diagnoses", [])
        draft.setdefault("limitations", [])
        draft.setdefault("impression", "")
        draft.setdefault("urgency", "routine")

        # The vision model speaks routine/soon/urgent; normalise onto the
        # shared 5-level acuity scale.
        urgency = acuity.from_legacy(draft.get("urgency"))
        draft["urgency"] = urgency

        # ── Step 5: annotate image with ROIs ────────────────────────────
        annotated_path: str | None = None
        rois = draft.get("regions_of_interest", [])

        if prepared_path and rois:
            try:
                annotated_path = annotate_image(
                    png_path=prepared_path,
                    regions_of_interest=rois,
                    output_dir=Path(prepared_path).parent,
                )
            except Exception as exc:
                draft["_annotation_warning"] = str(exc)

        draft["prepared_image_path"] = prepared_path
        draft["annotated_image_path"] = annotated_path

        return SkillResult(
            skill=self.name,
            draft=draft,
            urgency=urgency,
            signed=False,
        )


def _friendly_modality(raw: str) -> str:
    return {
        "xray":  "Chest X-Ray",
        "ct":    "CT Scan",
        "mri":   "MRI",
        "dicom": "DICOM",
    }.get(raw.lower(), raw.capitalize())


def _fallback_result(
    skill_name: str,
    modality_label: str,
    prepared_path: str | None,
    error_key: str,
    error_message: str,
    raw_response: str | None = None,
) -> SkillResult:
    draft = {
        "modality": modality_label,
        "findings": [],
        "regions_of_interest": [],
        "possible_diagnoses": [],
        "limitations": [],
        "impression": "AI analysis unavailable. Please review the image manually.",
        "urgency": "non-urgent",
        "prepared_image_path": prepared_path,
        "annotated_image_path": None,
        error_key: error_message,
    }
    if raw_response:
        draft["_raw_response"] = raw_response[:2000]
    return SkillResult(skill=skill_name, draft=draft, urgency="routine", signed=False)
