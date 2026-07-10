from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError


@lru_cache
def get_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise MissingConfigurationError("OpenAI", ["OPENAI_API_KEY"])
    return OpenAI(api_key=settings.openai_api_key)
