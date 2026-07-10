from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.historico import servico as servico_de_historico
from app.shared.datas import validar_data_nao_futura, validar_periodo


def buscar_resumo_do_dia_de_venda(
    dia_de_venda_id: UUID,
    *,
    produto_id: UUID | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(client, dia_de_venda_id)
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
            client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )
    decisoes_sobra = _executar_lista_opcional(
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
    )

    produtos = _montar_resumos_dos_produtos(itens_producao, itens_venda, decisoes_sobra)
    if produto_id:
        produtos = [produto for produto in produtos if produto["produto_id"] == str(produto_id)]
    totais = _somar_produtos(produtos)
    historico = servico_de_historico.listar_eventos_da_linha_do_tempo(
        dia_de_venda_id=dia_de_venda_id,
        limite=500,
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
) -> dict:
    validar_data_nao_futura(data_venda, campo="data_venda")
    client = get_supabase_client()
    dias = (
        client.table("dias_de_venda")
        .select("id")
        .eq("data_venda", data_venda.isoformat())
        .order("aberto_em")
        .execute()
        .data
    )
    if not dias:
        raise NotFoundError("Dia de venda", data_venda.isoformat())
    resumos = [
        buscar_resumo_do_dia_de_venda(UUID(dia["id"]), produto_id=produto_id) for dia in dias
    ]
    return _consolidar_resumos_da_mesma_data(resumos)


def buscar_produtos_da_venda_do_dia(dia_de_venda_id: UUID) -> list[dict]:
    return buscar_resumo_do_dia_de_venda(dia_de_venda_id)["produtos"]


def buscar_resumo_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    produto_id: UUID | None = None,
) -> dict:
    validar_periodo(data_inicio, data_fim)
    resumo = _buscar_resumo_leve_do_periodo(
        data_inicio,
        data_fim,
        incluir_dias=True,
        produto_id=produto_id,
    )
    resumo["produto_id"] = produto_id
    return resumo


def buscar_resumo_leve_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    comparar: bool = False,
    incluir_dias: bool = False,
) -> dict:
    validar_periodo(data_inicio, data_fim)
    resumo = _buscar_resumo_leve_do_periodo(data_inicio, data_fim, incluir_dias=incluir_dias)
    if comparar:
        tamanho_periodo = (data_fim - data_inicio).days + 1
        data_fim_anterior = data_inicio - timedelta(days=1)
        data_inicio_anterior = data_inicio - timedelta(days=tamanho_periodo)
        resumo_anterior = _buscar_resumo_leve_do_periodo(
            data_inicio_anterior,
            data_fim_anterior,
            incluir_dias=False,
        )
        resumo["periodo_anterior"] = {
            "faturamento_bruto": resumo_anterior["faturamento_bruto"],
        }
    return resumo


def _consolidar_resumos_da_mesma_data(resumos: list[dict]) -> dict:
    if len(resumos) == 1:
        return resumos[0]

    data_venda = resumos[0]["data_venda"]
    produtos = _consolidar_produtos_por_data(resumos)
    totais = _somar_produtos(produtos)
    historico = []
    correcoes = []
    locais = {
        resumo.get("nome_local")
        for resumo in resumos
        if resumo.get("nome_local")
    }
    for resumo in resumos:
        historico.extend(resumo.get("historico") or [])
        correcoes.extend(resumo.get("correcoes") or [])

    produtos_produzidos = [produto for produto in produtos if produto["quantidade_produzida"] > 0]
    produtos_vendidos = [produto for produto in produtos if produto["quantidade_vendida"] > 0]
    produtos_sobrando = [produto for produto in produtos if produto["quantidade_sobra"] > 0]
    produtos_esgotados = [produto for produto in produtos if produto["esgotado"]]
    dia_ids = [
        dia_id
        for resumo in resumos
        for dia_id in (resumo.get("dia_de_venda_ids") or [resumo["dia_de_venda_id"]])
    ]
    situacao = "aberto" if any(resumo["situacao"] == "aberto" for resumo in resumos) else "fechado"
    return {
        "dia_de_venda_id": resumos[-1]["dia_de_venda_id"],
        "dia_de_venda_ids": dia_ids,
        "quantidade_aberturas": len(dia_ids),
        "data_venda": data_venda,
        "data": data_venda,
        "nome_local": next(iter(locais)) if len(locais) == 1 else "Multiplas aberturas",
        "situacao": situacao,
        "status": situacao.upper(),
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


def _consolidar_produtos_por_data(resumos: list[dict]) -> list[dict]:
    produtos_por_id: dict[str, dict] = {}
    for resumo in resumos:
        for produto in resumo["produtos"]:
            produto_id = produto["produto_id"]
            if produto_id not in produtos_por_id:
                produtos_por_id[produto_id] = {
                    **produto,
                    "faturamento_bruto": Decimal("0"),
                    "custo_estimado": Decimal("0"),
                    "lucro_estimado": Decimal("0"),
                    "quantidade_produzida": 0,
                    "quantidade_sobra_aproveitada": 0,
                    "quantidade_sobra_descartada": 0,
                    "quantidade_disponivel": 0,
                    "quantidade_vendida": 0,
                    "quantidade_sobra": 0,
                }
            acumulado = produtos_por_id[produto_id]
            acumulado["quantidade_produzida"] += produto["quantidade_produzida"]
            acumulado["quantidade_sobra_aproveitada"] += produto["quantidade_sobra_aproveitada"]
            acumulado["quantidade_sobra_descartada"] += produto[
                "quantidade_sobra_descartada"
            ]
            acumulado["quantidade_disponivel"] += produto["quantidade_disponivel"]
            acumulado["quantidade_vendida"] += produto["quantidade_vendida"]
            acumulado["faturamento_bruto"] += Decimal(str(produto["faturamento_bruto"]))
            acumulado["custo_estimado"] += Decimal(str(produto["custo_estimado"]))
            acumulado["lucro_estimado"] += Decimal(str(produto["lucro_estimado"]))
            acumulado["quantidade_sobra"] = (
                acumulado["quantidade_disponivel"] - acumulado["quantidade_vendida"]
            )
            acumulado["participou_da_venda"] = True
            acumulado["esgotado"] = (
                acumulado["quantidade_disponivel"] > 0
                and acumulado["quantidade_vendida"] >= acumulado["quantidade_disponivel"]
            )
    return sorted(produtos_por_id.values(), key=lambda produto: produto["nome_produto"])


def _buscar_resumo_leve_do_periodo(
    data_inicio: date,
    data_fim: date,
    *,
    incluir_dias: bool,
    produto_id: UUID | None = None,
) -> dict:
    client = get_supabase_client()
    dias = (
        client.table("dias_de_venda")
        .select("id, data_venda, nome_local_no_momento, situacao, aberto_em")
        .gte("data_venda", data_inicio.isoformat())
        .lte("data_venda", data_fim.isoformat())
        .order("data_venda")
        .order("aberto_em")
        .execute()
        .data
    )
    resumos_por_abertura = _montar_resumos_leves_das_aberturas(
        client,
        dias,
        produto_id=produto_id,
    )
    resumos_por_data = _consolidar_resumos_leves_por_data(resumos_por_abertura)
    totais = _somar_dias(resumos_por_data)
    resumo = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "faturamento_bruto": totais["faturamento_bruto"],
        "lucro_estimado": totais["lucro_estimado"],
        "total_vendido": totais["total_vendido"],
        "total_sobra": totais["total_sobra"],
    }
    if incluir_dias:
        resumo["dias"] = _formatar_dias_leves(resumos_por_data)
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
        client.table("itens_producao")
        .select("*")
        .in_("dia_de_venda_id", dia_ids)
        .execute()
        .data
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
            client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )
    decisoes_sobra = _executar_lista_opcional(
        client.table("decisoes_sobra").select("*").in_("dia_destino_id", dia_ids)
    )

    producoes_por_dia = _agrupar_por_chave(itens_producao, "dia_de_venda_id")
    vendas_por_dia = _agrupar_por_chave(itens_venda, "dia_de_venda_id")
    decisoes_por_dia = _agrupar_por_chave(decisoes_sobra, "dia_destino_id")

    resumos = []
    for dia in dias:
        dia_id = dia["id"]
        produtos = _montar_resumos_dos_produtos(
            producoes_por_dia.get(dia_id, []),
            vendas_por_dia.get(dia_id, []),
            decisoes_por_dia.get(dia_id, []),
        )
        if produto_id:
            produtos = [
                produto
                for produto in produtos
                if str(produto["produto_id"]) == str(produto_id)
            ]
        totais = _somar_produtos(produtos)
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


def _agrupar_por_chave(linhas: list[dict], chave: str) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(str(linha[chave]), []).append(linha)
    return grupos


def _consolidar_resumos_leves_por_data(resumos: list[dict]) -> list[dict]:
    resumos_por_data = _agrupar_por_chave(resumos, "data_venda")
    return [
        _consolidar_resumos_leves_da_mesma_data(resumos_por_data[data_venda])
        for data_venda in sorted(resumos_por_data)
    ]


def _consolidar_resumos_leves_da_mesma_data(resumos: list[dict]) -> dict:
    if len(resumos) == 1:
        return resumos[0]

    totais = _somar_dias(resumos)
    locais = {resumo.get("nome_local") for resumo in resumos if resumo.get("nome_local")}
    situacao = "aberto" if any(resumo["situacao"] == "aberto" for resumo in resumos) else "fechado"
    return {
        "dia_de_venda_id": resumos[-1]["dia_de_venda_id"],
        "data_venda": resumos[0]["data_venda"],
        "nome_local": next(iter(locais)) if len(locais) == 1 else "Multiplas aberturas",
        "situacao": situacao,
        **totais,
    }


def _formatar_dias_leves(resumos: list[dict]) -> list[dict]:
    return [
        {
            "dia_de_venda_id": resumo["dia_de_venda_id"],
            "data_venda": resumo["data_venda"],
            "nome_local": resumo.get("nome_local"),
            "situacao": resumo["situacao"],
            "faturamento_bruto": resumo["faturamento_bruto"],
            "lucro_estimado": resumo["lucro_estimado"],
        }
        for resumo in resumos
    ]


def _montar_resumos_dos_produtos(
    itens_producao: list[dict],
    itens_venda: list[dict],
    decisoes_sobra: list[dict],
) -> list[dict]:
    resumos: dict[str, dict] = {}

    for item in itens_producao:
        produto_id = item["produto_id"]
        resumos[produto_id] = {
            "produto_id": produto_id,
            "nome_produto": item["nome_produto_no_momento"],
            "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
            "participou_da_venda": True,
            "esgotado": False,
            "quantidade_produzida": item["quantidade_produzida"],
            "quantidade_sobra_aproveitada": 0,
            "quantidade_sobra_descartada": 0,
            "quantidade_disponivel": item["quantidade_produzida"],
            "quantidade_vendida": 0,
            "quantidade_sobra": item["quantidade_produzida"],
            "faturamento_bruto": Decimal("0"),
            "custo_estimado": Decimal("0"),
            "lucro_estimado": Decimal("0"),
        }

    for item in decisoes_sobra:
        quantidade_usada = item["quantidade_usada_hoje"]
        quantidade_descartada = item["quantidade_nao_usada_hoje"]
        if quantidade_usada <= 0 and quantidade_descartada <= 0:
            continue
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": item["nome_produto_no_momento"],
                "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
                "participou_da_venda": True,
                "esgotado": False,
                "quantidade_produzida": 0,
                "quantidade_sobra_aproveitada": 0,
                "quantidade_sobra_descartada": 0,
                "quantidade_disponivel": 0,
                "quantidade_vendida": 0,
                "quantidade_sobra": 0,
                "faturamento_bruto": Decimal("0"),
                "custo_estimado": Decimal("0"),
                "lucro_estimado": Decimal("0"),
            }
        resumo = resumos[produto_id]
        resumo["quantidade_sobra_aproveitada"] += quantidade_usada
        resumo["quantidade_sobra_descartada"] += quantidade_descartada
        resumo["quantidade_disponivel"] = (
            resumo["quantidade_produzida"] + resumo["quantidade_sobra_aproveitada"]
        )
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    for item in itens_venda:
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": item["nome_produto_no_momento"],
                "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
                "participou_da_venda": True,
                "esgotado": False,
                "quantidade_produzida": 0,
                "quantidade_sobra_aproveitada": 0,
                "quantidade_sobra_descartada": 0,
                "quantidade_disponivel": 0,
                "quantidade_vendida": 0,
                "quantidade_sobra": 0,
                "faturamento_bruto": Decimal("0"),
                "custo_estimado": Decimal("0"),
                "lucro_estimado": Decimal("0"),
            }
        resumo = resumos[produto_id]
        resumo["quantidade_vendida"] += item["quantidade"]
        resumo["faturamento_bruto"] += Decimal(str(item["valor_total_venda"]))
        resumo["custo_estimado"] += Decimal(str(item["valor_total_custo"]))
        resumo["lucro_estimado"] = resumo["faturamento_bruto"] - resumo["custo_estimado"]
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    produtos = [_finalizar_resumo_produto(produto) for produto in resumos.values()]
    produtos = [produto for produto in produtos if produto["participou_da_venda"]]
    return sorted(produtos, key=lambda produto: produto["nome_produto"])


def _finalizar_resumo_produto(produto: dict) -> dict:
    participou = any(
        [
            produto["quantidade_produzida"] > 0,
            produto["quantidade_sobra_aproveitada"] > 0,
            produto["quantidade_sobra_descartada"] > 0,
            produto["quantidade_vendida"] > 0,
        ]
    )
    produto["participou_da_venda"] = participou
    produto["esgotado"] = (
        produto["quantidade_disponivel"] > 0
        and produto["quantidade_vendida"] >= produto["quantidade_disponivel"]
    )
    return produto


def _somar_produtos(produtos: list[dict]) -> dict:
    return {
        "total_produzido": sum(produto["quantidade_produzida"] for produto in produtos),
        "total_sobra_aproveitada": sum(
            produto["quantidade_sobra_aproveitada"] for produto in produtos
        ),
        "total_sobra_descartada": sum(
            produto["quantidade_sobra_descartada"] for produto in produtos
        ),
        "total_disponivel": sum(produto["quantidade_disponivel"] for produto in produtos),
        "total_vendido": sum(produto["quantidade_vendida"] for produto in produtos),
        "total_sobra": sum(produto["quantidade_sobra"] for produto in produtos),
        "faturamento_bruto": sum(
            (produto["faturamento_bruto"] for produto in produtos),
            Decimal("0"),
        ),
        "custo_estimado": sum((produto["custo_estimado"] for produto in produtos), Decimal("0")),
        "lucro_estimado": sum((produto["lucro_estimado"] for produto in produtos), Decimal("0")),
    }


def _somar_dias(dias: list[dict]) -> dict:
    return {
        "total_produzido": sum(dia["total_produzido"] for dia in dias),
        "total_sobra_aproveitada": sum(dia["total_sobra_aproveitada"] for dia in dias),
        "total_sobra_descartada": sum(dia["total_sobra_descartada"] for dia in dias),
        "total_disponivel": sum(dia["total_disponivel"] for dia in dias),
        "total_vendido": sum(dia["total_vendido"] for dia in dias),
        "total_sobra": sum(dia["total_sobra"] for dia in dias),
        "faturamento_bruto": sum((dia["faturamento_bruto"] for dia in dias), Decimal("0")),
        "custo_estimado": sum((dia["custo_estimado"] for dia in dias), Decimal("0")),
        "lucro_estimado": sum((dia["lucro_estimado"] for dia in dias), Decimal("0")),
    }


def _listar_correcoes_do_dia(client, dia_de_venda_id: UUID) -> list[dict]:
    return _executar_lista_opcional(
        client.table("correcoes_dia_fechado")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .order("criado_em", desc=True)
    )


def _executar_lista_opcional(consulta) -> list[dict]:
    try:
        return consulta.execute().data
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return []
        raise


def _erro_tabela_ausente(exc: Exception) -> bool:
    mensagem = str(exc)
    return "PGRST205" in mensagem and "Could not find the table" in mensagem
