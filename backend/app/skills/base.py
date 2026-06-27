"""Shared contract every first-pass skill implements.

The unified engine runs one pipeline:
    ingest -> structure -> reason (a Skill) -> score -> human sign-off -> audit

Each of the 4 features is a Skill: a system prompt (prompt.md), an output
JSON schema (schema.json), and a run() that returns a DRAFT for clinician
review. Nothing is ever auto-signed — `signed` starts False, always.

ALL FOUR TRACKS BUILD AGAINST THIS INTERFACE. Agree changes here together.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillInput:
    text: str = ""                       # extracted report / case-note text
    image_path: str | None = None        # path to a scan, if any
    context: dict = field(default_factory=dict)  # patient context, prior labs, retrieval


@dataclass
class SkillResult:
    skill: str
    draft: dict                          # must validate against the skill's schema.json
    urgency: str | None = None           # "routine" | "soon" | "urgent" | None
    signed: bool = False                 # clinician sets True at sign-off; never auto


class Skill:
    """Subclass per feature. Set `name` and `dir = Path(__file__).parent`."""

    name: str = "base"
    dir: Path = Path(__file__).parent

    def load_prompt(self) -> str:
        return (self.dir / "prompt.md").read_text()

    def load_schema(self) -> dict:
        return json.loads((self.dir / "schema.json").read_text())

    def run(self, data: SkillInput) -> SkillResult:
        """Produce a draft for clinician review. AI APPROACH PENDING."""
        raise NotImplementedError
