from app.modules.dias_de_venda.domain.regras_dia import (
    dia_parece_seed_analytics,
    requisicao_indica_nova_abertura,
)
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCriarItemProducao,
    RequisicaoIniciarDiaDeVenda,
)

PRODUTO = "11111111-1111-1111-1111-111111111111"


def test_dia_parece_seed_analytics_detecta_marcadores():
    assert dia_parece_seed_analytics({"observacoes": "gerado pelo SEED analytics"})
    assert dia_parece_seed_analytics({"nome_local_no_momento": "loja seed_analytics"})


def test_dia_normal_nao_parece_seed():
    dia = {"observacoes": "dia normal", "nome_local_no_momento": "Loja"}
    assert not dia_parece_seed_analytics(dia)
    assert not dia_parece_seed_analytics({})


def test_nova_abertura_falsa_sem_dia_existente():
    req = RequisicaoIniciarDiaDeVenda(observacoes="algo")
    assert not requisicao_indica_nova_abertura(req, dia_atual_existente=None)


def test_nova_abertura_verdadeira_quando_ha_dados_e_dia_existente():
    req = RequisicaoIniciarDiaDeVenda(observacoes="reabrir")
    assert requisicao_indica_nova_abertura(req, dia_atual_existente={"id": "x"})


def test_nova_abertura_verdadeira_com_itens_producao():
    req = RequisicaoIniciarDiaDeVenda(
        itens_producao=[RequisicaoCriarItemProducao(produto_id=PRODUTO, quantidade_produzida=5)]
    )
    assert requisicao_indica_nova_abertura(req, dia_atual_existente={"id": "x"})


def test_nova_abertura_falsa_sem_dados_extras():
    req = RequisicaoIniciarDiaDeVenda()
    assert not requisicao_indica_nova_abertura(req, dia_atual_existente={"id": "x"})
