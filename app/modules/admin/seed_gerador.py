"""Gerador puro da massa de vendas usada pelo endpoint administrativo.

Este modulo nao acessa o Supabase. Ele recebe produtos e snapshots de preco ja
resolvidos e devolve um lote completo para persistencia. A mesma ``seed``
produz as mesmas contagens, cenarios e decisoes de sobra.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from random import Random
from uuid import UUID, uuid4

from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake
from app.shared.linha_do_tempo import normalizar_tipo_evento_publico

OBSERVACOES_DIA = [
    "movimento forte no periodo da manha",
    "chuva reduziu o fluxo no fim do dia",
    "cliente pediu bastante item recheado",
    "produto tradicional teve giro acima do esperado",
    "fornada saiu mais tarde e concentrou as vendas",
    "demanda estavel para comparativo de historico",
    "promocao local aumentou o volume de unidades",
]

OBSERVACOES_ITEM = [
    "producao seed para teste de analytics",
    "volume simulado com variacao aleatoria",
    "fornada usada para historico fake",
]

CENARIOS = {
    "normal": {
        "fator_producao": (0.90, 1.10),
        "taxa_venda": (0.55, 0.82),
        "fator_vendas": (0.90, 1.10),
    },
    "alta_demanda": {
        "fator_producao": (0.95, 1.20),
        "taxa_venda": (0.80, 0.97),
        "fator_vendas": (1.10, 1.35),
    },
    "baixa_demanda": {
        "fator_producao": (0.85, 1.10),
        "taxa_venda": (0.25, 0.52),
        "fator_vendas": (0.55, 0.80),
    },
    "excesso_producao": {
        "fator_producao": (1.30, 1.70),
        "taxa_venda": (0.30, 0.58),
        "fator_vendas": (0.70, 1.00),
    },
    "esgotamento": {
        "fator_producao": (0.60, 0.88),
        "taxa_venda": (0.94, 1.00),
        "fator_vendas": (1.15, 1.45),
    },
}


def montar_lote(
    *,
    requisicao: RequisicaoGerarVendasFake,
    datas: list[date],
    produtos: list[dict],
    snapshots: dict[tuple[str, date], dict],
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str,
) -> dict:
    lote = _lote_vazio()
    produtos_por_id = {str(produto["id"]): produto for produto in produtos}
    cenarios = _planejar_cenarios(len(datas), rng)
    sobras_anteriores: dict[str, dict] = {}

    for data_venda, cenario in zip(datas, cenarios, strict=True):
        sobras_anteriores = _montar_dia(
            lote,
            requisicao=requisicao,
            data_venda=data_venda,
            cenario=cenario,
            produtos=produtos,
            produtos_por_id=produtos_por_id,
            snapshots=snapshots,
            sobras_anteriores=sobras_anteriores,
            rng=rng,
            lote_id=lote_id,
            seed=seed,
            usuario_id=usuario_id,
        )

    lote["total_unidades_sobrando"] = sum(dia["unidades_sobrando"] for dia in lote["dias_saida"])
    return lote


def _lote_vazio() -> dict:
    return {
        "dias_de_venda": [],
        "itens_producao": [],
        "vendas": [],
        "itens_venda": [],
        "decisoes_sobra": [],
        "eventos": [],
        "dias_saida": [],
        "produtos_usados": {},
        "total_vendas": 0,
        "total_itens_venda": 0,
        "total_unidades_produzidas": 0,
        "total_unidades_vendidas": 0,
        "total_vendas_canceladas": 0,
        "total_unidades_sobra_reaproveitadas": 0,
        "total_unidades_sobra_descartadas": 0,
        "total_unidades_sobrando": 0,
    }


def _planejar_cenarios(quantidade_dias: int, rng: Random) -> list[str]:
    """Espalha todos os cenarios antes de repeti-los para maximizar variedade."""
    nomes = list(CENARIOS)
    planejados: list[str] = []
    while len(planejados) < quantidade_dias:
        ciclo = nomes.copy()
        rng.shuffle(ciclo)
        planejados.extend(ciclo)
    return planejados[:quantidade_dias]


def _montar_dia(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    data_venda: date,
    cenario: str,
    produtos: list[dict],
    produtos_por_id: dict[str, dict],
    snapshots: dict[tuple[str, date], dict],
    sobras_anteriores: dict[str, dict],
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str,
) -> dict[str, dict]:
    dia_id = uuid4()
    abertura_em = _instante_do_dia(data_venda, 6, rng.randint(0, 45))
    fechamento_em = _instante_do_dia(data_venda, 20, rng.randint(0, 45))
    selecionados = _selecionar_produtos_do_dia(requisicao, produtos, rng)

    estoque, recebidas, reaproveitadas, descartadas = _decidir_sobras_anteriores(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        sobras_anteriores=sobras_anteriores,
        produtos_por_id=produtos_por_id,
        rng=rng,
        usuario_id=usuario_id,
        criado_em=abertura_em,
    )
    _abrir_dia(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        cenario=cenario,
        lote_id=lote_id,
        usuario_id=usuario_id,
        abertura_em=abertura_em,
        fechamento_em=fechamento_em,
        rng=rng,
    )
    unidades_produzidas = _produzir(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        cenario=cenario,
        selecionados=selecionados,
        snapshots=snapshots,
        estoque=estoque,
        rng=rng,
        usuario_id=usuario_id,
        criado_em=abertura_em,
    )
    resultado_vendas = _vender(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        cenario=cenario,
        produtos_por_id=produtos_por_id,
        snapshots=snapshots,
        estoque=estoque,
        rng=rng,
        lote_id=lote_id,
        seed=seed,
        usuario_id=usuario_id,
    )
    unidades_sobrando = sum(estoque.values())
    observacao = _fechar_dia(
        lote,
        requisicao=requisicao,
        dia_id=dia_id,
        data_venda=data_venda,
        cenario=cenario,
        lote_id=lote_id,
        unidades_produzidas=unidades_produzidas,
        unidades_vendidas=resultado_vendas["unidades_vendidas"],
        unidades_sobrando=unidades_sobrando,
        rng=rng,
        usuario_id=usuario_id,
        fechamento_em=fechamento_em,
    )

    dia_saida = {
        "id": dia_id,
        "data_venda": data_venda,
        "produtos_produzidos": len(selecionados),
        "vendas_criadas": resultado_vendas["vendas_criadas"],
        "itens_venda_criados": resultado_vendas["itens_criados"],
        "unidades_produzidas": unidades_produzidas,
        "unidades_vendidas": resultado_vendas["unidades_vendidas"],
        "vendas_canceladas": resultado_vendas["vendas_canceladas"],
        "cenario": cenario,
        "unidades_sobra_recebidas": recebidas,
        "unidades_sobra_reaproveitadas": reaproveitadas,
        "unidades_sobra_descartadas": descartadas,
        "unidades_sobrando": unidades_sobrando,
        "observacoes_fechamento": observacao,
    }
    lote["dias_saida"].append(dia_saida)
    lote["total_vendas"] += resultado_vendas["vendas_criadas"]
    lote["total_itens_venda"] += resultado_vendas["itens_criados"]
    lote["total_unidades_produzidas"] += unidades_produzidas
    lote["total_unidades_vendidas"] += resultado_vendas["unidades_vendidas"]
    lote["total_vendas_canceladas"] += resultado_vendas["vendas_canceladas"]
    lote["total_unidades_sobra_reaproveitadas"] += reaproveitadas
    lote["total_unidades_sobra_descartadas"] += descartadas

    return {
        produto_id: {
            "dia_id": dia_id,
            "produto": produtos_por_id[produto_id],
            "quantidade": quantidade,
        }
        for produto_id, quantidade in estoque.items()
        if quantidade > 0
    }


def _decidir_sobras_anteriores(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    sobras_anteriores: dict[str, dict],
    produtos_por_id: dict[str, dict],
    rng: Random,
    usuario_id: UUID | str,
    criado_em: datetime,
) -> tuple[dict[str, int], int, int, int]:
    estoque: dict[str, int] = {}
    recebidas = sum(item["quantidade"] for item in sobras_anteriores.values())
    reaproveitadas = 0
    descartadas = 0
    decisoes = []

    for produto_id, sobra in sorted(sobras_anteriores.items()):
        quantidade_sobra = sobra["quantidade"]
        if rng.random() <= requisicao.probabilidade_reaproveitar_sobra:
            percentual = rng.uniform(
                requisicao.percentual_reaproveitamento_min,
                requisicao.percentual_reaproveitamento_max,
            )
            quantidade_usada = min(
                quantidade_sobra,
                max(1, round(quantidade_sobra * percentual)),
            )
        else:
            quantidade_usada = 0
        quantidade_nao_usada = quantidade_sobra - quantidade_usada
        produto = produtos_por_id[produto_id]
        if quantidade_usada:
            estoque[produto_id] = quantidade_usada
            _registrar_produto_usado(lote, produto)
        reaproveitadas += quantidade_usada
        descartadas += quantidade_nao_usada
        decisoes.append(
            {
                "id": uuid4(),
                "dia_origem_id": sobra["dia_id"],
                "dia_destino_id": dia_id,
                "produto_id": produto["id"],
                "nome_produto_no_momento": produto["nome"],
                "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
                "quantidade_sobra_origem": quantidade_sobra,
                "quantidade_usada_hoje": quantidade_usada,
                "quantidade_nao_usada_hoje": quantidade_nao_usada,
                "observacoes": f"{requisicao.marcador} decisao automatica de sobra",
                "criado_em": criado_em,
            }
        )

    lote["decisoes_sobra"].extend(decisoes)
    if decisoes:
        lote["eventos"].append(
            _evento(
                tipo_evento="sobras_decididas",
                titulo="Sobras do dia anterior decididas",
                tipo_entidade="dia_de_venda",
                entidade_id=dia_id,
                dia_de_venda_id=dia_id,
                usuario_id=usuario_id,
                criado_em=criado_em,
                detalhes={
                    "origem": "seed_analytics",
                    "data_destino": data_venda.isoformat(),
                    "quantidade_recebida": recebidas,
                    "quantidade_reaproveitada": reaproveitadas,
                    "quantidade_descartada": descartadas,
                },
            )
        )
    return estoque, recebidas, reaproveitadas, descartadas


def _abrir_dia(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    cenario: str,
    lote_id: UUID,
    usuario_id: UUID | str,
    abertura_em: datetime,
    fechamento_em: datetime,
    rng: Random,
) -> None:
    observacao = _observacao_abertura(requisicao, lote_id, cenario, rng)
    lote["dias_de_venda"].append(
        {
            "id": dia_id,
            "data_venda": data_venda,
            "nome_local_no_momento": requisicao.nome_local,
            "observacoes": observacao,
            "situacao": "fechado" if requisicao.fechar_dias else "aberto",
            "aberto_em": abertura_em,
            "fechado_em": fechamento_em if requisicao.fechar_dias else None,
            "criado_em": abertura_em,
            "atualizado_em": fechamento_em if requisicao.fechar_dias else abertura_em,
            "usuario_id": usuario_id,
        }
    )
    lote["eventos"].append(
        _evento(
            tipo_evento="dia_de_venda_aberto",
            titulo=f"Dia aberto: {data_venda.isoformat()}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_id,
            dia_de_venda_id=dia_id,
            usuario_id=usuario_id,
            criado_em=abertura_em,
            detalhes={
                "nome_local": requisicao.nome_local,
                "lote_id": str(lote_id),
                "cenario": cenario,
                "origem": "seed_analytics",
            },
        )
    )


def _produzir(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    cenario: str,
    selecionados: list[dict],
    snapshots: dict[tuple[str, date], dict],
    estoque: dict[str, int],
    rng: Random,
    usuario_id: UUID | str,
    criado_em: datetime,
) -> int:
    unidades_produzidas = 0
    for produto in selecionados:
        snapshot = snapshots[(str(produto["id"]), data_venda)]
        preco = snapshot["preco"]
        quantidade = _quantidade_produzida(requisicao, data_venda, cenario, rng)
        item_id = uuid4()
        lote["itens_producao"].append(
            {
                "id": item_id,
                "dia_de_venda_id": dia_id,
                "produto_id": produto["id"],
                "nome_produto_no_momento": produto["nome"],
                "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
                "versao_preco_id": preco["id"],
                "preco_venda_unitario_no_momento": preco["preco_venda"],
                "preco_custo_unitario_no_momento": preco["preco_custo"],
                "quantidade_produzida": quantidade,
                "observacoes": rng.choice(OBSERVACOES_ITEM),
                "criado_em": criado_em,
                "atualizado_em": criado_em,
            }
        )
        produto_id = str(produto["id"])
        estoque[produto_id] = estoque.get(produto_id, 0) + quantidade
        unidades_produzidas += quantidade
        _registrar_produto_usado(lote, produto)
        lote["eventos"].append(
            _evento(
                tipo_evento="item_producao_adicionado",
                titulo=f"Producao adicionada: {produto['nome']}",
                tipo_entidade="item_producao",
                entidade_id=item_id,
                dia_de_venda_id=dia_id,
                usuario_id=usuario_id,
                criado_em=criado_em,
                detalhes={
                    "produto_id": produto["id"],
                    "quantidade_produzida": quantidade,
                    "cenario": cenario,
                    "origem": "seed_analytics",
                },
            )
        )
    return unidades_produzidas


def _vender(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    cenario: str,
    produtos_por_id: dict[str, dict],
    snapshots: dict[tuple[str, date], dict],
    estoque: dict[str, int],
    rng: Random,
    lote_id: UUID,
    seed: int,
    usuario_id: UUID | str,
) -> dict[str, int]:
    metas = _metas_de_venda(estoque, cenario, rng)
    quantidade_planejada = _quantidade_vendas_planejada(requisicao, cenario, rng)
    resultado = {
        "vendas_criadas": 0,
        "itens_criados": 0,
        "unidades_vendidas": 0,
        "vendas_canceladas": 0,
    }

    for _ in range(quantidade_planejada):
        itens = _planejar_itens_da_venda(requisicao, estoque, metas, rng)
        if not itens:
            break
        venda_id = uuid4()
        ocorrido_em = _horario_venda(data_venda, rng)
        cancelada = rng.random() < requisicao.taxa_cancelamento
        tipo_entrada = rng.choice(requisicao.tipos_entrada)
        linhas_itens = [
            _item_venda(
                venda_id=venda_id,
                dia_id=dia_id,
                produto=produtos_por_id[item["produto_id"]],
                quantidade=item["quantidade"],
                snapshot=snapshots[(item["produto_id"], data_venda)],
                criado_em=ocorrido_em,
            )
            for item in itens
        ]

        if not cancelada:
            for item in itens:
                produto_id = item["produto_id"]
                estoque[produto_id] -= item["quantidade"]
                metas[produto_id] -= item["quantidade"]
            resultado["unidades_vendidas"] += sum(item["quantidade"] for item in itens)
        else:
            resultado["vendas_canceladas"] += 1

        lote["vendas"].append(
            {
                "id": venda_id,
                "dia_de_venda_id": dia_id,
                "tipo_entrada": tipo_entrada,
                "texto_original": _descrever_venda(itens, produtos_por_id),
                "observacoes": f"{requisicao.marcador} venda simulada do lote {lote_id}",
                "ocorrido_em": ocorrido_em,
                "situacao": "cancelada" if cancelada else "ativa",
                "cancelado_em": ocorrido_em if cancelada else None,
                "motivo_cancelamento": "Cancelamento simulado para teste" if cancelada else None,
                "criado_em": ocorrido_em,
                "atualizado_em": ocorrido_em,
                "usuario_id": usuario_id,
            }
        )
        lote["itens_venda"].extend(linhas_itens)
        resultado["vendas_criadas"] += 1
        resultado["itens_criados"] += len(linhas_itens)
        lote["eventos"].append(
            _evento(
                tipo_evento="VENDA_REALIZADA",
                titulo="Venda registrada",
                tipo_entidade="venda",
                entidade_id=venda_id,
                dia_de_venda_id=dia_id,
                usuario_id=usuario_id,
                criado_em=ocorrido_em,
                detalhes={
                    "tipo_entrada": tipo_entrada,
                    "situacao": "cancelada" if cancelada else "ativa",
                    "origem": "seed_analytics",
                    "lote_id": str(lote_id),
                    "seed": seed,
                    "itens": [
                        {
                            "produto_id": item["produto_id"],
                            "quantidade": item["quantidade"],
                        }
                        for item in itens
                    ],
                },
            )
        )
        if cancelada:
            lote["eventos"].append(
                _evento(
                    tipo_evento="venda_cancelada",
                    titulo="Venda cancelada",
                    tipo_entidade="venda",
                    entidade_id=venda_id,
                    dia_de_venda_id=dia_id,
                    usuario_id=usuario_id,
                    criado_em=ocorrido_em,
                    detalhes={"origem": "seed_analytics", "lote_id": str(lote_id)},
                )
            )
    return resultado


def _fechar_dia(
    lote: dict,
    *,
    requisicao: RequisicaoGerarVendasFake,
    dia_id: UUID,
    data_venda: date,
    cenario: str,
    lote_id: UUID,
    unidades_produzidas: int,
    unidades_vendidas: int,
    unidades_sobrando: int,
    rng: Random,
    usuario_id: UUID | str,
    fechamento_em: datetime,
) -> str | None:
    if not requisicao.fechar_dias:
        return None
    observacao = (
        f"{requisicao.marcador} lote {lote_id}. Cenario {cenario}. "
        f"{rng.choice(OBSERVACOES_DIA)}. Produzidos {unidades_produzidas}, "
        f"vendidos {unidades_vendidas}, sobrando {unidades_sobrando}."
    )
    lote["dias_de_venda"][-1]["observacoes"] = observacao
    lote["eventos"].append(
        _evento(
            tipo_evento="dia_de_venda_fechado",
            titulo=f"Dia fechado: {data_venda.isoformat()}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_id,
            dia_de_venda_id=dia_id,
            usuario_id=usuario_id,
            criado_em=fechamento_em,
            detalhes={
                "lote_id": str(lote_id),
                "cenario": cenario,
                "origem": "seed_analytics",
            },
        )
    )
    return observacao


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
    cenario: str,
    rng: Random,
) -> int:
    base = rng.randint(requisicao.quantidade_producao_min, requisicao.quantidade_producao_max)
    minimo, maximo = CENARIOS[cenario]["fator_producao"]
    fator_cenario = Decimal(str(rng.uniform(minimo, maximo)))
    fator_semana = Decimal("1.18") if data_venda.weekday() >= 5 else Decimal("1.00")
    return max(1, round(Decimal(base) * fator_cenario * fator_semana))


def _metas_de_venda(estoque: dict[str, int], cenario: str, rng: Random) -> dict[str, int]:
    minimo, maximo = CENARIOS[cenario]["taxa_venda"]
    metas = {}
    for produto_id, disponivel in estoque.items():
        taxa = rng.uniform(minimo, maximo)
        meta = round(disponivel * taxa)
        if cenario == "esgotamento" and disponivel:
            meta = max(meta, disponivel - rng.randint(0, min(2, disponivel)))
        metas[produto_id] = min(disponivel, max(0, meta))
    return metas


def _quantidade_vendas_planejada(
    requisicao: RequisicaoGerarVendasFake,
    cenario: str,
    rng: Random,
) -> int:
    base = rng.randint(requisicao.vendas_por_dia_min, requisicao.vendas_por_dia_max)
    minimo, maximo = CENARIOS[cenario]["fator_vendas"]
    quantidade = round(base * rng.uniform(minimo, maximo))
    return min(requisicao.vendas_por_dia_max, max(requisicao.vendas_por_dia_min, quantidade))


def _planejar_itens_da_venda(
    requisicao: RequisicaoGerarVendasFake,
    estoque: dict[str, int],
    metas: dict[str, int],
    rng: Random,
) -> list[dict]:
    candidatos = [
        produto_id
        for produto_id, meta in metas.items()
        if meta > 0 and estoque.get(produto_id, 0) > 0
    ]
    if not candidatos:
        return []
    quantidade_itens = rng.randint(requisicao.itens_por_venda_min, requisicao.itens_por_venda_max)
    selecionados = rng.sample(candidatos, min(quantidade_itens, len(candidatos)))
    itens = []
    for produto_id in selecionados:
        maximo = min(
            requisicao.quantidade_item_venda_max,
            estoque[produto_id],
            metas[produto_id],
        )
        if maximo <= 0:
            continue
        minimo = min(requisicao.quantidade_item_venda_min, maximo)
        itens.append({"produto_id": produto_id, "quantidade": rng.randint(minimo, maximo)})
    return itens


def _item_venda(
    *,
    venda_id: UUID,
    dia_id: UUID,
    produto: dict,
    quantidade: int,
    snapshot: dict,
    criado_em: datetime,
) -> dict:
    preco = snapshot["preco"]
    preco_venda = Decimal(str(preco["preco_venda"]))
    preco_custo = Decimal(str(preco["preco_custo"]))
    return {
        "id": uuid4(),
        "venda_id": venda_id,
        "dia_de_venda_id": dia_id,
        "produto_id": produto["id"],
        "nome_produto_no_momento": produto["nome"],
        "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
        "versao_preco_id": preco["id"],
        "preco_venda_unitario_no_momento": preco_venda,
        "preco_custo_unitario_no_momento": preco_custo,
        "quantidade": quantidade,
        "valor_total_venda": preco_venda * quantidade,
        "valor_total_custo": preco_custo * quantidade,
        "criado_em": criado_em,
    }


def _evento(
    *,
    tipo_evento: str,
    titulo: str,
    tipo_entidade: str,
    entidade_id: UUID,
    dia_de_venda_id: UUID,
    usuario_id: UUID | str,
    criado_em: datetime,
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
        "criado_em": criado_em,
    }


def _registrar_produto_usado(lote: dict, produto: dict) -> None:
    lote["produtos_usados"][str(produto["id"])] = {
        "id": produto["id"],
        "nome": produto["nome"],
        "origem": produto.get("_origem_seed", "existente"),
    }


def _descrever_venda(itens: list[dict], produtos_por_id: dict[str, dict]) -> str:
    partes = [
        f"{item['quantidade']}x {produtos_por_id[item['produto_id']]['nome']}" for item in itens
    ]
    return "Seed analytics: " + ", ".join(partes)


def _observacao_abertura(
    requisicao: RequisicaoGerarVendasFake,
    lote_id: UUID,
    cenario: str,
    rng: Random,
) -> str:
    partes = [
        f"{requisicao.marcador} lote {lote_id}",
        f"cenario {cenario}",
        rng.choice(OBSERVACOES_DIA),
    ]
    if requisicao.observacao_base:
        partes.append(requisicao.observacao_base)
    return ". ".join(partes)


def _instante_do_dia(data_venda: date, hora: int, minuto: int) -> datetime:
    return datetime.combine(data_venda, time(hour=hora, minute=minuto), tzinfo=UTC)


def _horario_venda(data_venda: date, rng: Random) -> datetime:
    return datetime.combine(
        data_venda,
        time(hour=rng.randint(7, 19), minute=rng.randint(0, 59), second=rng.randint(0, 59)),
        tzinfo=UTC,
    )
