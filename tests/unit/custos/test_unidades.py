from decimal import Decimal

import pytest

from app.core.errors import BadRequestError
from app.modules.custos.domain import unidades


def test_resolver_unidade_base():
    assert unidades.resolver_unidade("kg") == ("massa", Decimal("1000"))
    assert unidades.resolver_unidade("g") == ("massa", Decimal("1"))
    assert unidades.resolver_unidade("ml") == ("volume", Decimal("1"))
    assert unidades.resolver_unidade("unidade") == ("unidade", Decimal("1"))


def test_resolver_unidade_com_equivalencia_informada():
    # "500g" e lido como massa de 500 gramas.
    assert unidades.resolver_unidade("500g") == ("massa", Decimal("500"))


def test_resolver_unidade_nao_suportada_levanta():
    with pytest.raises(BadRequestError):
        unidades.resolver_unidade("parsec")


def test_normalizar_unidade_trata_acento_e_caixa():
    assert unidades.normalizar_unidade("  Kg  ") == "kg"
    # "xicaras" ja e uma unidade base valida (volume/240), entao permanece.
    assert unidades.normalizar_unidade("Xícaras") == "xicaras"
    assert unidades.resolver_unidade("Xícaras") == ("volume", Decimal("240"))


def test_calcular_custo_por_unidade():
    # R$10 por 2 kg => R$0,005 por grama.
    assert unidades.calcular_custo_por_unidade(Decimal("10"), Decimal("2"), "kg") == Decimal(
        "0.005000"
    )


def test_calcular_custo_por_unidade_quantidade_zero():
    with pytest.raises(BadRequestError):
        unidades.calcular_custo_por_unidade(Decimal("10"), Decimal("0"), "kg")


def test_calcular_custo_ingrediente_compativel():
    custo = unidades.calcular_custo_ingrediente(Decimal("0.005"), Decimal("500"), "g", "kg")
    assert custo == Decimal("2.50")


def test_calcular_custo_ingrediente_incompativel_levanta():
    with pytest.raises(BadRequestError):
        unidades.calcular_custo_ingrediente(Decimal("0.005"), Decimal("500"), "ml", "kg")


def test_unidade_suportada():
    assert unidades.unidade_suportada("kg")
    assert not unidades.unidade_suportada("parsec")
    assert not unidades.unidade_suportada(None)


def test_descrever_unidade_aproximada():
    assert unidades.descrever_unidade_aproximada("xicara") == "xicara = 240 ml"
    assert unidades.descrever_unidade_aproximada("kg") is None


def test_formatar_quantidade_para_compra_promove_para_kg():
    assert unidades.formatar_quantidade_para_compra("massa", Decimal("1500")) == (
        "kg",
        Decimal("1.500"),
    )
    assert unidades.formatar_quantidade_para_compra("massa", Decimal("500")) == (
        "g",
        Decimal("500.000"),
    )


def test_arredondamentos():
    assert unidades.arredondar_moeda(Decimal("2.005")) == Decimal("2.01")
    assert unidades.arredondar_quantidade(Decimal("1.23456")) == Decimal("1.235")
