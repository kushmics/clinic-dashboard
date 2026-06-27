"""Central configuration, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Clinic Dashboard API"
    # API-first image/text reasoning.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    # Legacy knobs kept so other tracks are not blocked while migrating.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    # Where uploaded labs/scans land. Keep PHI out of git.
    upload_dir: str = "./data/uploads"


settings = Settings()
