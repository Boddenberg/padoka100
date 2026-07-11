"""Servico base de dia de venda: CRUD, producao e fechamento.

Os fluxos maiores (iniciar dia e corrigir dia fechado) vivem em `use_cases/`;
aqui ficam as operacoes de base e as fachadas finas que outros modulos usam.

Todo acesso a dias de venda passa por ``buscar_linha_dia_de_venda`` (ou pelas
listagens), que aplicam o filtro de dono. Itens de producao e decisoes de
sobra herdam o escopo do dia ja validado.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from app.core.errors import BadRequestError, NotFoundError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.payload import first_or_none, to_db_payload
from app.modules.dias_de_venda.esquemas import (
    RequisicaoAtualizarDiaDeVenda,
    RequisicaoCorrigirDiaFechado,
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
    RequisicaoIniciarDiaDeVenda,
)
from app.modules.locais import servico as servico_de_locais
from app.modules.produtos import public as produtos_public
from app.shared.datas import validar_data_nao_futura, validar_periodo
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from supabase import Client


def listar_dias_de_venda(
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    if data_inicio and data_fim:
        validar_periodo(data_inicio, data_fim)
    elif data_inicio:
        validar_data_nao_futura(data_inicio, campo="data_inicio")
    elif data_fim:
        validar_data_nao_futura(data_fim, campo="data_fim")

    client = get_supabase_client()
    consulta = client.table("dias_de_venda").select("*").order("data_venda", desc=True)
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    if data_inicio:
        consulta = consulta.gte("data_venda", data_inicio.isoformat())
    if data_fim:
        consulta = consulta.lte("data_venda", data_fim.isoformat())
    if situacao:
        consulta = consulta.eq("situacao", situacao)
    dias = consulta.execute().data
    return [anexar_itens_producao(client, dia) for dia in dias]


def criar_dia_de_venda(
    requisicao: RequisicaoCriarDiaDeVenda,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    validar_data_nao_futura(requisicao.data_venda, campo="data_venda")
    client = get_supabase_client()
    nome_local_no_momento = requisicao.nome_local
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id, usuario_id=usuario_id)
        nome_local_no_momento = local["nome"]

    dados_dia = to_db_payload(
        {
            "data_venda": requisicao.data_venda,
            "local_id": requisicao.local_id,
            "nome_local_no_momento": nome_local_no_momento,
            "observacoes": requisicao.observacoes,
            "situacao": "aberto",
            "usuario_id": usuario_id,
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
        usuario_id=usuario_id,
        detalhes={"nome_local": nome_local_no_momento},
    )

    for item in requisicao.itens_producao:
        salvar_item_producao(UUID(dia_de_venda["id"]), item, usuario_id=usuario_id)

    return buscar_dia_de_venda(UUID(dia_de_venda["id"]), usuario_id=usuario_id)


def buscar_dia_de_venda_atual(
    *,
    data_venda: date | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    if data_venda:
        validar_data_nao_futura(data_venda, campo="data_venda")

    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .order("aberto_em", desc=True)
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    dia_de_venda = first_or_none(consulta.limit(1).execute().data)
    if not dia_de_venda:
        raise NotFoundError(
            "Dia de venda aberto",
            data_venda.isoformat() if data_venda else "atual",
        )
    return anexar_itens_producao(client, dia_de_venda)


def buscar_dia_de_venda(
    dia_de_venda_id: UUID | str,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id, usuario_id=usuario_id)
    return anexar_itens_producao(client, dia_de_venda)


def buscar_linha_dia_de_venda(
    client: Client,
    dia_de_venda_id: UUID | str,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    consulta = client.table("dias_de_venda").select("*").eq("id", str(dia_de_venda_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    dia_de_venda = first_or_none(consulta.limit(1).execute().data)
    if not dia_de_venda:
        raise NotFoundError("Dia de venda", str(dia_de_venda_id))
    return dia_de_venda


def atualizar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoAtualizarDiaDeVenda,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id, usuario_id=usuario_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel editar um dia fechado.")

    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id, usuario_id=usuario_id)
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
            usuario_id=usuario_id,
            detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
        )
    return anexar_itens_producao(client, dia_de_venda)


def salvar_item_producao(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCriarItemProducao,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id, usuario_id=usuario_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel alterar a producao de um dia fechado.")

    snapshot = produtos_public.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
        usuario_id=usuario_id,
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
        usuario_id=usuario_id,
        detalhes={
            "produto_id": str(requisicao.produto_id),
            "quantidade_produzida": requisicao.quantidade_produzida,
            "preco_venda_unitario_no_momento": preco["preco_venda"],
        },
    )
    return item


def fechar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoFecharDiaDeVenda,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id, usuario_id=usuario_id)
    if dia_de_venda["situacao"] == "fechado":
        return anexar_itens_producao(client, dia_de_venda)

    dados_atualizacao = {
        "situacao": "fechado",
        "fechado_em": datetime.now(UTC),
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
        usuario_id=usuario_id,
    )
    return anexar_itens_producao(client, dia_fechado)


def iniciar_dia_de_venda(
    requisicao: RequisicaoIniciarDiaDeVenda,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    from app.modules.dias_de_venda.use_cases.iniciar_dia import (
        iniciar_dia_de_venda as _iniciar,
    )

    return _iniciar(requisicao, usuario_id=usuario_id)


def corrigir_dia_fechado(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCorrigirDiaFechado,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    from app.modules.dias_de_venda.use_cases.correcao_dia_fechado import (
        corrigir_dia_fechado as _corrigir,
    )

    return _corrigir(dia_de_venda_id, requisicao, usuario_id=usuario_id)


def anexar_itens_producao(client: Client, dia_de_venda: dict) -> dict:
    itens = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
    dia_de_venda["itens_producao"] = itens
    dia_de_venda["sobras_usadas_hoje"] = listar_decisoes_sobra_do_destino(
        client,
        dia_de_venda["id"],
    )
    return dia_de_venda


def listar_decisoes_sobra_do_destino(client: Client, dia_de_venda_id: UUID | str) -> list[dict]:
    return (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
