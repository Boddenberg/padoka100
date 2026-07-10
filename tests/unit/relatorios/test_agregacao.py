from decimal import Decimal

from app.modules.relatorios.domain import agregacao


def _producao(produto_id, qtd, nome):
    return {
        "produto_id": produto_id,
        "nome_produto_no_momento": nome,
        "url_imagem_produto_no_momento": None,
        "quantidade_produzida": qtd,
    }


def _venda(produto_id, qtd, nome, total_venda, total_custo):
    return {
        "produto_id": produto_id,
        "nome_produto_no_momento": nome,
        "quantidade": qtd,
        "valor_total_venda": total_venda,
        "valor_total_custo": total_custo,
    }


def _decisao(produto_id, usada, descartada, nome):
    return {
        "produto_id": produto_id,
        "nome_produto_no_momento": nome,
        "quantidade_usada_hoje": usada,
        "quantidade_nao_usada_hoje": descartada,
    }


def test_resumo_producao_e_venda():
    produtos = agregacao.montar_resumos_dos_produtos(
        [_producao("p1", 10, "Pao")],
        [_venda("p1", 4, "Pao", "6.00", "2.40")],
        [],
    )
    (resumo,) = produtos
    assert resumo["quantidade_produzida"] == 10
    assert resumo["quantidade_disponivel"] == 10
    assert resumo["quantidade_vendida"] == 4
    assert resumo["quantidade_sobra"] == 6
    assert resumo["faturamento_bruto"] == Decimal("6.00")
    assert resumo["lucro_estimado"] == Decimal("3.60")
    assert resumo["esgotado"] is False


def test_produto_esgotado_quando_vende_tudo():
    produtos = agregacao.montar_resumos_dos_produtos(
        [_producao("p1", 5, "Pao")],
        [_venda("p1", 5, "Pao", "5.00", "2.00")],
        [],
    )
    assert produtos[0]["esgotado"] is True


def test_sobra_aproveitada_e_descartada_de_dia_anterior():
    produtos = agregacao.montar_resumos_dos_produtos(
        [],
        [],
        [_decisao("p2", usada=3, descartada=2, nome="Bolo")],
    )
    (resumo,) = produtos
    assert resumo["quantidade_sobra_aproveitada"] == 3
    assert resumo["quantidade_sobra_descartada"] == 2
    assert resumo["quantidade_disponivel"] == 3
    assert resumo["quantidade_sobra"] == 3


def test_produtos_ordenados_por_nome_e_filtra_inativos():
    produtos = agregacao.montar_resumos_dos_produtos(
        [_producao("p1", 5, "Zebra"), _producao("p2", 0, "Abelha")],
        [],
        [],
    )
    # 'Abelha' foi produzido 0 e nao vendeu -> nao participou -> excluido.
    assert [p["nome_produto"] for p in produtos] == ["Zebra"]


def test_somar_produtos_agrega_decimais():
    produtos = agregacao.montar_resumos_dos_produtos(
        [_producao("p1", 10, "Pao"), _producao("p2", 5, "Bolo")],
        [
            _venda("p1", 4, "Pao", "6.00", "2.40"),
            _venda("p2", 5, "Bolo", "25.00", "10.00"),
        ],
        [],
    )
    totais = agregacao.somar_produtos(produtos)
    assert totais["total_produzido"] == 15
    assert totais["total_vendido"] == 9
    assert totais["faturamento_bruto"] == Decimal("31.00")
    assert totais["lucro_estimado"] == Decimal("18.60")


def test_agrupar_por_chave():
    linhas = [
        {"dia": "a", "v": 1},
        {"dia": "a", "v": 2},
        {"dia": "b", "v": 3},
    ]
    grupos = agregacao.agrupar_por_chave(linhas, "dia")
    assert set(grupos) == {"a", "b"}
    assert len(grupos["a"]) == 2


def test_consolidar_resumos_leves_da_mesma_data_soma_aberturas():
    base = {
        "total_produzido": 5,
        "total_sobra_aproveitada": 0,
        "total_sobra_descartada": 0,
        "total_disponivel": 5,
        "total_vendido": 5,
        "total_sobra": 0,
        "faturamento_bruto": Decimal("10"),
        "custo_estimado": Decimal("4"),
        "lucro_estimado": Decimal("6"),
    }
    dia = "2026-01-01"
    ab1 = {"dia_de_venda_id": "d1", "data_venda": dia, "situacao": "fechado", **base}
    ab2 = {"dia_de_venda_id": "d2", "data_venda": dia, "situacao": "aberto", **base}
    consolidado = agregacao.consolidar_resumos_leves_da_mesma_data([ab1, ab2])
    assert consolidado["faturamento_bruto"] == Decimal("20")
    assert consolidado["situacao"] == "aberto"  # qualquer abertura aberta domina


def test_consolidar_resumos_leves_uma_abertura_retorna_ela_mesma():
    resumo = {"dia_de_venda_id": "d1", "data_venda": "2026-01-01", "situacao": "fechado"}
    assert agregacao.consolidar_resumos_leves_da_mesma_data([resumo]) is resumo
