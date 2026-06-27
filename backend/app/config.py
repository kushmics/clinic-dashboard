"""Central configuration, loaded from environment / .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from the repo root (next to .env.example) OR backend/ — backend wins
# if both exist. Absolute paths so it works regardless of where you run uvicorn.
_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT / ".env", _BACKEND / ".env"),
        extra="ignore",
    )

    app_name: str = "Clinic Dashboard API"
    # AI model layer — OpenAI (sponsor) is the default for vision/text extraction.
    # The model only EXTRACTS; flagging/severity is deterministic (no LLM).
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"   # current-gen vision model; override via env
    # Semantic retrieval layer — Exa attaches verifiable guideline/literature
    # citations to differential next steps.
    exa_api_key: str | None = None
    # Kept so the alternative provider path is not blocked.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    # Where uploaded labs/scans land. Keep PHI out of git.
    upload_dir: str = "./data/uploads"


settings = Settings()
