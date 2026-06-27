"""Synthetic-case checks for the deterministic lab-triage engine.

No network, no API key — exercises extraction (deterministic paths) + triage
against the cited SGH/NUH tables. Run:
    .venv/bin/python tests/test_lab_triage.py
(or with pytest if installed). Synthetic data only — never real PHI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skills.base import SkillInput
from app.skills.lab_triage.skill import LabTriageSkill

SKILL = LabTriageSkill()


def _run(text="", context=None, image_path=None):
    return SKILL.run(SkillInput(text=text, context=context or {}, image_path=image_path)).draft


def _find(items, analyte):
    return next((i for i in items if i["analyte"].lower().startswith(analyte.lower())), None)


def test_critical_potassium_is_urgent_via_sgh():
    d = _run("Potassium 6.5 mmol/L (3.5-5.1) H\nSodium 138 mmol/L (135-145)")
    # 5-level acuity: a critical value is life-threatening -> immediate (L1).
    assert d["urgency"] == "immediate"
    k = _find(d["abnormals"], "potassium")
    assert k and k["flag"] == "critical" and k["direction"] == "high"
    assert k["threshold_source"]["table"] == "SGH" and k["threshold_source"]["threshold"] == 5.7
    # Sodium 138 is inside its printed range -> normal, not flagged.
    assert _find(d["normals"], "sodium")
    print("✓ critical potassium -> immediate, SGH-sourced; normal sodium kept")


def test_printed_range_drives_non_critical_flag():
    d = _run("Haemoglobin 11.2 g/dL 13.0-17.0")  # report prints its own range
    hb = _find(d["abnormals"], "haem")
    assert hb and hb["flag"] == "low" and hb["threshold_source"]["table"] == "report"
    # 5-level acuity: a non-critical abnormal flag maps to urgent (L3).
    assert d["urgency"] == "urgent"
    print("✓ report's printed range used; low Hb -> urgent")


def test_nuh_fallback_and_provisional_when_sex_unknown():
    d = _run("Haemoglobin 11.2 g/dL")  # no printed range, no sex
    hb = _find(d["abnormals"], "haem")
    assert hb["threshold_source"]["table"] == "NUH"
    assert hb["provisional"] is True
    assert any("Sex not supplied" in a for a in d["assumptions"])
    print("✓ NUH fallback when report prints no range; provisional + assumption logged")


def test_sex_context_removes_provisional():
    d = _run("Haemoglobin 11.2 g/dL", context={"sex": "female", "sex_source": "provided",
                                               "age": 40, "age_source": "provided"})
    hb = _find(d["abnormals"], "haem")
    assert hb["provisional"] is False  # 11.2 < 11.5 female low
    assert d["context_used"]["sex"] == "female"
    print("✓ supplied sex/age -> definitive NUH female range, not provisional")


def test_unit_mismatch_goes_unassessed_not_guessed():
    d = _run("Potassium 6.5 mg/dL")  # wrong unit for potassium
    assert not d["abnormals"]
    u = _find(d["unassessed"], "potassium")
    assert u and "unit mismatch" in u["reason"]
    print("✓ unit mismatch -> unassessed (no magnitude guessed)")


def test_unknown_analyte_surfaced_not_dropped():
    d = _run("Widgetase 5.0 U/L")
    u = _find(d["unassessed"], "widgetase")
    assert u and "no reference range" in u["reason"]
    print("✓ unknown analyte surfaced in unassessed, never dropped")


def test_age_sex_extracted_from_report_text():
    d = _run("Age: 54  Sex: F\nHaemoglobin 11.0 g/dL")
    assert d["context_used"]["sex"] == "female" and d["context_used"]["sex_source"] == "report"
    assert d["context_used"]["age"] == 54
    print("✓ age/sex auto-extracted from report header")


def test_json_input_path_and_critical_low():
    d = _run('{"patient":{"sex":"female","age":40},'
             '"measurements":[{"analyte":"Potassium","value":2.1,"unit":"mmol/L"}]}')
    k = _find(d["abnormals"], "potassium")
    assert k["flag"] == "critical" and k["direction"] == "low"
    assert d["meta"]["extraction_method"] == "json"
    print("✓ JSON input parsed; potassium 2.1 -> critical low")


def test_delta_against_prior():
    d = _run("Potassium 6.5 mmol/L (3.5-5.1)",
             context={"priors": {"potassium": 4.0}})
    k = _find(d["abnormals"], "potassium")
    assert k["delta"] and k["delta"]["prior"] == 4.0 and k["delta"]["change"] == 2.5
    print("✓ delta vs prior computed when a prior is supplied")


def test_sort_critical_first():
    d = _run("Haemoglobin 11.2 g/dL 13.0-17.0\nPotassium 6.5 mmol/L (3.5-5.1)")
    assert d["abnormals"][0]["flag"] == "critical"  # potassium ahead of low Hb
    print("✓ never-miss sort puts critical first")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} lab_triage checks passed.")
