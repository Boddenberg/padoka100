from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings
from app.core.errors import MissingConfigurationError


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise MissingConfigurationError("Supabase", missing)
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

