from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError
from supabase import Client, create_client


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_api_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY ou SUPABASE_KEY")
    if missing:
        raise MissingConfigurationError("Supabase", missing)
    return create_client(settings.supabase_url, settings.supabase_api_key)
