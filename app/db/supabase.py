"""Compatibilidade: o cliente Supabase vive agora em app.infra.supabase.client.

Mantido como reexport para nao quebrar imports existentes. Prefira importar de
``app.infra.supabase.client`` em codigo novo.
"""

from app.infra.supabase.client import get_supabase_client

__all__ = ["get_supabase_client"]
