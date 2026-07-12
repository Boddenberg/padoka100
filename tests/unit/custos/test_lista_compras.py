from datetime import date
from decimal import Decimal
from uuid import UUID

from app.modules.custos import servico as servico_de_custos
from app.modules.custos.esquemas import ItemListaComprasProduto, RequisicaoGerarListaCompras

PRODUTO_ID = UUID("11111111-1111-1111-1111-111111111111")
RECEITA_ID = UUID("22222222-2222-2222-2222-222222222222")
INSUMO_ID = UUID("33333333-3333-3333-3333-333333333333")


def _preparar_lista(monkeypatch, ingrediente: dict, preco: dict) -> dict:
    monkeypatch.setattr(
        servico_de_custos.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {"id": str(PRODUTO_ID), "nome": "Pao de Queijo"},
    )
    monkeypatch.setattr(
        servico_de_custos,
        "_resolver_receita",
        lambda *args, **kwargs: {
            "id": str(RECEITA_ID),
            "produto_id": str(PRODUTO_ID),
            "rendimento": "10",
            "ingredientes": [ingrediente],
        },
    )
    monkeypatch.setattr(
        servico_de_custos,
        "buscar_insumo",
        lambda *args, **kwargs: {
            "id": str(INSUMO_ID),
            "nome": ingrediente["nome_insumo_no_momento"],
            "categoria": None,
        },
    )
    monkeypatch.setattr(
        servico_de_custos,
        "buscar_preco_vigente_insumo",
        lambda *args, **kwargs: preco,
    )

    return servico_de_custos.gerar_lista_compras(
        RequisicaoGerarListaCompras(
            itens=[ItemListaComprasProduto(produto_id=PRODUTO_ID, quantidade=Decimal("10"))],
            data_referencia=date(2026, 7, 11),
            salvar=False,
        )
    )


def test_lista_recalcula_custo_base_por_litro_sem_multiplicar_por_mil(monkeypatch):
    resposta = _preparar_lista(
        monkeypatch,
        {
            "insumo_id": str(INSUMO_ID),
            "nome_insumo_no_momento": "leite integral",
            "quantidade_usada": Decimal("250"),
            "unidade": "ml",
        },
        {
            "quantidade_comprada": Decimal("6"),
            "unidade_compra": "l",
            "preco_total": Decimal("32.94"),
            "custo_por_unidade": Decimal("5.490000"),
        },
    )

    (item,) = resposta["itens"]
    assert item["quantidade_base"] == Decimal("250.000")
    assert item["unidade_base"] == "ml"
    assert item["quantidade_sugerida"] == Decimal("250.000")
    assert item["unidade_sugerida"] == "ml"
    assert item["custo_unitario_base"] == Decimal("0.005490")
    assert item["custo_estimado"] == Decimal("1.37")


def test_lista_corrige_preco_antigo_salvo_como_unidade_generica(monkeypatch):
    resposta = _preparar_lista(
        monkeypatch,
        {
            "insumo_id": str(INSUMO_ID),
            "nome_insumo_no_momento": "leite integral",
            "quantidade_usada": Decimal("250"),
            "unidade": "ml",
            "observacoes": "Cupom mostra leite integral 3% TP 1L.",
        },
        {
            "quantidade_comprada": Decimal("6"),
            "unidade_compra": "un",
            "preco_total": Decimal("32.94"),
            "custo_por_unidade": Decimal("5.490000"),
        },
    )

    (item,) = resposta["itens"]
    assert item["quantidade_base"] == Decimal("250.000")
    assert item["unidade_base"] == "ml"
    assert item["custo_unitario_base"] == Decimal("0.005490")
    assert item["custo_estimado"] == Decimal("1.37")


def test_lista_usa_equivalencia_da_ia_quando_nao_ha_dado_deterministico(monkeypatch):
    from app.modules.custos import conversao_ia

    monkeypatch.setattr(
        conversao_ia,
        "_consultar_llm",
        lambda **kwargs: {"quantidade": 500, "unidade": "g", "confianca": 0.9},
    )
    resposta = _preparar_lista(
        monkeypatch,
        {
            "insumo_id": str(INSUMO_ID),
            "nome_insumo_no_momento": "mistura para pao caseiro",
            "quantidade_usada": Decimal("250"),
            "unidade": "g",
        },
        {
            "quantidade_comprada": Decimal("2"),
            "unidade_compra": "pacote",
            "preco_total": Decimal("20.00"),
            "custo_por_unidade": Decimal("10.00"),
        },
    )

    (item,) = resposta["itens"]
    # 2 pacotes de 500 g por R$ 20,00 => R$ 0,02/g; 250 g usados => R$ 5,00.
    assert item["custo_unitario_base"] == Decimal("0.020000")
    assert item["custo_estimado"] == Decimal("5.00")
    assert item["status"] == "ESTIMADO"
    assert "estimada por IA" in (item["observacoes"] or "")


def test_lista_nao_consulta_ia_quando_ha_equivalencia_explicita(monkeypatch):
    from app.modules.custos import conversao_ia

    def nao_pode_chamar(**kwargs):
        raise AssertionError("LLM nao deveria ser consultado com equivalencia explicita")

    monkeypatch.setattr(conversao_ia, "_consultar_llm", nao_pode_chamar)
    resposta = _preparar_lista(
        monkeypatch,
        {
            "insumo_id": str(INSUMO_ID),
            "nome_insumo_no_momento": "mistura para pao caseiro",
            "quantidade_usada": Decimal("250"),
            "unidade": "g",
            "observacoes": "Embalagem informada: 1 pacote de 500g.",
        },
        {
            "quantidade_comprada": Decimal("2"),
            "unidade_compra": "pacote",
            "preco_total": Decimal("20.00"),
            "custo_por_unidade": Decimal("10.00"),
        },
    )

    (item,) = resposta["itens"]
    assert item["custo_estimado"] == Decimal("5.00")


def test_lista_converte_pacote_da_receita_para_embalagem_com_equivalencia(monkeypatch):
    resposta = _preparar_lista(
        monkeypatch,
        {
            "insumo_id": str(INSUMO_ID),
            "nome_insumo_no_momento": "queijo ralado parmesao",
            "quantidade_usada": Decimal("1"),
            "unidade": "pacote",
        },
        {
            "quantidade_comprada": Decimal("2"),
            "unidade_compra": "100g",
            "preco_total": Decimal("15.98"),
            "custo_por_unidade": Decimal("0.079900"),
        },
    )

    (item,) = resposta["itens"]
    assert item["quantidade_base"] == Decimal("100.000")
    assert item["unidade_base"] == "g"
    assert item["quantidade_sugerida"] == Decimal("100.000")
    assert item["unidade_sugerida"] == "g"
    assert item["custo_estimado"] == Decimal("7.99")
    assert item["status"] == "ESTIMADO"
