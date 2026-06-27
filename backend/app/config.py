"""Central configuration, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Clinic Dashboard API"
    # AI approach is still TBD — both knobs are here so neither path is blocked.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    # Where uploaded labs/scans land. Keep PHI out of git.
    upload_dir: str = "./data/uploads"


settings = Settings()
