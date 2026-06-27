"""Track C — Differential diagnosis: ranked differentials + cited next steps."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List

import httpx

from app.config import settings
from app.skills.base import Skill, SkillInput, SkillResult

from .kb import KB, evaluate_red_flags, flag_observations, parse_labs_from_text, score_conditions


class DifferentialDxSkill(Skill):
    name = "differential_dx"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        text = data.text or ""
        kb = KB.load()

        # 1) Prefer Track A's structured lab-triage draft; fall back to free text.
        lab_triage = data.context.get("lab_triage") or data.context.get("lab_triage_draft")
        if lab_triage:
            raw_obs, ctx = observations_from_lab_triage(lab_triage, kb)
            ctx = {**ctx, **{k: v for k, v in data.context.items() if k in {"sex", "age"}}}
        else:
            raw_obs = parse_labs_from_text(text, kb)
            ctx = {**infer_context(text), **{k: v for k, v in data.context.items() if k in {"sex", "age"}}}
        obs = flag_observations(raw_obs, kb, ctx)

        # 2) Score candidate conditions.
        scored = score_conditions(obs, kb)

        # 3) Evaluate red flags (lab thresholds) + simple text high-risk phrases.
        red_hits = evaluate_red_flags(obs, kb)
        lower_text = text.lower()
        for rule in kb.red_flags:
            r = rule.get("rule", {})
            phrases = r.get("text_contains")
            if phrases and any(p.lower() in lower_text for p in phrases):
                red_hits.append(rule)

        differentials = []
        for item in scored[:5]:
            steps = []
            for step in item.get("next_steps", []):
                citation = None
                if not data.context.get("disable_evidence_search"):
                    citation = search_evidence_for_step(item["condition"], step, obs)
                steps.append({"action": step, "citation": citation})
            differentials.append({
                "condition": item["condition"],
                "likelihood": to_likelihood(item["score"]),
                "supporting": pretty_support(item.get("matched", []), kb),
                "next_steps": steps,
            })

        urgency = "urgent" if red_hits else None
        draft = {
            "differentials": differentials,
            "red_flags": [h.get("message") or h.get("name") for h in red_hits],
            "observations": obs,
        }
        return SkillResult(skill=self.name, draft=draft, urgency=urgency)


def infer_context(text: str) -> dict:
    t = (text or "").lower()
    sex = None
    if " female " in f" {t} " or t.startswith("female") or " f, " in f" {t} ":
        sex = "female"
    if " male " in f" {t} " or t.startswith("male") or " m, " in f" {t} ":
        sex = "male"
    # Crude age extractor: first 1-3 digit number before yo/y-o/years, or after
    # a leading sex marker (e.g. "Female 28, fatigue").
    m = re.search(r"\b(\d{1,3})\s*(?:yo|y/o|years?|yrs?)\b|\b(?:male|female|m|f)\s+(\d{1,3})\b", t)
    age = None
    if m:
        digs = [g for g in m.groups() or [] if g and g.isdigit()]
        age = float(digs[0]) if digs else None
    ctx = {}
    if sex:
        ctx["sex"] = sex
    if age:
        ctx["age"] = age
    return ctx


def observations_from_lab_triage(draft: dict[str, Any], kb: KB) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Reuse Track A's structured draft instead of reparsing the original text."""
    if "draft" in draft and isinstance(draft["draft"], dict):
        draft = draft["draft"]
    raw: dict[str, dict[str, Any]] = {}
    for bucket in ("abnormals", "normals"):
        for item in draft.get(bucket, []) or []:
            code = _lab_code(item.get("analyte", ""), kb)
            if not code:
                continue
            raw[code] = {"value": item.get("value"), "units": item.get("unit")}
    ctx = draft.get("context_used") or {}
    return raw, {k: v for k, v in ctx.items() if k in {"sex", "age"} and v is not None}


def search_evidence_for_step(
    condition: str,
    step: str,
    observations: dict[str, dict[str, Any]],
    kb: KB | None = None,
) -> dict[str, str | None] | None:
    """Fetch one verifiable Exa citation for a proposed next step.

    Fails soft when EXA_API_KEY is absent so local demos/tests still run; the UI
    can show the action with `citation: null` rather than fabricating a source.
    """
    if not settings.exa_api_key:
        return None
    kb = kb or KB.load()
    query = _evidence_query(condition, step, observations, kb)
    payload = {
        "query": query,
        "type": "auto",
        "numResults": 1,
        "contents": {"highlights": {"query": step, "maxCharacters": 400}},
    }
    try:
        resp = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": settings.exa_api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except Exception:
        return None
    if not results:
        return None
    top = results[0]
    highlights = top.get("highlights") or []
    return {
        "title": top.get("title") or top.get("url") or "Exa result",
        "url": top.get("url"),
        "snippet": highlights[0] if highlights else (top.get("summary") or top.get("text") or "")[:400],
        "query": query,
        "source": "exa",
    }


def _lab_code(label: str, kb: KB) -> str | None:
    normalized = re.sub(r"\s+", " ", (label or "").strip().lower())
    if normalized in kb.alias_to_code:
        return kb.alias_to_code[normalized]
    compact = re.sub(r"[^a-z0-9+]+", "", normalized)
    for alias, code in kb.alias_to_code.items():
        if re.sub(r"[^a-z0-9+]+", "", alias) == compact:
            return code
    return None


def _evidence_query(condition: str, step: str, observations: dict[str, dict[str, Any]], kb: KB) -> str:
    abnormal_bits = []
    for code, obs in observations.items():
        if obs.get("flag") == "normal":
            continue
        lab = kb.labs.get(code)
        name = lab.name if lab else code
        val = obs.get("value")
        units = obs.get("units") or (lab.unit if lab else "")
        abnormal_bits.append(f"{name} {val} {units}".strip())
    clinical_context = ", ".join(abnormal_bits[:3])
    if clinical_context:
        return f"current guideline {condition} workup {step} {clinical_context}"
    return f"current guideline {condition} workup {step}"


def to_likelihood(score: float) -> str:
    if score >= 7:
        return "high"
    if score >= 4:
        return "moderate"
    return "low"


def pretty_support(matched: List[str], kb: KB) -> List[str]:
    out: List[str] = []
    for key in matched:
        if "." in key:
            lab_code, feat = key.split(".", 1)
            lab = kb.labs.get(lab_code)
            label = lab.name if lab else lab_code
            if feat.startswith("fold_gt_"):
                out.append(f"{label} > ULN by threshold")
            else:
                out.append(f"{label} {feat}")
        else:
            out.append(key)
    return out
