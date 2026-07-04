from uuid import UUID

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.locais.esquemas import RequisicaoAtualizarLocal, RequisicaoCriarLocal
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def listar_locais(*, somente_ativos: bool = True) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("locais").select("*").order("nome")
    if somente_ativos:
        consulta = consulta.eq("situacao", "ativo")
    return consulta.execute().data


def buscar_local(local_id: UUID | str) -> dict:
    client = get_supabase_client()
    local = first_or_none(
        client.table("locais").select("*").eq("id", str(local_id)).limit(1).execute().data
    )
    if not local:
        raise NotFoundError("Local", str(local_id))
    return local


def criar_local(requisicao: RequisicaoCriarLocal) -> dict:
    client = get_supabase_client()
    local = client.table("locais").insert(to_db_payload(requisicao.model_dump())).execute().data[0]
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="local_criado",
        titulo=f"Local criado: {local['nome']}",
        tipo_entidade="local",
        entidade_id=local["id"],
    )
    return local


def atualizar_local(local_id: UUID, requisicao: RequisicaoAtualizarLocal) -> dict:
    client = get_supabase_client()
    buscar_local(local_id)
    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if not dados_atualizacao:
        return buscar_local(local_id)
    local = (
        client.table("locais")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(local_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="local_atualizado",
        titulo=f"Local atualizado: {local['nome']}",
        tipo_entidade="local",
        entidade_id=local_id,
        detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
    )
    return local
