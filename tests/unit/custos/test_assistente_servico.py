from uuid import UUID

from app.modules.custos import assistente_servico

PRODUTO_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_estado_estima_custo_quando_unidades_sao_incompativeis(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Pao de Queijo",
            "preco_atual": {"preco_venda": "3.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Pao de Queijo", "rendimento": "30", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "calda especial",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                    "status": "CONFIRMADO",
                }
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    # Unidades incompativeis nao travam mais o custeio: o custo sai como
    # estimativa aproximada (1 embalagem inteira) com avisos para o usuario.
    assert estado["pendencias"] == []
    assert estado["situacao"] == "pronto_para_confirmar"
    (calda,) = estado["custo_simulado"]["ingredientes"]
    assert calda["calculo_estimado"] is True
    assert calda["custo_total_estimado"] == "5.00"
    assert estado["custo_simulado"]["calculo_aproximado"] is True
    assert any("embalagem" in aviso for aviso in estado["avisos"])
    assert any("estimativa aproximada" in aviso for aviso in estado["avisos"])


def test_estado_infere_embalagens_comuns_e_equivalencia_explicita(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Pao de Queijo",
            "preco_atual": {"preco_venda": "25.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Pao de Queijo", "rendimento": "30", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "leite integral",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                    "status": "CONFIRMADO",
                },
                {
                    "nome": "oleo",
                    "quantidade_usada": "0.5",
                    "unidade_usada": "copo",
                    "quantidade_comprada": "2",
                    "unidade_compra": "un",
                    "preco_total": "20",
                    "status": "CONFIRMADO",
                },
                {
                    "nome": "queijo ralado parmesao",
                    "quantidade_usada": "1",
                    "unidade_usada": "pacote",
                    "quantidade_comprada": "2",
                    "unidade_compra": "100g",
                    "preco_total": "10",
                    "status": "CONFIRMADO",
                },
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    assert estado["situacao"] == "pronto_para_confirmar"
    assert estado["pendencias"] == []
    leite, oleo, parmesao = estado["custo_simulado"]["ingredientes"]
    assert leite["unidade_compra_calculo"] == "1l"
    assert leite["calculo_estimado"] is True
    assert oleo["unidade_compra_calculo"] == "900ml"
    assert oleo["calculo_estimado"] is True
    assert parmesao["unidade_usada_calculo"] == "g"
    assert parmesao["quantidade_usada_calculo"] == "100"
    assert parmesao["unidade_compra_calculo"] == "100g"


def test_estado_converte_medida_caseira_para_massa_quando_compra_e_kg(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Bolo",
            "preco_atual": {"preco_venda": "10.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Bolo", "rendimento": "10", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "farinha de trigo",
                    "quantidade_usada": "2",
                    "unidade_usada": "xicara",
                    "quantidade_comprada": "1",
                    "unidade_compra": "kg",
                    "preco_total": "5",
                    "status": "CONFIRMADO",
                }
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    assert estado["pendencias"] == []
    (farinha,) = estado["custo_simulado"]["ingredientes"]
    assert farinha["quantidade_usada_calculo"] == "240"
    assert farinha["unidade_usada_calculo"] == "g"
    assert farinha["calculo_estimado"] is True


def test_consolidar_pendencia_legada_de_unidade_incompativel_nao_vira_compra_generica():
    pendencia = (
        "Ingrediente 1: leite integral: Unidade do ingrediente incompativel "
        "com a unidade de compra."
    )

    resultado = assistente_servico._consolidar_pendencias_para_fase(
        [pendencia],
        {
            "ingredientes": [
                {
                    "nome": "leite integral",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                }
            ]
        },
        fase="coletando_precos",
    )

    assert resultado == [pendencia]
