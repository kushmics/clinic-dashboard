"""Track C — Differential diagnosis: ranked differentials + next steps."""
from __future__ import annotations
from pathlib import Path
from typing import List

from app.skills.base import Skill, SkillInput, SkillResult
from .kb import KB, parse_labs_from_text, flag_observations, evaluate_red_flags, score_conditions


def infer_context(text: str) -> dict:
        import re
        t = (text or '').lower()
        sex = None
        if ' female ' in f' {t} ' or t.startswith('female') or ' f, ' in f' {t} ':
            sex = 'f'
        if ' male ' in f' {t} ' or t.startswith('male') or ' m, ' in f' {t} ':
            sex = 'm'
        # crude age extractor: first 1-3 digit number before 'yo' or followed by 'year'
        m = re.search(r'((d{1,3})s*(yo|y/o|years?|yrs?))|((d{1,3})s*[,])', t)
        age = None
        if m:
            digs = [g for g in m.groups() or [] if g and g.isdigit()]
            age = float(digs[0]) if digs else None
        ctx = {}
        if sex: ctx['sex'] = sex
        if age: ctx['age'] = age
        return ctx
        t = (text or '').lower()
        sex = None
        if ' female ' in f' {t} ' or t.startswith('female') or ' f, ' in f' {t} ':
            sex = 'f'
        if ' male ' in f' {t} ' or t.startswith('male') or ' m, ' in f' {t} ':
            sex = 'm'
        return { 'sex': sex } if sex else {}

class DifferentialDxSkill(Skill):
    name = "differential_dx"
    dir = Path(__file__).parent

    def run(self, data: SkillInput) -> SkillResult:
        text = data.text or ""
        kb = KB.load()

        # 1) Parse labs from free text and flag
        raw_obs = parse_labs_from_text(text, kb)
        ctx = infer_context(text)
        obs = flag_observations(raw_obs, kb, ctx)

        # 2) Score candidate conditions
        scored = score_conditions(obs, kb)

        # 3) Evaluate red flags (lab thresholds) + simple text high-risk phrases
        red_hits = evaluate_red_flags(obs, kb)
        lower_text = text.lower()
        for rule in kb.red_flags:
            r = rule.get("rule", {})
            phrases = r.get("text_contains")
            if phrases and any(p.lower() in lower_text for p in phrases):
                red_hits.append(rule)

        def to_likelihood(score: float) -> str:
            if score >= 7:
                return "high"
            if score >= 4:
                return "moderate"
            return "low"

        def pretty_support(matched: List[str]) -> List[str]:
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

        differentials = []
        for item in scored[:5]:
            differentials.append({
                "condition": item["condition"],
                "likelihood": to_likelihood(item["score"]),
                "supporting": pretty_support(item.get("matched", [])),
                "next_steps": item.get("next_steps", []),
            })

        urgency = None
        if red_hits:
            urgency = "urgent"

        draft = {
            "differentials": differentials,
            "red_flags": [h.get("message") or h.get("name") for h in red_hits],
            "observations": obs,
        }

        return SkillResult(skill=self.name, draft=draft, urgency=urgency)
