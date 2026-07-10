"""Mapeamento puro do usuario do Supabase Auth para o perfil local."""

from app.infra.supabase.payload import to_db_payload
from app.modules.auth.seguranca import normalizar_email


def montar_dados_usuario_supabase(usuario_supabase: dict, *, primeiro_usuario: bool) -> dict:
    metadata = usuario_supabase.get("user_metadata") or {}
    nome = (
        metadata.get("name")
        or metadata.get("full_name")
        or metadata.get("display_name")
        or usuario_supabase.get("email")
    )
    return to_db_payload(
        {
            "supabase_auth_id": str(usuario_supabase.get("id") or "").strip(),
            "email": normalizar_email(str(usuario_supabase.get("email") or "")),
            "nome": str(nome).strip() if nome else None,
            "foto_url": metadata.get("avatar_url") or metadata.get("picture"),
            "telefone": metadata.get("phone") or usuario_supabase.get("phone"),
            "papel": "dono" if primeiro_usuario else "usuario",
            "plano": "basico",
            "situacao": "ativo",
        }
    )
