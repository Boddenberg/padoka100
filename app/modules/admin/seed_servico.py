from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from random import Random
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import AppError, BadRequestError
from app.db.supabase import get_supabase_client
from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake
from app.modules.produtos import servico as servico_de_produtos
from app.modules.produtos.esquemas import RequisicaoCriarProduto, RequisicaoCriarVersaoDePreco
from app.modules.vendas.esquemas import RequisicaoItemVendido
from app.shared.db import to_db_payload
from app.shared.linha_do_tempo import normalizar_tipo_evento_publico

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


def gerar_vendas_fake(
    requisicao: RequisicaoGerarVendasFake,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    datas = _resolver_datas(requisicao)
    lote_id = uuid4()
    seed = requisicao.seed if requisicao.seed is not None else uuid4().int % 1_000_000_000
    rng = Random(seed)
    avisos: list[str] = []

    if requisicao.limpar_seed_anterior:
        removidos = _limpar_seed_anterior(datas, requisicao.marcador, usuario_id=usuario_id)
        if removidos:
            avisos.append(f"{removidos} dia(s) seed anterior removido(s) no periodo.")

    produtos = _resolver_produtos_para_seed(requisicao, datas, rng, avisos, usuario_id=usuario_id)
    if not produtos:
        raise BadRequestError("Nao ha produtos com preco vigente para gerar o historico fake.")

    lote = _montar_lote_seed(
        requisicao=requisicao,
        datas=datas,
        produtos=produtos,
        rng=rng,
        lote_id=lote_id,
        seed=seed,
        usuario_id=usuario_id,
    )
    client = get_supabase_client()
    _inserir_em_lotes(client, "dias_de_venda", lote["dias_de_venda"])
    _inserir_em_lotes(client, "itens_producao", lote["itens_producao"])
    _inserir_em_lotes(client, "vendas", lote["vendas"])
    _inserir_em_lotes(client, "itens_venda", lote["itens_venda"])
    _inserir_em_lotes(client, "eventos_linha_do_tempo", lote["eventos"])

    return {
        "lote_id": lote_id,
        "seed": seed,
        "periodo_inicio": min(datas),
        "periodo_fim": max(datas),
        "total_dias": len(lote["dias_saida"]),
        "total_vendas": lote["total_vendas"],
        "total_itens_venda": lote["total_itens_venda"],
        "total_unidades_produzidas": lote["total_unidades_produzidas"],
        "total_unidades_vendidas": lote["total_unidades_vendidas"],
        "produtos_usados": list(lote["produtos_usados"].values()),
        "dias": lote["dias_saida"],
        "avisos": avisos,
    }


def _montar_lote_seed(
    *,
    requisicao: RequisicaoGerarVendasFake,
    datas: list[date],
    produtos: list[dict],
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str | None = None,
) -> dict:
    lote = {
        "dias_de_venda": [],
        "itens_producao": [],
        "vendas": [],
        "itens_venda": [],
        "eventos": [],
        "dias_saida": [],
        "produtos_usados": {},
        "total_vendas": 0,
        "total_itens_venda": 0,
        "total_unidades_produzidas": 0,
        "total_unidades_vendidas": 0,
    }
    snapshots = _montar_snapshots_de_precos(produtos, datas)
    for data_venda in datas:
        _montar_dia_seed(
            lote,
            requisicao=requisicao,
            data_venda=data_venda,
            produtos=produtos,
            snapshots=snapshots,
            rng=rng,
            lote_id=lote_id,
            seed=seed,
            usuario_id=usuario_id,
        )
    return lote


def _montar_dia_seed(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    data_venda: date,
    produtos: list[dict],
    snapshots: dict,
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str | None = None,
) -> None:
    # A ordem das chamadas ao rng precisa ser estavel: a mesma seed deve
    # gerar exatamente o mesmo lote de dados fake.
    dia_id = uuid4()
    selecionados = _selecionar_produtos_do_dia(requisicao, produtos, rng)
    _abrir_dia_seed(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        rng=rng,
        lote_id=lote_id,
        usuario_id=usuario_id,
    )
    estoque, unidades_produzidas = _produzir_itens_do_dia_seed(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        selecionados=selecionados,
        snapshots=snapshots,
        rng=rng,
        usuario_id=usuario_id,
    )
    vendas_dia, itens_venda_dia, unidades_vendidas = _vender_itens_do_dia_seed(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        selecionados=selecionados,
        snapshots=snapshots,
        estoque=estoque,
        rng=rng,
        lote_id=lote_id,
        seed=seed,
        usuario_id=usuario_id,
    )
    observacao_fechamento = _fechar_dia_seed(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        rng=rng,
        lote_id=lote_id,
        unidades_produzidas=unidades_produzidas,
        unidades_vendidas=unidades_vendidas,
        usuario_id=usuario_id,
    )
    lote["dias_saida"].append(
        {
            "id": dia_id,
            "data_venda": data_venda,
            "produtos_produzidos": len(selecionados),
            "vendas_criadas": vendas_dia,
            "itens_venda_criados": itens_venda_dia,
            "unidades_produzidas": unidades_produzidas,
            "unidades_vendidas": unidades_vendidas,
            "observacoes_fechamento": observacao_fechamento,
        }
    )
    lote["total_vendas"] += vendas_dia
    lote["total_itens_venda"] += itens_venda_dia
    lote["total_unidades_produzidas"] += unidades_produzidas
    lote["total_unidades_vendidas"] += unidades_vendidas


def _abrir_dia_seed(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    rng: Random,
    lote_id: UUID,
    usuario_id: UUID | str | None = None,
) -> None:
    observacao_abertura = _montar_observacao_abertura(
        marcador=requisicao.marcador,
        lote_id=lote_id,
        observacao_base=requisicao.observacao_base,
        rng=rng,
    )
    lote["dias_de_venda"].append(
        {
            "id": dia_id,
            "data_venda": data_venda,
            "nome_local_no_momento": requisicao.nome_local,
            "observacoes": observacao_abertura,
            "situacao": "fechado" if requisicao.fechar_dias else "aberto",
            "fechado_em": datetime.now(UTC) if requisicao.fechar_dias else None,
            "usuario_id": usuario_id,
        }
    )
    lote["eventos"].append(
        _montar_evento_seed(
            tipo_evento="dia_de_venda_aberto",
            titulo=f"Dia aberto: {data_venda.isoformat()}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_id,
            dia_de_venda_id=dia_id,
            usuario_id=usuario_id,
            detalhes={"nome_local": requisicao.nome_local, "lote_id": str(lote_id)},
        )
    )


def _produzir_itens_do_dia_seed(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    selecionados: list[dict],
    snapshots: dict,
    rng: Random,
    usuario_id: UUID | str | None = None,
) -> tuple[dict[str, int], int]:
    estoque: dict[str, int] = {}
    unidades_produzidas = 0
    for produto in selecionados:
        snapshot = _buscar_snapshot(snapshots, produto["id"], data_venda)
        produto_linha = snapshot["produto"]
        preco = snapshot["preco"]
        quantidade = _quantidade_produzida(requisicao, data_venda, rng)
        item_id = uuid4()
        lote["itens_producao"].append(
            {
                "id": item_id,
                "dia_de_venda_id": dia_id,
                "produto_id": produto_linha["id"],
                "nome_produto_no_momento": produto_linha["nome"],
                "url_imagem_produto_no_momento": produto_linha.get("url_imagem_principal"),
                "versao_preco_id": preco["id"],
                "preco_venda_unitario_no_momento": preco["preco_venda"],
                "preco_custo_unitario_no_momento": preco["preco_custo"],
                "quantidade_produzida": quantidade,
                "observacoes": rng.choice(OBSERVACOES_ITEM),
            }
        )
        estoque[str(produto_linha["id"])] = quantidade
        unidades_produzidas += quantidade
        lote["produtos_usados"][str(produto_linha["id"])] = {
            "id": produto_linha["id"],
            "nome": produto_linha["nome"],
        }
        lote["eventos"].append(
            _montar_evento_seed(
                tipo_evento="item_producao_adicionado",
                titulo=f"Producao adicionada: {produto_linha['nome']}",
                tipo_entidade="item_producao",
                entidade_id=item_id,
                dia_de_venda_id=dia_id,
                usuario_id=usuario_id,
                detalhes={
                    "produto_id": produto_linha["id"],
                    "quantidade_produzida": quantidade,
                    "preco_venda_unitario_no_momento": preco["preco_venda"],
                    "origem": "seed_analytics",
                },
            )
        )
    return estoque, unidades_produzidas


def _vender_itens_do_dia_seed(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    selecionados: list[dict],
    snapshots: dict,
    estoque: dict[str, int],
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str | None = None,
) -> tuple[int, int, int]:
    vendas_dia = 0
    itens_venda_dia = 0
    unidades_vendidas = 0
    quantidade_vendas_planejada = rng.randint(
        requisicao.vendas_por_dia_min,
        requisicao.vendas_por_dia_max,
    )
    for _ in range(quantidade_vendas_planejada):
        itens = _montar_itens_de_venda(requisicao, selecionados, estoque, rng)
        if not itens:
            break
        venda_id = uuid4()
        ocorrido_em = _horario_aleatorio(data_venda, rng)
        venda_itens = [
            _montar_item_venda_seed(
                venda_id=venda_id,
                dia_de_venda_id=dia_id,
                item=item,
                snapshot=_buscar_snapshot(snapshots, str(item.produto_id), data_venda),
            )
            for item in itens
        ]
        lote["vendas"].append(
            {
                "id": venda_id,
                "dia_de_venda_id": dia_id,
                "tipo_entrada": "manual",
                "texto_original": _descrever_venda_seed(itens, lote["produtos_usados"]),
                "observacoes": f"{requisicao.marcador} venda simulada do lote {lote_id}",
                "ocorrido_em": ocorrido_em,
                "situacao": "ativa",
                "usuario_id": usuario_id,
            }
        )
        lote["itens_venda"].extend(venda_itens)
        vendas_dia += 1
        itens_venda_dia += len(venda_itens)
        unidades_vendidas += sum(item["quantidade"] for item in venda_itens)
        lote["eventos"].append(
            _montar_evento_seed(
                tipo_evento="VENDA_REALIZADA",
                titulo="Venda registrada",
                tipo_entidade="venda",
                entidade_id=venda_id,
                dia_de_venda_id=dia_id,
                usuario_id=usuario_id,
                detalhes={
                    "tipo_entrada": "manual",
                    "origem": "seed_analytics",
                    "lote_id": str(lote_id),
                    "seed": seed,
                    "itens": [
                        {
                            "produto_id": item["produto_id"],
                            "produto": item["nome_produto_no_momento"],
                            "quantidade": item["quantidade"],
                            "valor_total": item["valor_total_venda"],
                        }
                        for item in venda_itens
                    ],
                },
            )
        )
    return vendas_dia, itens_venda_dia, unidades_vendidas


def _fechar_dia_seed(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    rng: Random,
    lote_id: UUID,
    unidades_produzidas: int,
    unidades_vendidas: int,
    usuario_id: UUID | str | None = None,
) -> str | None:
    if not requisicao.fechar_dias:
        return None
    observacao_fechamento = _montar_observacao_fechamento(
        requisicao=requisicao,
        lote_id=lote_id,
        rng=rng,
        unidades_produzidas=unidades_produzidas,
        unidades_vendidas=unidades_vendidas,
    )
    lote["dias_de_venda"][-1]["observacoes"] = observacao_fechamento
    lote["eventos"].append(
        _montar_evento_seed(
            tipo_evento="dia_de_venda_fechado",
            titulo=f"Dia fechado: {data_venda.isoformat()}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_id,
            dia_de_venda_id=dia_id,
            usuario_id=usuario_id,
            detalhes={"lote_id": str(lote_id), "origem": "seed_analytics"},
        )
    )
    return observacao_fechamento


def _montar_snapshots_de_precos(
    produtos: list[dict],
    datas: list[date],
) -> dict[tuple[str, date], dict]:
    produto_por_id = {str(produto["id"]): produto for produto in produtos}
    versoes_por_produto = _listar_versoes_de_preco_para_periodo(
        list(produto_por_id),
        min(datas),
        max(datas),
    )
    snapshots: dict[tuple[str, date], dict] = {}
    for produto_id, produto in produto_por_id.items():
        versoes = versoes_por_produto.get(produto_id, [])
        for data_venda in datas:
            preco = _selecionar_preco_vigente(versoes, data_venda)
            if not preco:
                raise BadRequestError(
                    "Produto sem preco vigente para gerar historico fake.",
                    {"produto_id": produto_id, "data_venda": data_venda.isoformat()},
                )
            snapshots[(produto_id, data_venda)] = {"produto": produto, "preco": preco}
    return snapshots


def _buscar_snapshot(
    snapshots: dict[tuple[str, date], dict],
    produto_id: UUID | str,
    data_venda: date,
) -> dict:
    chave = (str(produto_id), data_venda)
    return snapshots[chave]


def _montar_item_venda_seed(
    *,
    venda_id: UUID,
    dia_de_venda_id: UUID,
    item: RequisicaoItemVendido,
    snapshot: dict,
) -> dict:
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    preco_venda = Decimal(str(preco["preco_venda"]))
    preco_custo = Decimal(str(preco["preco_custo"]))
    return {
        "id": uuid4(),
        "venda_id": venda_id,
        "dia_de_venda_id": dia_de_venda_id,
        "produto_id": item.produto_id,
        "nome_produto_no_momento": produto["nome"],
        "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
        "versao_preco_id": preco["id"],
        "preco_venda_unitario_no_momento": preco_venda,
        "preco_custo_unitario_no_momento": preco_custo,
        "quantidade": item.quantidade,
        "valor_total_venda": preco_venda * item.quantidade,
        "valor_total_custo": preco_custo * item.quantidade,
    }


def _montar_evento_seed(
    *,
    tipo_evento: str,
    titulo: str,
    tipo_entidade: str,
    entidade_id: UUID,
    dia_de_venda_id: UUID,
    usuario_id: UUID | str | None = None,
    detalhes: dict | None = None,
) -> dict:
    return {
        "dia_de_venda_id": dia_de_venda_id,
        "tipo_entidade": tipo_entidade,
        "entidade_id": entidade_id,
        "tipo_evento": normalizar_tipo_evento_publico(tipo_evento),
        "titulo": titulo,
        "detalhes": detalhes or {},
        "usuario_id": usuario_id,
    }


def _inserir_em_lotes(client, tabela: str, linhas: list[dict], *, tamanho_lote: int = 500) -> None:
    if not linhas:
        return
    for inicio in range(0, len(linhas), tamanho_lote):
        lote = linhas[inicio : inicio + tamanho_lote]
        client.table(tabela).insert([to_db_payload(linha) for linha in lote]).execute()


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


def _limpar_seed_anterior(
    datas: list[date],
    marcador: str,
    *,
    usuario_id: UUID | str | None = None,
) -> int:
    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("id")
        .gte("data_venda", min(datas).isoformat())
        .lte("data_venda", max(datas).isoformat())
        .ilike("observacoes", f"%{marcador}%")
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    linhas = consulta.execute().data
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
    *,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    produtos: list[dict] = []
    if requisicao.produto_ids:
        for produto_id in requisicao.produto_ids:
            produto = servico_de_produtos.buscar_produto(
                produto_id,
                data_preco=min(datas),
                usuario_id=usuario_id,
            )
            produtos.append(produto)
    else:
        produtos = servico_de_produtos.listar_produtos(
            somente_ativos=True,
            data_preco=min(datas),
            usuario_id=usuario_id,
        )

    produtos = _filtrar_produtos_com_preco_para_datas(produtos, datas, avisos)

    minimo_desejado = min(
        max(requisicao.produtos_por_dia_min, min(requisicao.produtos_por_dia_max, 4)),
        len(PRODUTOS_FAKE),
    )
    if len(produtos) < minimo_desejado and requisicao.criar_produtos_fake_se_necessario:
        faltantes = minimo_desejado - len(produtos)
        produtos.extend(_garantir_produtos_fake(datas, faltantes, rng, usuario_id=usuario_id))
        avisos.append(
            "Produtos seed foram criados/reutilizados para garantir preco vigente no periodo."
        )
    return _deduplicar_produtos(produtos)


def _filtrar_produtos_com_preco_para_datas(
    produtos: list[dict],
    datas: list[date],
    avisos: list[str],
) -> list[dict]:
    if not produtos:
        return []
    versoes_por_produto = _listar_versoes_de_preco_para_periodo(
        [str(produto["id"]) for produto in produtos],
        min(datas),
        max(datas),
    )
    produtos_validos = []
    for produto in produtos:
        versoes = versoes_por_produto.get(str(produto["id"]), [])
        if all(_selecionar_preco_vigente(versoes, data_alvo) for data_alvo in datas):
            produtos_validos.append(produto)
            continue
        avisos.append(f"Produto {produto['nome']} ignorado por falta de preco no periodo.")
    return produtos_validos


def _listar_versoes_de_preco_para_periodo(
    produto_ids: list[str],
    inicio: date,
    fim: date,
) -> dict[str, list[dict[str, Any]]]:
    if not produto_ids:
        return {}
    client = get_supabase_client()
    linhas = (
        client.table("versoes_preco_produto")
        .select("*")
        .in_("produto_id", produto_ids)
        .lte("vigente_desde", fim.isoformat())
        .or_(f"vigente_ate.is.null,vigente_ate.gte.{inicio.isoformat()}")
        .order("produto_id")
        .order("vigente_desde")
        .execute()
        .data
    )
    por_produto: dict[str, list[dict[str, Any]]] = {produto_id: [] for produto_id in produto_ids}
    for linha in linhas:
        por_produto.setdefault(str(linha["produto_id"]), []).append(linha)
    return por_produto


def _selecionar_preco_vigente(
    versoes: list[dict[str, Any]],
    data_alvo: date,
) -> dict[str, Any] | None:
    preco_vigente = None
    for versao in versoes:
        vigente_desde = _parse_data_db(versao["vigente_desde"])
        vigente_ate = versao.get("vigente_ate")
        if vigente_desde > data_alvo:
            continue
        if vigente_ate and _parse_data_db(vigente_ate) < data_alvo:
            continue
        if not preco_vigente or vigente_desde >= _parse_data_db(preco_vigente["vigente_desde"]):
            preco_vigente = versao
    return preco_vigente


def _parse_data_db(valor: date | str) -> date:
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(valor)


def _garantir_produtos_fake(
    datas: list[date],
    quantidade: int,
    rng: Random,
    *,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    client = get_supabase_client()
    consulta = (
        client.table("produtos")
        .select("*")
        .like("nome", "[Seed]%")
        .eq("situacao", "ativo")
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    existentes = consulta.execute().data
    por_nome = {produto["nome"]: produto for produto in existentes}
    specs = PRODUTOS_FAKE.copy()
    rng.shuffle(specs)
    produtos: list[dict] = []

    for nome, preco_venda, preco_custo in specs:
        if len(produtos) >= quantidade:
            break
        produto = por_nome.get(nome)
        if produto:
            _garantir_preco_seed(
                produto["id"],
                min(datas),
                preco_venda,
                preco_custo,
                usuario_id=usuario_id,
            )
            produtos.append(
                servico_de_produtos.buscar_produto(
                    UUID(produto["id"]),
                    data_preco=min(datas),
                    usuario_id=usuario_id,
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
            ),
            usuario_id=usuario_id,
        )
        produtos.append(criado)
    return produtos


def _garantir_preco_seed(
    produto_id: UUID | str,
    data_inicio: date,
    preco_venda: Decimal,
    preco_custo: Decimal,
    *,
    usuario_id: UUID | str | None = None,
) -> None:
    try:
        servico_de_produtos.buscar_snapshot_do_produto(
            produto_id,
            data_inicio,
            usuario_id=usuario_id,
        )
    except AppError:
        servico_de_produtos.criar_versao_de_preco(
            UUID(str(produto_id)),
            RequisicaoCriarVersaoDePreco(
                preco_venda=preco_venda,
                preco_custo=preco_custo,
                vigente_desde=data_inicio,
                motivo="Seed analytics retroativo",
            ),
            usuario_id=usuario_id,
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
