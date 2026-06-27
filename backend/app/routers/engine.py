"""Unified first-pass engine: dispatch to any skill by name.

ingest -> structure -> reason (skill) -> score -> [human sign-off] -> audit
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.skills import REGISTRY
from app.skills.base import SkillInput

router = APIRouter(prefix="/engine", tags=["engine"])


class RunSkillRequest(BaseModel):
    text: str = ""
    image_path: str | None = None
    context: dict = Field(default_factory=dict)


@router.get("/skills")
def list_skills() -> dict:
    return {"skills": sorted(REGISTRY)}


@router.post("/run/{skill_name}")
def run_skill(skill_name: str, payload: RunSkillRequest | None = None) -> dict:
    skill = REGISTRY.get(skill_name)
    if skill is None:
        raise HTTPException(404, f"unknown skill: {skill_name}")
    payload = payload or RunSkillRequest()
    result = skill.run(
        SkillInput(
            text=payload.text,
            image_path=payload.image_path,
            context=payload.context,
        )
    )
    return {"skill": result.skill, "draft": result.draft, "urgency": result.urgency, "signed": result.signed}
