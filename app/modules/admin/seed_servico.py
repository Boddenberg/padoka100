from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from random import Random
from uuid import UUID, uuid4

from app.core.errors import AppError, BadRequestError
from app.db.supabase import get_supabase_client
from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake
from app.modules.dias_de_venda import servico as servico_de_dias
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
)
from app.modules.produtos import servico as servico_de_produtos
from app.modules.produtos.esquemas import RequisicaoCriarProduto, RequisicaoCriarVersaoDePreco
from app.modules.vendas import servico as servico_de_vendas
from app.modules.vendas.esquemas import RequisicaoItemVendido, RequisicaoRegistrarVenda

PRODUTOS_FAKE = [
    ("[Seed] Pao Frances", Decimal("1.20"), Decimal("0.45")),
    ("[Seed] Pao de Queijo", Decimal("4.50"), Decimal("1.40")),
    ("[Seed] Pao Sovado", Decimal("8.90"), Decimal("3.10")),
    ("[Seed] Broa de Milho", Decimal("6.50"), Decimal("2.20")),
    ("[Seed] Rosca Doce", Decimal("7.90"), Decimal("2.70")),
    ("[Seed] Baguete", Decimal("9.50"), Decimal("3.40")),
    ("[Seed] Sonho", Decimal("6.00"), Decimal("2.10")),
    ("[Seed] Croissant", Decimal("12.00"), Decimal("4.80")),
]

OBSERVACOES_DIA = [
    "movimento forte no periodo da manha",
    "chuva reduziu o fluxo no fim do dia",
    "cliente pediu bastante item recheado",
    "produto tradicional teve giro acima do esperado",
    "fornada saiu um pouco mais tarde e concentrou vendas",
    "demanda estavel para comparativo de historico",
    "promocao local aumentou volume de unidades",
]

OBSERVACOES_ITEM = [
    "producao seed para teste de analytics",
    "volume simulado com variacao aleatoria",
    "fornada usada para historico fake",
]


def gerar_vendas_fake(requisicao: RequisicaoGerarVendasFake) -> dict:
    datas = _resolver_datas(requisicao)
    lote_id = uuid4()
    seed = requisicao.seed if requisicao.seed is not None else uuid4().int % 1_000_000_000
    rng = Random(seed)
    avisos: list[str] = []

    if requisicao.limpar_seed_anterior:
        removidos = _limpar_seed_anterior(datas, requisicao.marcador)
        if removidos:
            avisos.append(f"{removidos} dia(s) seed anterior removido(s) no periodo.")

    produtos = _resolver_produtos_para_seed(requisicao, datas, rng, avisos)
    if not produtos:
        raise BadRequestError("Nao ha produtos com preco vigente para gerar o historico fake.")

    dias_saida: list[dict] = []
    produtos_usados: dict[str, dict] = {}
    total_vendas = 0
    total_itens_venda = 0
    total_unidades_produzidas = 0
    total_unidades_vendidas = 0

    for data_venda in datas:
        selecionados = _selecionar_produtos_do_dia(requisicao, produtos, rng)
        observacao_abertura = _montar_observacao_abertura(
            marcador=requisicao.marcador,
            lote_id=lote_id,
            observacao_base=requisicao.observacao_base,
            rng=rng,
        )
        dia = servico_de_dias.criar_dia_de_venda(
            RequisicaoCriarDiaDeVenda(
                data_venda=data_venda,
                nome_local=requisicao.nome_local,
                observacoes=observacao_abertura,
            )
        )

        estoque: dict[str, int] = {}
        unidades_produzidas_dia = 0
        for produto in selecionados:
            quantidade = _quantidade_produzida(requisicao, data_venda, rng)
            item = servico_de_dias.salvar_item_producao(
                UUID(dia["id"]),
                RequisicaoCriarItemProducao(
                    produto_id=UUID(produto["id"]),
                    quantidade_produzida=quantidade,
                    observacoes=rng.choice(OBSERVACOES_ITEM),
                ),
            )
            estoque[str(produto["id"])] = quantidade
            unidades_produzidas_dia += quantidade
            produtos_usados[str(produto["id"])] = {
                "id": produto["id"],
                "nome": produto["nome"],
            }
            produtos_usados[str(item["produto_id"])] = {
                "id": item["produto_id"],
                "nome": item["nome_produto_no_momento"],
            }

        vendas_dia = 0
        itens_venda_dia = 0
        unidades_vendidas_dia = 0
        quantidade_vendas_planejada = rng.randint(
            requisicao.vendas_por_dia_min,
            requisicao.vendas_por_dia_max,
        )
        for _ in range(quantidade_vendas_planejada):
            itens = _montar_itens_de_venda(requisicao, selecionados, estoque, rng)
            if not itens:
                break
            ocorrido_em = _horario_aleatorio(data_venda, rng)
            venda = servico_de_vendas.registrar_venda(
                RequisicaoRegistrarVenda(
                    dia_de_venda_id=UUID(dia["id"]),
                    itens=itens,
                    tipo_entrada="manual",
                    texto_original=_descrever_venda_seed(itens, produtos_usados),
                    observacoes=f"{requisicao.marcador} venda simulada do lote {lote_id}",
                    ocorrido_em=ocorrido_em,
                ),
                detalhes_evento={
                    "origem": "seed_analytics",
                    "lote_id": str(lote_id),
                    "seed": seed,
                },
            )
            vendas_dia += 1
            itens_venda_dia += len(venda["itens"])
            unidades_vendidas_dia += sum(item["quantidade"] for item in venda["itens"])

        observacao_fechamento = None
        if requisicao.fechar_dias:
            observacao_fechamento = _montar_observacao_fechamento(
                requisicao=requisicao,
                lote_id=lote_id,
                rng=rng,
                unidades_produzidas=unidades_produzidas_dia,
                unidades_vendidas=unidades_vendidas_dia,
            )
            servico_de_dias.fechar_dia_de_venda(
                UUID(dia["id"]),
                RequisicaoFecharDiaDeVenda(observacoes=observacao_fechamento),
            )

        dias_saida.append(
            {
                "id": dia["id"],
                "data_venda": data_venda,
                "produtos_produzidos": len(selecionados),
                "vendas_criadas": vendas_dia,
                "itens_venda_criados": itens_venda_dia,
                "unidades_produzidas": unidades_produzidas_dia,
                "unidades_vendidas": unidades_vendidas_dia,
                "observacoes_fechamento": observacao_fechamento,
            }
        )
        total_vendas += vendas_dia
        total_itens_venda += itens_venda_dia
        total_unidades_produzidas += unidades_produzidas_dia
        total_unidades_vendidas += unidades_vendidas_dia

    return {
        "lote_id": lote_id,
        "seed": seed,
        "periodo_inicio": min(datas),
        "periodo_fim": max(datas),
        "total_dias": len(dias_saida),
        "total_vendas": total_vendas,
        "total_itens_venda": total_itens_venda,
        "total_unidades_produzidas": total_unidades_produzidas,
        "total_unidades_vendidas": total_unidades_vendidas,
        "produtos_usados": list(produtos_usados.values()),
        "dias": dias_saida,
        "avisos": avisos,
    }


def _resolver_datas(requisicao: RequisicaoGerarVendasFake) -> list[date]:
    hoje = date.today()
    if requisicao.datas:
        datas = sorted(set(requisicao.datas))
    else:
        if requisicao.data_inicio and requisicao.data_fim:
            inicio = requisicao.data_inicio
            fim = requisicao.data_fim
        elif requisicao.data_inicio:
            inicio = requisicao.data_inicio
            fim = min(hoje, inicio + timedelta(days=requisicao.quantidade_dias - 1))
        elif requisicao.data_fim:
            fim = requisicao.data_fim
            inicio = fim - timedelta(days=requisicao.quantidade_dias - 1)
        else:
            fim = hoje - timedelta(days=1)
            inicio = fim - timedelta(days=requisicao.quantidade_dias - 1)
        datas = [inicio + timedelta(days=offset) for offset in range((fim - inicio).days + 1)]

    if not datas:
        raise BadRequestError("Informe ao menos uma data para gerar o historico fake.")
    futuras = [data for data in datas if data > hoje]
    if futuras:
        raise BadRequestError(
            "Nao e possivel gerar vendas fake em datas futuras.",
            {"datas_futuras": [data.isoformat() for data in futuras]},
        )
    if len(datas) > 120:
        raise BadRequestError("Gere no maximo 120 dias por chamada.")
    return datas


def _limpar_seed_anterior(datas: list[date], marcador: str) -> int:
    client = get_supabase_client()
    linhas = (
        client.table("dias_de_venda")
        .select("id")
        .gte("data_venda", min(datas).isoformat())
        .lte("data_venda", max(datas).isoformat())
        .ilike("observacoes", f"%{marcador}%")
        .execute()
        .data
    )
    ids = [linha["id"] for linha in linhas]
    if not ids:
        return 0
    client.table("eventos_linha_do_tempo").delete().in_("dia_de_venda_id", ids).execute()
    client.table("dias_de_venda").delete().in_("id", ids).execute()
    return len(ids)


def _resolver_produtos_para_seed(
    requisicao: RequisicaoGerarVendasFake,
    datas: list[date],
    rng: Random,
    avisos: list[str],
) -> list[dict]:
    produtos: list[dict] = []
    if requisicao.produto_ids:
        for produto_id in requisicao.produto_ids:
            produto = servico_de_produtos.buscar_produto(produto_id, data_preco=min(datas))
            if _produto_tem_preco_para_datas(produto["id"], datas):
                produtos.append(produto)
            else:
                avisos.append(f"Produto {produto['nome']} ignorado por falta de preco no periodo.")
    else:
        candidatos = servico_de_produtos.listar_produtos(somente_ativos=True, data_preco=min(datas))
        produtos = [
            produto for produto in candidatos if _produto_tem_preco_para_datas(produto["id"], datas)
        ]

    minimo_desejado = min(
        max(requisicao.produtos_por_dia_min, min(requisicao.produtos_por_dia_max, 4)),
        len(PRODUTOS_FAKE),
    )
    if len(produtos) < minimo_desejado and requisicao.criar_produtos_fake_se_necessario:
        faltantes = minimo_desejado - len(produtos)
        produtos.extend(_garantir_produtos_fake(datas, faltantes, rng))
        avisos.append(
            "Produtos seed foram criados/reutilizados para garantir preco vigente no periodo."
        )
    return _deduplicar_produtos(produtos)


def _produto_tem_preco_para_datas(produto_id: UUID | str, datas: list[date]) -> bool:
    for data_alvo in datas:
        try:
            servico_de_produtos.buscar_snapshot_do_produto(produto_id, data_alvo)
        except AppError:
            return False
    return True


def _garantir_produtos_fake(datas: list[date], quantidade: int, rng: Random) -> list[dict]:
    client = get_supabase_client()
    existentes = (
        client.table("produtos")
        .select("*")
        .like("nome", "[Seed]%")
        .eq("situacao", "ativo")
        .execute()
        .data
    )
    por_nome = {produto["nome"]: produto for produto in existentes}
    specs = PRODUTOS_FAKE.copy()
    rng.shuffle(specs)
    produtos: list[dict] = []

    for nome, preco_venda, preco_custo in specs:
        if len(produtos) >= quantidade:
            break
        produto = por_nome.get(nome)
        if produto:
            _garantir_preco_seed(produto["id"], min(datas), preco_venda, preco_custo)
            produtos.append(
                servico_de_produtos.buscar_produto(
                    UUID(produto["id"]),
                    data_preco=min(datas),
                )
            )
            continue
        criado = servico_de_produtos.criar_produto(
            RequisicaoCriarProduto(
                nome=nome,
                descricao="Produto fake para testes de historico e analytics.",
                preco_venda=preco_venda,
                preco_custo=preco_custo,
                vigente_desde=min(datas),
                motivo_preco="Seed analytics",
            )
        )
        produtos.append(criado)
    return produtos


def _garantir_preco_seed(
    produto_id: UUID | str,
    data_inicio: date,
    preco_venda: Decimal,
    preco_custo: Decimal,
) -> None:
    try:
        servico_de_produtos.buscar_snapshot_do_produto(produto_id, data_inicio)
    except AppError:
        servico_de_produtos.criar_versao_de_preco(
            UUID(str(produto_id)),
            RequisicaoCriarVersaoDePreco(
                preco_venda=preco_venda,
                preco_custo=preco_custo,
                vigente_desde=data_inicio,
                motivo="Seed analytics retroativo",
            ),
        )


def _deduplicar_produtos(produtos: list[dict]) -> list[dict]:
    vistos: set[str] = set()
    saida: list[dict] = []
    for produto in produtos:
        produto_id = str(produto["id"])
        if produto_id in vistos:
            continue
        vistos.add(produto_id)
        saida.append(produto)
    return saida


def _selecionar_produtos_do_dia(
    requisicao: RequisicaoGerarVendasFake,
    produtos: list[dict],
    rng: Random,
) -> list[dict]:
    maximo = min(requisicao.produtos_por_dia_max, len(produtos))
    minimo = min(requisicao.produtos_por_dia_min, maximo)
    quantidade = rng.randint(minimo, maximo)
    return rng.sample(produtos, quantidade)


def _quantidade_produzida(
    requisicao: RequisicaoGerarVendasFake,
    data_venda: date,
    rng: Random,
) -> int:
    base = rng.randint(requisicao.quantidade_producao_min, requisicao.quantidade_producao_max)
    fator = Decimal("1.20") if data_venda.weekday() >= 5 else Decimal("1.00")
    return max(1, int(Decimal(base) * fator))


def _montar_itens_de_venda(
    requisicao: RequisicaoGerarVendasFake,
    produtos: list[dict],
    estoque: dict[str, int],
    rng: Random,
) -> list[RequisicaoItemVendido]:
    candidatos = [produto for produto in produtos if estoque.get(str(produto["id"]), 0) > 0]
    if not candidatos:
        return []
    quantidade_itens = rng.randint(requisicao.itens_por_venda_min, requisicao.itens_por_venda_max)
    selecionados = rng.sample(candidatos, min(quantidade_itens, len(candidatos)))
    itens: list[RequisicaoItemVendido] = []
    for produto in selecionados:
        produto_id = str(produto["id"])
        restante = estoque.get(produto_id, 0)
        if restante <= 0:
            continue
        maximo = min(requisicao.quantidade_item_venda_max, restante)
        minimo = min(requisicao.quantidade_item_venda_min, maximo)
        quantidade = rng.randint(minimo, maximo)
        estoque[produto_id] = restante - quantidade
        itens.append(RequisicaoItemVendido(produto_id=UUID(produto_id), quantidade=quantidade))
    return itens


def _horario_aleatorio(data_venda: date, rng: Random) -> datetime:
    return datetime.combine(
        data_venda,
        time(hour=rng.randint(6, 19), minute=rng.randint(0, 59), second=rng.randint(0, 59)),
        tzinfo=UTC,
    )


def _descrever_venda_seed(
    itens: list[RequisicaoItemVendido],
    produtos_usados: dict[str, dict],
) -> str:
    partes = []
    for item in itens:
        produto = produtos_usados.get(str(item.produto_id))
        nome = produto["nome"] if produto else str(item.produto_id)
        partes.append(f"{item.quantidade}x {nome}")
    return "Seed analytics: " + ", ".join(partes)


def _montar_observacao_abertura(
    *,
    marcador: str,
    lote_id: UUID,
    observacao_base: str | None,
    rng: Random,
) -> str:
    partes = [f"{marcador} lote {lote_id}", rng.choice(OBSERVACOES_DIA)]
    if observacao_base:
        partes.append(observacao_base)
    return ". ".join(partes)


def _montar_observacao_fechamento(
    *,
    requisicao: RequisicaoGerarVendasFake,
    lote_id: UUID,
    rng: Random,
    unidades_produzidas: int,
    unidades_vendidas: int,
) -> str:
    sobra = max(unidades_produzidas - unidades_vendidas, 0)
    return (
        f"{requisicao.marcador} lote {lote_id}. Fechamento simulado: "
        f"{rng.choice(OBSERVACOES_DIA)}. Produzidos {unidades_produzidas}, "
        f"vendidos {unidades_vendidas}, sobra estimada {sobra}."
    )
