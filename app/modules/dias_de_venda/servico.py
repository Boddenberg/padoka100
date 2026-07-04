from datetime import date, datetime, timezone
from uuid import UUID

from supabase import Client

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda.esquemas import (
    RequisicaoAtualizarDiaDeVenda,
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
)
from app.modules.locais import servico as servico_de_locais
from app.modules.produtos import servico as servico_de_produtos
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def listar_dias_de_venda(
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("dias_de_venda").select("*").order("data_venda", desc=True)
    if data_inicio:
        consulta = consulta.gte("data_venda", data_inicio.isoformat())
    if data_fim:
        consulta = consulta.lte("data_venda", data_fim.isoformat())
    if situacao:
        consulta = consulta.eq("situacao", situacao)
    dias = consulta.execute().data
    return [_anexar_itens_producao(client, dia) for dia in dias]


def criar_dia_de_venda(requisicao: RequisicaoCriarDiaDeVenda) -> dict:
    client = get_supabase_client()
    nome_local_no_momento = requisicao.nome_local
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        nome_local_no_momento = local["nome"]

    dados_dia = to_db_payload(
        {
            "data_venda": requisicao.data_venda,
            "local_id": requisicao.local_id,
            "nome_local_no_momento": nome_local_no_momento,
            "observacoes": requisicao.observacoes,
            "situacao": "aberto",
        }
    )
    dia_de_venda = client.table("dias_de_venda").insert(dados_dia).execute().data[0]
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_aberto",
        titulo=f"Dia aberto: {dia_de_venda['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda["id"],
        dia_de_venda_id=dia_de_venda["id"],
        detalhes={"nome_local": nome_local_no_momento},
    )

    for item in requisicao.itens_producao:
        salvar_item_producao(UUID(dia_de_venda["id"]), item)

    return buscar_dia_de_venda(UUID(dia_de_venda["id"]))


def buscar_dia_de_venda_atual(*, data_venda: date | None = None) -> dict:
    client = get_supabase_client()
    consulta = client.table("dias_de_venda").select("*").eq("situacao", "aberto").order("aberto_em", desc=True)
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    dia_de_venda = first_or_none(consulta.limit(1).execute().data)
    if not dia_de_venda:
        raise NotFoundError("Dia de venda aberto", data_venda.isoformat() if data_venda else "atual")
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_dia_de_venda(dia_de_venda_id: UUID | str) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_linha_dia_de_venda(client: Client, dia_de_venda_id: UUID | str) -> dict:
    dia_de_venda = first_or_none(
        client.table("dias_de_venda").select("*").eq("id", str(dia_de_venda_id)).limit(1).execute().data
    )
    if not dia_de_venda:
        raise NotFoundError("Dia de venda", str(dia_de_venda_id))
    return dia_de_venda


def atualizar_dia_de_venda(dia_de_venda_id: UUID, requisicao: RequisicaoAtualizarDiaDeVenda) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel editar um dia fechado.")

    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        dados_atualizacao["nome_local_no_momento"] = local["nome"]
    elif requisicao.nome_local is not None:
        dados_atualizacao["nome_local_no_momento"] = requisicao.nome_local
    dados_atualizacao.pop("nome_local", None)

    if dados_atualizacao:
        dia_de_venda = (
            client.table("dias_de_venda")
            .update(to_db_payload(dados_atualizacao))
            .eq("id", str(dia_de_venda_id))
            .execute()
            .data[0]
        )
        registrar_evento_na_linha_do_tempo(
            client,
            tipo_evento="dia_de_venda_atualizado",
            titulo=f"Dia atualizado: {dia_de_venda['data_venda']}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_de_venda_id,
            dia_de_venda_id=dia_de_venda_id,
            detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
        )
    return _anexar_itens_producao(client, dia_de_venda)


def salvar_item_producao(dia_de_venda_id: UUID, requisicao: RequisicaoCriarItemProducao) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel alterar a producao de um dia fechado.")

    snapshot = servico_de_produtos.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
    )
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    dados_item = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda_id,
            "produto_id": requisicao.produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco["preco_venda"],
            "preco_custo_unitario_no_momento": preco["preco_custo"],
            "quantidade_produzida": requisicao.quantidade_produzida,
            "observacoes": requisicao.observacoes,
        }
    )

    existente = first_or_none(
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("produto_id", str(requisicao.produto_id))
        .limit(1)
        .execute()
        .data
    )
    if existente:
        item = (
            client.table("itens_producao")
            .update(dados_item)
            .eq("id", existente["id"])
            .execute()
            .data[0]
        )
        tipo_evento = "item_producao_atualizado"
        titulo = f"Producao atualizada: {produto['nome']}"
    else:
        item = client.table("itens_producao").insert(dados_item).execute().data[0]
        tipo_evento = "item_producao_adicionado"
        titulo = f"Producao adicionada: {produto['nome']}"

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento=tipo_evento,
        titulo=titulo,
        tipo_entidade="item_producao",
        entidade_id=item["id"],
        dia_de_venda_id=dia_de_venda_id,
        detalhes={
            "produto_id": str(requisicao.produto_id),
            "quantidade_produzida": requisicao.quantidade_produzida,
            "preco_venda_unitario_no_momento": preco["preco_venda"],
        },
    )
    return item


def fechar_dia_de_venda(dia_de_venda_id: UUID, requisicao: RequisicaoFecharDiaDeVenda) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        return _anexar_itens_producao(client, dia_de_venda)

    dados_atualizacao = {
        "situacao": "fechado",
        "fechado_em": datetime.now(timezone.utc),
    }
    if requisicao.observacoes is not None:
        dados_atualizacao["observacoes"] = requisicao.observacoes
    dia_fechado = (
        client.table("dias_de_venda")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(dia_de_venda_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_fechado",
        titulo=f"Dia fechado: {dia_fechado['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda_id,
        dia_de_venda_id=dia_de_venda_id,
    )
    return _anexar_itens_producao(client, dia_fechado)


def _anexar_itens_producao(client: Client, dia_de_venda: dict) -> dict:
    itens = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
    dia_de_venda["itens_producao"] = itens
    return dia_de_venda
