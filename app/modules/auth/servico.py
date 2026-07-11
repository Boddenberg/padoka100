from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import coluna_ausente, tabela_ausente
from app.modules.auth.adapters import supabase_auth
from app.modules.auth.domain.capacidades import capacidades_do_usuario
from app.modules.auth.domain.usuario_supabase import montar_dados_usuario_supabase
from app.modules.auth.esquemas import (
    RequisicaoAtualizarPapel,
    RequisicaoAtualizarPerfil,
    RequisicaoAtualizarPlano,
    RequisicaoLogin,
    RequisicaoRegistrarUsuario,
    RequisicaoTrocarSenha,
)
from app.modules.auth.seguranca import (
    gerar_hash_senha,
    gerar_hash_token,
    gerar_token_acesso,
    normalizar_email,
    verificar_senha,
)
from app.modules.midia import servico as servico_de_midia
from app.shared.db import first_or_none, to_db_payload

HORAS_EXPIRACAO_SESSAO = 24 * 14
PAPEIS_ORDENADOS = {"usuario": 1, "administrador": 2, "dono": 3}
USUARIO_SEM_TOKEN_ID = "00000000-0000-0000-0000-000000000000"


def registrar_usuario(requisicao: RequisicaoRegistrarUsuario) -> dict:
    client = get_supabase_client()
    email = normalizar_email(str(requisicao.email))
    if _buscar_usuario_por_email(client, email):
        raise ConflictError("Ja existe usuario cadastrado com esse e-mail.", {"email": email})

    primeiro_usuario = _contar_usuarios(client) == 0
    usuario = (
        client.table("usuarios")
        .insert(
            to_db_payload(
                {
                    "email": email,
                    "senha_hash": gerar_hash_senha(requisicao.senha),
                    "nome": requisicao.nome,
                    "foto_url": requisicao.foto_url,
                    "data_nascimento": requisicao.data_nascimento,
                    "telefone": requisicao.telefone,
                    "papel": "dono" if primeiro_usuario else "usuario",
                    "plano": "basico",
                    "situacao": "ativo",
                }
            )
        )
        .execute()
        .data[0]
    )
    return _usuario_publico(usuario)


def login(requisicao: RequisicaoLogin) -> dict:
    client = get_supabase_client()
    email = normalizar_email(str(requisicao.email))
    usuario = _buscar_usuario_por_email(client, email)
    if not usuario or not verificar_senha(requisicao.senha, usuario["senha_hash"]):
        raise AppError(
            status_code=401,
            code="invalid_credentials",
            message="E-mail ou senha invalidos.",
            details={},
        )
    if usuario["situacao"] != "ativo":
        raise AppError(
            status_code=403,
            code="inactive_user",
            message="Usuario inativo.",
            details={"usuario_id": usuario["id"]},
        )

    token = gerar_token_acesso()
    expira_em = datetime.now(UTC) + timedelta(hours=HORAS_EXPIRACAO_SESSAO)
    client.table("sessoes_usuario").insert(
        to_db_payload(
            {
                "usuario_id": usuario["id"],
                "token_hash": gerar_hash_token(token),
                "expira_em": expira_em,
            }
        )
    ).execute()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expira_em": expira_em,
        "usuario": _usuario_publico(usuario),
    }


def buscar_usuario_por_token(token: str) -> tuple[dict, dict]:
    client = get_supabase_client()
    sessao = first_or_none(
        client.table("sessoes_usuario")
        .select("*")
        .eq("token_hash", gerar_hash_token(token))
        .is_("revogado_em", "null")
        .limit(1)
        .execute()
        .data
    )
    if not sessao:
        usuario = buscar_usuario_por_token_supabase(token)
        return usuario, {"id": None, "provedor": "supabase"}
    if datetime.fromisoformat(sessao["expira_em"].replace("Z", "+00:00")) < datetime.now(UTC):
        raise AppError(
            status_code=401,
            code="expired_token",
            message="Sessao expirada.",
            details={},
        )

    usuario = buscar_linha_usuario(sessao["usuario_id"])
    if usuario["situacao"] != "ativo":
        raise AppError(
            status_code=403,
            code="inactive_user",
            message="Usuario inativo.",
            details={"usuario_id": usuario["id"]},
        )
    client.table("sessoes_usuario").update(
        to_db_payload({"ultimo_uso_em": datetime.now(UTC)})
    ).eq("id", sessao["id"]).execute()
    return _usuario_publico(usuario), sessao


def buscar_usuario_por_token_supabase(token: str) -> dict:
    usuario_supabase = supabase_auth.buscar_usuario_do_token(token)
    return sincronizar_usuario_supabase(usuario_supabase)


def sincronizar_usuario_supabase(usuario_supabase: dict) -> dict:
    client = get_supabase_client()
    auth_id = str(usuario_supabase.get("id") or "").strip()
    email = normalizar_email(str(usuario_supabase.get("email") or ""))
    if not auth_id or not email:
        raise AppError(
            status_code=401,
            code="invalid_token",
            message="Sessao invalida ou expirada.",
            details={},
        )

    usuario = _buscar_usuario_por_supabase_auth_id(client, auth_id)
    if usuario:
        return _usuario_publico(
            _atualizar_usuario_supabase_existente(client, usuario, usuario_supabase)
        )

    usuario_por_email = _buscar_usuario_por_email(client, email)
    if usuario_por_email:
        return _usuario_publico(
            _atualizar_usuario_supabase_existente(client, usuario_por_email, usuario_supabase)
        )

    criado = _escrever_perfil_supabase(
        lambda payload: client.table("usuarios").insert(payload),
        montar_dados_usuario_supabase(
            usuario_supabase,
            primeiro_usuario=_contar_usuarios(client) == 0,
        ),
    )
    if criado is None:
        raise AppError(
            status_code=503,
            code="perfil_indisponivel",
            message="Nao foi possivel criar o perfil do usuario. Tente novamente.",
            details={},
        )
    return _usuario_publico(criado)


def buscar_usuario_padrao_sem_token() -> dict:
    client = get_supabase_client()
    try:
        usuario = first_or_none(
            client.table("usuarios")
            .select("*")
            .eq("situacao", "ativo")
            .order("criado_em")
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _usuario_sem_token()
        raise
    if usuario:
        return _usuario_publico(usuario)
    return _usuario_sem_token()


def usuario_sem_token() -> dict:
    return _usuario_sem_token()


def _usuario_sem_token() -> dict:
    agora = datetime.now(UTC)
    return {
        "id": USUARIO_SEM_TOKEN_ID,
        "email": "sem-token@padoka.local",
        "nome": "Acesso sem token",
        "foto_url": None,
        "data_nascimento": None,
        "telefone": None,
        "papel": "dono",
        "situacao": "ativo",
        "criado_em": agora,
        "atualizado_em": agora,
    }


def logout(sessao_id: UUID | str) -> dict:
    client = get_supabase_client()
    client.table("sessoes_usuario").update(
        to_db_payload({"revogado_em": datetime.now(UTC)})
    ).eq("id", str(sessao_id)).execute()
    return {"sucesso": True}


def atualizar_perfil(usuario_id: UUID | str, requisicao: RequisicaoAtualizarPerfil) -> dict:
    client = get_supabase_client()
    usuario = buscar_linha_usuario(usuario_id)
    dados = requisicao.model_dump(exclude_unset=True)
    if "email" in dados and dados["email"] is not None:
        novo_email = normalizar_email(str(dados["email"]))
        existente = _buscar_usuario_por_email(client, novo_email)
        if existente and existente["id"] != usuario["id"]:
            raise ConflictError(
                "Ja existe usuario cadastrado com esse e-mail.",
                {"email": novo_email},
            )
        dados["email"] = novo_email
    if not dados:
        return _usuario_publico(usuario)
    atualizado = (
        client.table("usuarios")
        .update(to_db_payload(dados))
        .eq("id", str(usuario_id))
        .execute()
        .data[0]
    )
    return _usuario_publico(atualizado)


async def atualizar_foto_perfil(usuario_id: UUID | str | None, file: UploadFile) -> dict:
    if not usuario_id:
        raise AppError(
            status_code=400,
            code="profile_unavailable",
            message="Nao ha usuario autenticado para atualizar foto de perfil.",
            details={},
        )
    buscar_linha_usuario(usuario_id)
    client = get_supabase_client()
    midia = await servico_de_midia.enviar_midia(
        tipo_entidade="usuario",
        entidade_id=UUID(str(usuario_id)),
        file=file,
        descricao="Foto de perfil",
        texto_alternativo="Foto de perfil do usuario",
        definir_como_principal=False,
    )
    foto_url = midia.get("url_publica")
    if not foto_url:
        raise AppError(
            status_code=500,
            code="profile_photo_url_unavailable",
            message="Nao foi possivel gerar a URL publica da foto de perfil.",
            details={"midia_id": midia.get("id")},
        )
    atualizado = (
        client.table("usuarios")
        .update(to_db_payload({"foto_url": foto_url}))
        .eq("id", str(usuario_id))
        .execute()
        .data[0]
    )
    return _usuario_publico(atualizado)


def trocar_senha(usuario_id: UUID | str, requisicao: RequisicaoTrocarSenha) -> dict:
    client = get_supabase_client()
    usuario = buscar_linha_usuario(usuario_id)
    if not verificar_senha(requisicao.senha_atual, usuario["senha_hash"]):
        raise AppError(
            status_code=401,
            code="invalid_current_password",
            message="Senha atual invalida.",
            details={},
        )
    client.table("usuarios").update(
        to_db_payload({"senha_hash": gerar_hash_senha(requisicao.nova_senha)})
    ).eq("id", str(usuario_id)).execute()
    client.table("sessoes_usuario").update(
        to_db_payload({"revogado_em": datetime.now(UTC)})
    ).eq("usuario_id", str(usuario_id)).is_("revogado_em", "null").execute()
    return {"sucesso": True}


def listar_usuarios() -> list[dict]:
    client = get_supabase_client()
    try:
        usuarios = client.table("usuarios").select("*").order("criado_em").execute().data
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return []
        raise
    return [_usuario_publico(usuario) for usuario in usuarios]


def atualizar_papel_usuario(usuario_id: UUID, requisicao: RequisicaoAtualizarPapel) -> dict:
    client = get_supabase_client()
    buscar_linha_usuario(usuario_id)
    usuario = (
        client.table("usuarios")
        .update(to_db_payload({"papel": requisicao.papel}))
        .eq("id", str(usuario_id))
        .execute()
        .data[0]
    )
    return _usuario_publico(usuario)


def atualizar_plano_usuario(usuario_id: UUID, requisicao: RequisicaoAtualizarPlano) -> dict:
    client = get_supabase_client()
    buscar_linha_usuario(usuario_id)
    usuario = (
        client.table("usuarios")
        .update(to_db_payload({"plano": requisicao.plano}))
        .eq("id", str(usuario_id))
        .execute()
        .data[0]
    )
    return _usuario_publico(usuario)


def buscar_linha_usuario(usuario_id: UUID | str) -> dict:
    client = get_supabase_client()
    try:
        usuario = first_or_none(
            client.table("usuarios").select("*").eq("id", str(usuario_id)).limit(1).execute().data
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            raise NotFoundError("Usuario", str(usuario_id)) from exc
        raise
    if not usuario:
        raise NotFoundError("Usuario", str(usuario_id))
    return usuario


def papel_atende(usuario: dict, papeis: tuple[str, ...]) -> bool:
    papel_usuario = usuario.get("papel", "usuario")
    return any(PAPEIS_ORDENADOS[papel_usuario] >= PAPEIS_ORDENADOS[papel] for papel in papeis)


def _buscar_usuario_por_email(client, email: str) -> dict | None:
    return first_or_none(
        client.table("usuarios").select("*").eq("email", email).limit(1).execute().data
    )


def _buscar_usuario_por_supabase_auth_id(client, auth_id: str) -> dict | None:
    try:
        return first_or_none(
            client.table("usuarios")
            .select("*")
            .eq("supabase_auth_id", auth_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:
        if _erro_coluna_ausente(exc, "supabase_auth_id"):
            return None
        raise


def _atualizar_usuario_supabase_existente(client, usuario: dict, usuario_supabase: dict) -> dict:
    dados_supabase = montar_dados_usuario_supabase(
        usuario_supabase,
        primeiro_usuario=usuario.get("papel") == "dono",
    )
    dados = {
        "supabase_auth_id": dados_supabase["supabase_auth_id"],
        "email": dados_supabase["email"],
    }
    if not usuario.get("nome") and dados_supabase.get("nome"):
        dados["nome"] = dados_supabase["nome"]
    if not usuario.get("foto_url") and dados_supabase.get("foto_url"):
        dados["foto_url"] = dados_supabase["foto_url"]
    if not usuario.get("telefone") and dados_supabase.get("telefone"):
        dados["telefone"] = dados_supabase["telefone"]
    atualizado = _escrever_perfil_supabase(
        lambda payload: client.table("usuarios").update(payload).eq("id", usuario["id"]),
        to_db_payload(dados),
    )
    return atualizado or usuario


def _escrever_perfil_supabase(construir_consulta, payload: dict) -> dict | None:
    """Executa insert/update do perfil vindo do Supabase tolerando ambientes
    onde a coluna ``supabase_auth_id`` (migracao 012) ainda nao existe.

    Sem a coluna, refaz a escrita sem ela para o login nao quebrar com 500 -- o
    vinculo com o Supabase Auth fica pendente ate a migracao ser aplicada.
    """
    try:
        resultado = construir_consulta(payload).execute()
    except Exception as exc:
        if not _erro_coluna_ausente(exc, "supabase_auth_id"):
            raise
        payload_sem_vinculo = {
            coluna: valor for coluna, valor in payload.items() if coluna != "supabase_auth_id"
        }
        resultado = construir_consulta(payload_sem_vinculo).execute()
    linhas = getattr(resultado, "data", None) or []
    return linhas[0] if linhas else None


def _contar_usuarios(client) -> int:
    return len(client.table("usuarios").select("id").limit(2).execute().data)


def _usuario_publico(usuario: dict) -> dict:
    publico = {key: value for key, value in usuario.items() if key != "senha_hash"}
    publico["plano"] = publico.get("plano") or "basico"
    publico["capacidades"] = sorted(capacidades_do_usuario(publico))
    return publico


# Helpers centralizados em infra; aliases preservam os nomes locais.
_erro_tabela_ausente = tabela_ausente
_erro_coluna_ausente = coluna_ausente
