"""Differential Dx checks for structured lab input + cited next steps."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skills.base import SkillInput
from app.skills.differential_dx import skill as dx_skill
from app.skills.differential_dx.skill import DifferentialDxSkill


def test_uses_lab_triage_context_instead_of_reparsing_text():
    lab_triage = {
        "abnormals": [
            {
                "analyte": "Potassium",
                "value": 6.7,
                "unit": "mmol/L",
                "flag": "critical",
                "direction": "high",
            }
        ],
        "normals": [],
        "unassessed": [],
        "context_used": {"sex": "female", "age": 40},
    }

    out = DifferentialDxSkill().run(
        SkillInput(text="", context={"lab_triage": lab_triage, "disable_evidence_search": True})
    )

    assert out.urgency == "urgent"
    assert out.draft["observations"]["k"]["value"] == 6.7
    assert out.draft["red_flags"] == ["Potassium at or above 6.5 mmol/L"]


def test_next_steps_are_evidence_backed_with_exa_citations(monkeypatch):
    calls = []

    def fake_search(condition, step, observations):
        calls.append((condition, step, observations))
        return {
            "title": f"Guideline for {step}",
            "url": "https://example.org/guideline",
            "snippet": "Relevant guideline excerpt",
            "query": f"{condition} {step}",
            "source": "exa",
        }

    monkeypatch.setattr(dx_skill, "search_evidence_for_step", fake_search)

    out = DifferentialDxSkill().run(
        SkillInput(text="Female 28, fatigue. Hb 9.9 g/dL, MCV 70 fL, Ferritin 7 ng/mL.")
    )

    first = out.draft["differentials"][0]
    assert first["condition"] == "Iron deficiency anemia"
    assert first["next_steps"]
    assert all(isinstance(step, dict) for step in first["next_steps"])
    assert all(step["action"] and step["citation"]["url"] for step in first["next_steps"])
    assert calls[0][0] == "Iron deficiency anemia"
    assert "hb" in calls[0][2]
