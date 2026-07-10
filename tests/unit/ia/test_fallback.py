from app.modules.ia.domain import fallback
from app.modules.ia.domain.acoes import (
    ACAO_ABRIR_DIA_DE_VENDA,
    ACAO_CANCELAR_VENDA,
    ACAO_DESCONHECIDO,
    ACAO_FECHAR_DIA_DE_VENDA,
    ACAO_REGISTRAR_PRODUCAO,
    ACAO_REGISTRAR_VENDA,
)

PRODUTOS = [
    {"id": "11111111-1111-1111-1111-111111111111", "nome": "Sonho"},
    {"id": "22222222-2222-2222-2222-222222222222", "nome": "Croissant"},
]


def test_fallback_venda_com_item_e_quantidade():
    resultado = fallback.interpretar_com_fallback("vendi 3 sonho", PRODUTOS)
    assert resultado["acao"] == ACAO_REGISTRAR_VENDA
    assert resultado["itens"][0]["nome_produto"] == "Sonho"
    assert resultado["itens"][0]["quantidade"] == 3


def test_fallback_producao():
    resultado = fallback.interpretar_com_fallback("produzi 5 croissant", PRODUTOS)
    assert resultado["acao"] == ACAO_REGISTRAR_PRODUCAO
    assert resultado["itens"][0]["quantidade"] == 5


def test_fallback_fechar_e_abrir_dia():
    assert fallback.interpretar_com_fallback("fechar o dia", PRODUTOS)["acao"] == (
        ACAO_FECHAR_DIA_DE_VENDA
    )
    assert fallback.interpretar_com_fallback("abrir o dia", PRODUTOS)["acao"] == (
        ACAO_ABRIR_DIA_DE_VENDA
    )


def test_fallback_cancelamento_sem_item():
    resultado = fallback.interpretar_com_fallback("cancelar a ultima venda", PRODUTOS)
    assert resultado["acao"] == ACAO_CANCELAR_VENDA
    assert resultado["usar_ultima_venda"] is True


def test_fallback_desconhecido_sem_item_e_sem_verbo():
    resultado = fallback.interpretar_com_fallback("bom dia pessoal", PRODUTOS)
    assert resultado["acao"] == ACAO_DESCONHECIDO
    assert resultado["itens"] == []
    assert resultado["itens_nao_identificados"]


def test_normalizar_interpretacao_marca_produto_desconhecido():
    interpretacao = {
        "acao": "registrar_venda",
        "itens": [
            {"produto_id": "99999999-9999-9999-9999-999999999999", "quantidade": 2},
            {"produto_id": "11111111-1111-1111-1111-111111111111", "quantidade": 3},
        ],
    }
    resultado = fallback.normalizar_interpretacao(interpretacao, PRODUTOS)
    assert len(resultado["itens"]) == 1
    assert resultado["itens"][0]["nome_produto"] == "Sonho"
    assert resultado["itens_nao_identificados"]  # o produto 999... entrou aqui


def test_normalizar_interpretacao_agrupa_itens_repetidos():
    interpretacao = {
        "acao": "registrar_venda",
        "itens": [
            {"produto_id": "11111111-1111-1111-1111-111111111111", "quantidade": 2},
            {"produto_id": "11111111-1111-1111-1111-111111111111", "quantidade": 3},
        ],
    }
    resultado = fallback.normalizar_interpretacao(interpretacao, PRODUTOS)
    assert len(resultado["itens"]) == 1
    assert resultado["itens"][0]["quantidade"] == 5


def test_comando_pede_ultima_venda():
    assert fallback.comando_pede_ultima_venda("cancele a ultima venda", {})
    assert not fallback.comando_pede_ultima_venda("cancele a venda de 0 reais", {})


def test_comando_menciona_cancelamento_por_valor():
    assert fallback.comando_menciona_cancelamento_por_valor("cancelar venda de 0 reais")
    assert fallback.comando_menciona_cancelamento_por_valor("estorno de R$ 0,00")
    assert not fallback.comando_menciona_cancelamento_por_valor("cancelar a ultima")
