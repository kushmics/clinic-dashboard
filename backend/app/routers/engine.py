"""Unified first-pass engine: dispatch to any skill by name.

ingest -> structure -> reason (skill) -> score -> [human sign-off] -> audit
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.skills import REGISTRY
from app.skills.base import SkillInput

router = APIRouter(prefix="/engine", tags=["engine"])


class RunRequest(BaseModel):
    """Generic skill input. `context` carries patient sex/age, prior labs, and
    upstream skills' drafts (e.g. referral_letter consumes the others)."""
    text: str = ""
    image_path: str | None = None
    context: dict = {}


@router.get("/skills")
def list_skills() -> dict:
    return {"skills": sorted(REGISTRY)}


@router.post("/run/{skill_name}")
def run_skill(skill_name: str, req: RunRequest | None = None) -> dict:
    skill = REGISTRY.get(skill_name)
    if skill is None:
        raise HTTPException(404, f"unknown skill: {skill_name}")
    req = req or RunRequest()
    result = skill.run(SkillInput(text=req.text, image_path=req.image_path,
                                  context=req.context))
    return {"skill": result.skill, "draft": result.draft,
            "urgency": result.urgency, "signed": result.signed}
