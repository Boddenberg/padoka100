from app.modules.custos.assistant.rascunho import (
    equivalencia_explicita_na_unidade,
    mesclar_rascunhos,
    normalizar_ingrediente,
    normalizar_rascunho,
)


def test_normalizar_rascunho_vazio_tem_estrutura_completa():
    rascunho = normalizar_rascunho(None)
    assert rascunho["produto_id"] is None
    assert rascunho["receita"]["unidade_rendimento"] == "unidade"
    assert rascunho["receita"]["status"] == "PENDENTE"
    assert rascunho["ingredientes"] == []
    assert rascunho["custos_adicionais"] == []


def test_normalizar_rascunho_aceita_camel_case_e_aninhado():
    dados = {
        "rascunho": {
            "produtoId": "not-a-uuid",
            "receita": {"nome": " Pao ", "rendimento": "10,5"},
            "ingredientes": [{"nome": "farinha", "quantidade": "500", "unidade": "g"}],
        }
    }
    rascunho = normalizar_rascunho(dados)
    assert rascunho["produto_id"] is None  # uuid invalido vira None
    assert rascunho["receita"]["nome"] == "Pao"
    assert rascunho["receita"]["rendimento"] == "10.5"
    (ingrediente,) = rascunho["ingredientes"]
    assert ingrediente["quantidade_usada"] == "500"
    assert ingrediente["unidade_usada"] == "g"


def test_normalizar_rascunho_com_contexto_adiciona_fonte():
    rascunho = normalizar_rascunho({}, contexto="nota fiscal")
    assert rascunho["fontes"] == [{"tipo": "contexto", "texto": "nota fiscal"}]


def test_normalizar_ingrediente_quantidade_ambigua_escolhe_maior():
    item = normalizar_ingrediente({"nome": "ovo", "quantidade": "2 ou 3", "unidade": "ovos"})
    assert item["quantidade_usada"] == "3"
    assert item["quantidade_usada_ambigua"] is True
    assert item["unidade_usada"] == "ovos"


def test_equivalencia_explicita_na_unidade():
    equivalencia = equivalencia_explicita_na_unidade("pacote 5kg")
    assert equivalencia["unidade_base"] == "g"
    assert equivalencia["fator_base"] == 5000
    assert equivalencia_explicita_na_unidade("unidade") is None


def test_equivalencia_explicita_usa_primeira_medida_do_texto():
    equivalencia = equivalencia_explicita_na_unidade(
        "Cupom mostra leite integral TP 1L. Exemplo: 1 pacote = 1kg."
    )
    assert equivalencia["unidade_canonica"] == "1l"
    assert equivalencia["unidade_base"] == "ml"


def test_mesclar_rascunhos_preserva_receita_e_une_ingredientes():
    atual = {
        "produto_id": None,
        "receita": {"nome": "Pao", "rendimento": "10"},
        "ingredientes": [{"nome": "ovos", "quantidade_usada": "3", "unidade_usada": "ovos"}],
    }
    novo = {
        "ingredientes": [
            # nota de compra dos mesmos ovos: nao pode sobrescrever o uso da receita
            {
                "nome": "ovos grandes brancos",
                "quantidade_comprada": "30",
                "unidade_compra": "unidades",
                "preco_total": "25",
            },
            {"nome": "farinha", "quantidade_usada": "500", "unidade_usada": "g"},
        ]
    }
    resultado = mesclar_rascunhos(atual, novo)
    assert resultado["receita"]["nome"] == "Pao"
    assert len(resultado["ingredientes"]) == 2
    ovos = next(i for i in resultado["ingredientes"] if "ovo" in (i["nome"] or ""))
    # merge da nota mantem o nome e o uso da receita e agrega dados de compra
    assert ovos["nome"] == "ovos"
    assert ovos["quantidade_usada"] == "3"
    assert ovos["preco_total"] == "25"
