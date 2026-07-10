from app.modules.vendas.domain.availability import (
    calcular_quantidade_disponivel,
    calcular_quantidade_vendida,
    esgotou_com_a_venda,
)


def test_calcular_quantidade_disponivel_soma_producao_e_sobras():
    producao = [{"quantidade_produzida": 10}, {"quantidade_produzida": 5}]
    sobras = [{"quantidade_usada_hoje": 3}]
    assert calcular_quantidade_disponivel(producao, sobras) == 18


def test_calcular_quantidade_vendida_soma_itens():
    itens = [{"quantidade": 2}, {"quantidade": 4}]
    assert calcular_quantidade_vendida(itens) == 6


def test_esgotou_quando_venda_cruza_o_disponivel():
    assert esgotou_com_a_venda(
        quantidade_disponivel=10,
        quantidade_vendida_atual=10,
        quantidade_vendida_nesta_venda=3,
    )


def test_nao_esgota_quando_ja_estava_esgotado_antes():
    assert not esgotou_com_a_venda(
        quantidade_disponivel=10,
        quantidade_vendida_atual=13,
        quantidade_vendida_nesta_venda=1,
    )


def test_nao_esgota_quando_ainda_ha_disponivel():
    assert not esgotou_com_a_venda(
        quantidade_disponivel=10,
        quantidade_vendida_atual=8,
        quantidade_vendida_nesta_venda=3,
    )


def test_nao_esgota_quando_nao_havia_disponivel():
    assert not esgotou_com_a_venda(
        quantidade_disponivel=0,
        quantidade_vendida_atual=5,
        quantidade_vendida_nesta_venda=5,
    )
