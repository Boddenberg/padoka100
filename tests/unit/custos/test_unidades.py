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


def test_calcular_custo_por_unidade_nao_trava_com_unidade_desconhecida():
    # "fardo" nao esta na tabela: vale como 1 unidade/embalagem.
    assert unidades.calcular_custo_por_unidade(Decimal("30"), Decimal("3"), "fardo") == Decimal(
        "10.000000"
    )


def test_estimar_custo_ingrediente_mesmo_tipo_e_exato():
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("0.005"), Decimal("500"), "g", "kg", nome_ingrediente="farinha de trigo"
    )
    assert resultado["custo"] == Decimal("2.50")
    assert resultado["aproximado"] is False
    assert resultado["avisos"] == []


def test_estimar_custo_ingrediente_colher_de_sopa_contra_kg_usa_densidade():
    # R$5/kg de farinha => R$0,005/g. 1 colher de sopa = 15 ml x 0,55 g/ml = 8,25 g.
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("0.005"),
        Decimal("1"),
        "colher de sopa",
        "kg",
        nome_ingrediente="farinha de trigo",
    )
    assert resultado["custo"] == Decimal("0.04")
    assert resultado["quantidade_base"] == Decimal("8.250")
    assert resultado["unidade_base"] == "g"
    assert resultado["aproximado"] is True
    assert any("densidade" in aviso for aviso in resultado["avisos"])


def test_estimar_custo_ingrediente_massa_contra_litro_sem_densidade_conhecida():
    # R$8/l => R$0,008/ml. 200 g de "calda" (densidade padrao 1) = 200 ml.
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("0.008"), Decimal("200"), "g", "l", nome_ingrediente="calda"
    )
    assert resultado["custo"] == Decimal("1.60")
    assert resultado["aproximado"] is True
    assert any("1 g/ml" in aviso for aviso in resultado["avisos"])


def test_estimar_custo_ingrediente_ovos_contra_kg_usa_peso_tipico():
    # R$0,01/g. 3 ovos x 50 g = 150 g => R$1,50.
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("0.01"), Decimal("3"), "unidade", "kg", nome_ingrediente="ovos"
    )
    assert resultado["custo"] == Decimal("1.50")
    assert resultado["aproximado"] is True


def test_estimar_custo_ingrediente_uso_em_gramas_com_compra_por_embalagem():
    # Compra de 1 embalagem (R$5/un) sem equivalencia: assume 1 embalagem inteira.
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("5"), Decimal("300"), "g", "un", nome_ingrediente="calda especial"
    )
    assert resultado["custo"] == Decimal("5.00")
    assert resultado["aproximado"] is True
    assert any("embalagem" in aviso for aviso in resultado["avisos"])


def test_estimar_custo_ingrediente_unidade_desconhecida_nao_trava():
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("2"), Decimal("2"), "parsec", "un", nome_ingrediente="tempero"
    )
    assert resultado["custo"] == Decimal("4.00")
    assert resultado["aproximado"] is True
    assert any("nao reconhecida" in aviso for aviso in resultado["avisos"])


def test_estimar_custo_ingrediente_quantidade_invalida_vira_custo_zero():
    resultado = unidades.estimar_custo_ingrediente(
        Decimal("0.005"), Decimal("0"), "g", "kg", nome_ingrediente="farinha"
    )
    assert resultado["custo"] == Decimal("0.00")
    assert resultado["aproximado"] is True


def test_resolver_unidade_flexivel():
    assert unidades.resolver_unidade_flexivel("kg") == ("massa", Decimal("1000"), None)
    tipo, fator, aviso = unidades.resolver_unidade_flexivel("parsec")
    assert (tipo, fator) == ("unidade", Decimal("1"))
    assert "parsec" in aviso


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
