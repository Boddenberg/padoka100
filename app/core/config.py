from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Padoka 100 API"
    app_env: str = "local"
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    web_production_origin: str = "https://padoka100-web-production.up.railway.app"
    api_key: str = ""

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "padoka-midia"
    max_upload_bytes: int = 25 * 1024 * 1024

    openai_api_key: str = ""
    openai_chat_model: str = ""
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
    def cors_origins_resolved(self) -> list[str]:
        if not self.cors_origins:
            return ["*"]
        return list(dict.fromkeys([*self.cors_origins, self.web_production_origin]))

    @property
    def supabase_api_key(self) -> str:
        return self.supabase_service_role_key or self.supabase_key

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_api_key)

    @property
    def openai_text_model_resolved(self) -> str:
        return self.openai_text_model or self.openai_chat_model

    @property
    def openai_text_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_text_model_resolved)

    @property
    def openai_audio_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_transcription_model)

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
