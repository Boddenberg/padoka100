from decimal import Decimal

from app.modules.custos.assistant.ingredientes import (
    extrair_numeros_de_texto,
    inferir_unidade_da_quantidade_ambigua,
    nomes_ingredientes_compativeis,
    normalizar_nome_ingrediente,
    status_de_custo,
    tem_algum_dado_de_compra,
    tem_dados_de_compra_completos,
    texto_indica_quantidade_alternativa,
    tipo_custo_adicional,
)


def test_status_de_custo_normaliza_e_valida():
    assert status_de_custo("confirmado") == "CONFIRMADO"
    assert status_de_custo("invalido") == "PENDENTE"
    assert status_de_custo(None, padrao="ESTIMADO") == "ESTIMADO"


def test_tipo_custo_adicional_cai_para_outro():
    assert tipo_custo_adicional("Embalagem") == "embalagem"
    assert tipo_custo_adicional("gasolina") == "outro"
    assert tipo_custo_adicional(None) == "outro"


def test_nomes_compativeis_ignora_descritores_do_assistente():
    assert nomes_ingredientes_compativeis("ovos grandes brancos", "ovo")
    assert nomes_ingredientes_compativeis("sal iodado refinado", "sal")
    assert nomes_ingredientes_compativeis("queijo mussarela ralado", "queijo mussarela")


def test_nomes_nao_compativeis_por_termo_generico():
    # nomes identicos sempre casam, mesmo genericos...
    assert nomes_ingredientes_compativeis("queijo", "queijo")
    # ...mas "queijo" sozinho nao casa por subset com um queijo especifico
    assert not nomes_ingredientes_compativeis("queijo", "queijo mussarela")


def test_normalizar_nome_ingrediente_remove_preparo():
    assert normalizar_nome_ingrediente("cebola picada") == "cebola"
    assert normalizar_nome_ingrediente("carne moida especial") == "carne"


def test_texto_indica_quantidade_alternativa():
    assert texto_indica_quantidade_alternativa("2 ou 3 ovos")
    assert texto_indica_quantidade_alternativa("1 a 2 xicaras")
    assert not texto_indica_quantidade_alternativa("2 ovos")
    assert not texto_indica_quantidade_alternativa(None)


def test_extrair_numeros_de_texto_com_fracao():
    numeros = extrair_numeros_de_texto("1/2 ou 2")
    assert Decimal("0.5") in numeros
    assert Decimal("2") in numeros


def test_inferir_unidade_da_quantidade_ambigua():
    assert inferir_unidade_da_quantidade_ambigua("2 ou 3 xicaras", {}) == "xicaras"
    assert inferir_unidade_da_quantidade_ambigua("2 ou 3", {"nome": "ovos brancos"}) == "ovos"
    assert (
        inferir_unidade_da_quantidade_ambigua("2 ou 3", {"nome": "sal", "unidade_usada": "g"})
        == "g"
    )


def test_dados_de_compra():
    completo = {"quantidade_comprada": "1", "unidade_compra": "kg", "preco_total": "10"}
    assert tem_dados_de_compra_completos(completo)
    assert tem_algum_dado_de_compra({"preco_total": "5"})
    assert not tem_algum_dado_de_compra({"nome": "sal"})
