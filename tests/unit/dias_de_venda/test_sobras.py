import pytest

from app.core.errors import BadRequestError
from app.modules.dias_de_venda.domain.sobras import (
    calcular_sobras_pendentes,
    montar_linhas_decisoes_sobra,
    somar_sobras_ja_decididas_por_produto,
)
from app.modules.dias_de_venda.esquemas import RequisicaoDecisaoSobra


def _producao(produto_id, qtd, nome="Pao"):
    return {
        "produto_id": produto_id,
        "quantidade_produzida": qtd,
        "nome_produto_no_momento": nome,
        "url_imagem_produto_no_momento": None,
    }


def test_sobra_e_producao_menos_vendas():
    producao = [_producao("p1", 10, "Pao")]
    itens_venda = [{"produto_id": "p1", "quantidade": 4}]
    sobras = calcular_sobras_pendentes(producao, itens_venda, [], {})
    assert len(sobras) == 1
    assert sobras[0]["quantidade_sobra"] == 6
    assert sobras[0]["quantidade_sugerida_para_usar"] == 6


def test_sem_sobra_quando_vendeu_tudo():
    producao = [_producao("p1", 10)]
    itens_venda = [{"produto_id": "p1", "quantidade": 10}]
    assert calcular_sobras_pendentes(producao, itens_venda, [], {}) == []


def test_sobras_ja_decididas_reduzem_o_pendente():
    producao = [_producao("p1", 10)]
    sobras = calcular_sobras_pendentes(producao, [], [], {"p1": 4})
    assert sobras[0]["quantidade_sobra"] == 6


def test_decisoes_usadas_hoje_somam_disponibilidade():
    decisoes_usadas = [
        {
            "produto_id": "p2",
            "quantidade_usada_hoje": 3,
            "nome_produto_no_momento": "Bolo",
            "url_imagem_produto_no_momento": None,
        }
    ]
    sobras = calcular_sobras_pendentes([], [], decisoes_usadas, {})
    assert sobras[0]["produto_id"] == "p2"
    assert sobras[0]["quantidade_sobra"] == 3


def test_sobras_ordenadas_por_nome():
    producao = [_producao("p1", 5, "Zebra"), _producao("p2", 5, "Abelha")]
    sobras = calcular_sobras_pendentes(producao, [], [], {})
    assert [s["nome_produto"] for s in sobras] == ["Abelha", "Zebra"]


def test_somar_sobras_ja_decididas_agrupa_por_produto():
    decisoes = [
        {"produto_id": "p1", "quantidade_sobra_origem": 3},
        {"produto_id": "p1", "quantidade_sobra_origem": 2},
        {"produto_id": "p2", "quantidade_sobra_origem": 5},
    ]
    assert somar_sobras_ja_decididas_por_produto(decisoes) == {"p1": 5, "p2": 5}


# --- montar_linhas_decisoes_sobra ---

DIA_ORIGEM = {"id": "origem"}
DIA_DESTINO = {"id": "destino"}
PID = "11111111-1111-1111-1111-111111111111"
OUTRO_PID = "22222222-2222-2222-2222-222222222222"
SOBRA = {
    "produto_id": PID,
    "nome_produto": "Pao",
    "quantidade_sobra": 10,
    "url_imagem_produto": None,
}


def _decisao(produto_id=PID, usada=6, nao_usada=None):
    return RequisicaoDecisaoSobra(
        produto_id=produto_id,
        quantidade_usada_hoje=usada,
        quantidade_nao_usada_hoje=nao_usada,
    )


def test_montar_linhas_infere_nao_usada():
    linhas = montar_linhas_decisoes_sobra(
        dia_origem=DIA_ORIGEM,
        dia_destino=DIA_DESTINO,
        sobras_pendentes=[SOBRA],
        decisoes=[_decisao(usada=6)],
    )
    assert linhas[0]["quantidade_usada_hoje"] == 6
    assert linhas[0]["quantidade_nao_usada_hoje"] == 4
    assert linhas[0]["dia_origem_id"] == "origem"
    assert linhas[0]["dia_destino_id"] == "destino"


def test_montar_linhas_exige_decisoes():
    with pytest.raises(BadRequestError):
        montar_linhas_decisoes_sobra(
            dia_origem=DIA_ORIGEM,
            dia_destino=DIA_DESTINO,
            sobras_pendentes=[SOBRA],
            decisoes=[],
        )


def test_montar_linhas_rejeita_decisao_para_produto_sem_sobra():
    with pytest.raises(BadRequestError):
        montar_linhas_decisoes_sobra(
            dia_origem=DIA_ORIGEM,
            dia_destino=DIA_DESTINO,
            sobras_pendentes=[SOBRA],
            decisoes=[_decisao(produto_id=OUTRO_PID)],
        )


def test_selecao_parcial_processa_somente_itens_selecionados():
    """Cenario do bug relatado: usuario seleciona so um item; os demais nao
    podem entrar no dia atual — a lista de disponiveis nao e lista de consumo."""
    sobra_nao_selecionada = {
        "produto_id": OUTRO_PID,
        "nome_produto": "Bolo",
        "quantidade_sobra": 7,
        "url_imagem_produto": None,
    }
    linhas = montar_linhas_decisoes_sobra(
        dia_origem=DIA_ORIGEM,
        dia_destino=DIA_DESTINO,
        sobras_pendentes=[SOBRA, sobra_nao_selecionada],
        decisoes=[_decisao(produto_id=PID, usada=3)],
    )

    por_produto = {linha["produto_id"]: linha for linha in linhas}
    assert por_produto[PID]["quantidade_usada_hoje"] == 3
    assert por_produto[PID]["quantidade_nao_usada_hoje"] == 7
    # O item nao selecionado fica registrado como decidido, mas nada dele
    # entra na disponibilidade do dia atual.
    assert por_produto[OUTRO_PID]["quantidade_usada_hoje"] == 0
    assert por_produto[OUTRO_PID]["quantidade_nao_usada_hoje"] == 7


def test_montar_linhas_rejeita_soma_incoerente():
    with pytest.raises(BadRequestError):
        montar_linhas_decisoes_sobra(
            dia_origem=DIA_ORIGEM,
            dia_destino=DIA_DESTINO,
            sobras_pendentes=[SOBRA],
            decisoes=[_decisao(usada=6, nao_usada=1)],  # 6 + 1 != 10
        )


def test_montar_linhas_rejeita_usada_maior_que_sobra():
    with pytest.raises(BadRequestError):
        montar_linhas_decisoes_sobra(
            dia_origem=DIA_ORIGEM,
            dia_destino=DIA_DESTINO,
            sobras_pendentes=[SOBRA],
            decisoes=[_decisao(usada=12)],  # nao_usada inferida = -2
        )
