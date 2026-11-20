"""Application settings, loaded only from environment variables / .env (US-02).

Nothing secret is ever hard-coded. If a required setting is missing, the app
stops at start-up with a clear message that names the variable, never its value.
"""
from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when the environment is missing or has invalid settings."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required
    database_url: str = Field(description="postgresql+psycopg://user:password@host:5432/db")
    jwt_secret: str = Field(min_length=32, description="Random string of at least 32 characters")

    # Auth
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=480, ge=5, le=1440)

    # Web
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Business rules
    due_window_days: int = Field(default=7, ge=1, le=60)

    # AI (used by Person 3's module; optional here)
    ai_enabled: bool = True
    ai_timeout_seconds: int = Field(default=20, ge=1, le=120)
    ai_max_retries: int = Field(default=1, ge=0, le=3)
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        problems = sorted({str(err["loc"][0]).upper() for err in exc.errors()})
        raise ConfigError(
            "Missing or invalid configuration: "
            + ", ".join(problems)
            + ". Copy .env.example to .env and fill in these values."
        ) from None