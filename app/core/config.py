from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Padoka 100 API"
    app_env: str = "local"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=list)

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "padoka-media"

    openai_api_key: str = ""
    openai_text_model: str = ""
    openai_transcription_model: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return []

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def openai_text_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_text_model)

    @property
    def openai_audio_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_transcription_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()

