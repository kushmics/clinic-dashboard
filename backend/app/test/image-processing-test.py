# test_imaging.py — run from backend/ with venv active
import os
os.environ["ANTHROPIC_API_KEY"] = "your-key-here"

from app.skills.imaging_report.skill import ImagingReportSkill
from app.skills.base import SkillInput

skill = ImagingReportSkill()
result = skill.run(SkillInput(
    image_path="path/to/any_chest_xray.png",
    context={"modality_hint": "xray"}
))
print(result)