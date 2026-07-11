"""Relatorios de venda: consultas ao Supabase orquestrando a agregacao pura.

Toda a consolidacao (por produto, por data, leve por periodo) vive em
`domain.agregacao`; aqui ficam as consultas e a montagem das respostas.
"""

from datetime import date, timedelta
from uuid import UUID

from app.core.errors import NotFoundError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.result import executar_lista_opcional
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.historico import servico as servico_de_historico
from app.modules.relatorios.domain import agregacao
from app.shared.datas import validar_data_nao_futura, validar_periodo


def buscar_resumo_do_dia_de_venda(
    dia_de_venda_id: UUID,
    *,
    produto_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        client,
        dia_de_venda_id,
        usuario_id=usuario_id,
    )
    validar_data_nao_futura(date.fromisoformat(dia_de_venda["data_venda"]), campo="data_venda")
    itens_producao = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    vendas_ativas = (
        client.table("vendas")
        .select("id")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        itens_venda = (
            client.table("itens_venda").select("*").in_("venda_id", venda_ids).execute().data
        )
    decisoes_sobra = executar_lista_opcional(
        client.table("decisoes_sobra").select("*").eq("dia_destino_id", str(dia_de_venda_id))
    )

    produtos = agregacao.montar_resumos_dos_produtos(itens_producao, itens_venda, decisoes_sobra)
    if produto_id:
        produtos = [produto for produto in produtos if produto["produto_id"] == str(produto_id)]
    totais = agregacao.somar_produtos(produtos)
    historico = servico_de_historico.listar_eventos_da_linha_do_tempo(
        dia_de_venda_id=dia_de_venda_id,
        limite=500,
        usuario_id=usuario_id,
    )
    correcoes = _listar_correcoes_do_dia(client, dia_de_venda_id)
    produtos_produzidos = [produto for produto in produtos if produto["quantidade_produzida"] > 0]
    produtos_vendidos = [produto for produto in produtos if produto["quantidade_vendida"] > 0]
    produtos_sobrando = [produto for produto in produtos if produto["quantidade_sobra"] > 0]
    produtos_esgotados = [produto for produto in produtos if produto["esgotado"]]
    return {
        "dia_de_venda_id": dia_de_venda["id"],
        "dia_de_venda_ids": [dia_de_venda["id"]],
        "quantidade_aberturas": 1,
        "data_venda": dia_de_venda["data_venda"],
        "data": dia_de_venda["data_venda"],
        "nome_local": dia_de_venda.get("nome_local_no_momento"),
        "situacao": dia_de_venda["situacao"],
        "status": dia_de_venda["situacao"].upper(),
        **totais,
        "itens_vendidos": totais["total_vendido"],
        "faturamento_total": totais["faturamento_bruto"],
        "produtos": produtos,
        "produtos_produzidos": produtos_produzidos,
        "produtos_vendidos": produtos_vendidos,
        "produtos_sobrando": produtos_sobrando,
        "produtos_esgotados": produtos_esgotados,
        "historico": historico,
        "correcoes": correcoes,
    }


def buscar_resumo_do_dia_por_data(
    data_venda: date,
    *,
    produto_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    validar_data_nao_futura(data_venda, campo="data_venda")
    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("id")
        .eq("data_venda", data_venda.isoformat())
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    dias = consulta.order("aberto_em").execute().data
    if not dias:
        raise NotFoundError("Dia de venda", data_venda.isoformat())
    resumos = [
        buscar_resumo_do_dia_de_venda(
            UUID(dia["id"]),
            produto_id=produto_id,
            usuario_id=usuario_id,
        )
        for dia in dias
    ]
    return agregacao.consolidar_resumos_da_mesma_data(resumos)


def buscar_produtos_da_venda_do_dia(
    dia_de_venda_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    return buscar_resumo_do_dia_de_venda(dia_de_venda_id, usuario_id=usuario_id)["produtos"]


def buscar_resumo_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    produto_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    validar_periodo(data_inicio, data_fim)
    resumo = _buscar_resumo_leve_do_periodo(
        data_inicio,
        data_fim,
        incluir_dias=True,
        produto_id=produto_id,
        usuario_id=usuario_id,
    )
    resumo["produto_id"] = produto_id
    return resumo


def buscar_resumo_leve_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    comparar: bool = False,
    incluir_dias: bool = False,
    usuario_id: UUID | str | None = None,
) -> dict:
    validar_periodo(data_inicio, data_fim)
    resumo = _buscar_resumo_leve_do_periodo(
        data_inicio,
        data_fim,
        incluir_dias=incluir_dias,
        usuario_id=usuario_id,
    )
    if comparar:
        tamanho_periodo = (data_fim - data_inicio).days + 1
        data_fim_anterior = data_inicio - timedelta(days=1)
        data_inicio_anterior = data_inicio - timedelta(days=tamanho_periodo)
        resumo_anterior = _buscar_resumo_leve_do_periodo(
            data_inicio_anterior,
            data_fim_anterior,
            incluir_dias=False,
            usuario_id=usuario_id,
        )
        resumo["periodo_anterior"] = {
            "faturamento_bruto": resumo_anterior["faturamento_bruto"],
        }
    return resumo


def _buscar_resumo_leve_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    incluir_dias: bool,
    produto_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("id, data_venda, nome_local_no_momento, situacao, aberto_em")
        .gte("data_venda", data_inicio.isoformat())
        .lte("data_venda", data_fim.isoformat())
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    dias = consulta.order("data_venda").order("aberto_em").execute().data
    resumos_por_abertura = _montar_resumos_leves_das_aberturas(client, dias, produto_id=produto_id)
    resumos_por_data = agregacao.consolidar_resumos_leves_por_data(resumos_por_abertura)
    totais = agregacao.somar_dias(resumos_por_data)
    resumo = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "faturamento_bruto": totais["faturamento_bruto"],
        "lucro_estimado": totais["lucro_estimado"],
        "total_vendido": totais["total_vendido"],
        "total_sobra": totais["total_sobra"],
    }
    if incluir_dias:
        resumo["dias"] = agregacao.formatar_dias_leves(resumos_por_data)
    return resumo


def _montar_resumos_leves_das_aberturas(
    client,
    dias: list[dict],
    *,
    produto_id: UUID | None = None,
) -> list[dict]:
    dia_ids = [dia["id"] for dia in dias]
    if not dia_ids:
        return []

    itens_producao = (
        client.table("itens_producao").select("*").in_("dia_de_venda_id", dia_ids).execute().data
    )
    vendas_ativas = (
        client.table("vendas")
        .select("id, dia_de_venda_id")
        .in_("dia_de_venda_id", dia_ids)
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        itens_venda = (
            client.table("itens_venda").select("*").in_("venda_id", venda_ids).execute().data
        )
    decisoes_sobra = executar_lista_opcional(
        client.table("decisoes_sobra").select("*").in_("dia_destino_id", dia_ids)
    )

    producoes_por_dia = agregacao.agrupar_por_chave(itens_producao, "dia_de_venda_id")
    vendas_por_dia = agregacao.agrupar_por_chave(itens_venda, "dia_de_venda_id")
    decisoes_por_dia = agregacao.agrupar_por_chave(decisoes_sobra, "dia_destino_id")

    resumos = []
    for dia in dias:
        dia_id = dia["id"]
        produtos = agregacao.montar_resumos_dos_produtos(
            producoes_por_dia.get(dia_id, []),
            vendas_por_dia.get(dia_id, []),
            decisoes_por_dia.get(dia_id, []),
        )
        if produto_id:
            produtos = [
                produto for produto in produtos if str(produto["produto_id"]) == str(produto_id)
            ]
        totais = agregacao.somar_produtos(produtos)
        resumos.append(
            {
                "dia_de_venda_id": dia_id,
                "data_venda": dia["data_venda"],
                "nome_local": dia.get("nome_local_no_momento"),
                "situacao": dia["situacao"],
                **totais,
            }
        )
    return resumos


def _listar_correcoes_do_dia(client, dia_de_venda_id: UUID) -> list[dict]:
    return executar_lista_opcional(
        client.table("correcoes_dia_fechado")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .order("criado_em", desc=True)
    )
