"""Unified first-pass engine: dispatch to any skill by name.

ingest -> structure -> reason (skill) -> score -> [human sign-off] -> audit
"""
from fastapi import APIRouter, HTTPException

from app.skills import REGISTRY
from app.skills.base import SkillInput

router = APIRouter(prefix="/engine", tags=["engine"])


@router.get("/skills")
def list_skills() -> dict:
    return {"skills": sorted(REGISTRY)}


@router.post("/run/{skill_name}")
def run_skill(skill_name: str, text: str = "", image_path: str | None = None) -> dict:
    skill = REGISTRY.get(skill_name)
    if skill is None:
        raise HTTPException(404, f"unknown skill: {skill_name}")
    result = skill.run(SkillInput(text=text, image_path=image_path))
    return {"skill": result.skill, "draft": result.draft, "urgency": result.urgency, "signed": result.signed}
