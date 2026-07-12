from app.modules.custos import conversao_ia


def test_resposta_valida_vira_unidade_canonica(monkeypatch):
    monkeypatch.setattr(
        conversao_ia,
        "_consultar_llm",
        lambda **kwargs: {"quantidade": 395, "unidade": "g", "confianca": 0.9},
    )

    assert (
        conversao_ia.estimar_equivalencia_de_embalagem(
            nome="leite condensado",
            unidade_compra="lata",
        )
        == "395g"
    )


def test_resposta_invalida_ou_sem_confianca_e_descartada(monkeypatch):
    respostas_invalidas = (
        {"quantidade": None, "unidade": None, "confianca": 0.9},
        {"quantidade": 500, "unidade": "g", "confianca": 0.2},
        {"quantidade": -1, "unidade": "g", "confianca": 0.9},
        {"quantidade": 0, "unidade": "ml", "confianca": 0.9},
        {"quantidade": 500, "unidade": "kg", "confianca": 0.9},
        {"quantidade": 500, "unidade": "sacas", "confianca": 0.9},
        "texto solto",
    )
    for resposta in respostas_invalidas:
        conversao_ia.limpar_cache()
        monkeypatch.setattr(
            conversao_ia,
            "_consultar_llm",
            lambda resposta=resposta, **kwargs: resposta,
        )
        assert (
            conversao_ia.estimar_equivalencia_de_embalagem(
                nome="acucar cristal",
                unidade_compra="pacote",
            )
            is None
        ), f"resposta deveria ser descartada: {resposta!r}"


def test_falha_do_llm_nao_quebra_nem_cacheia(monkeypatch):
    chamadas = []

    def explode(**kwargs):
        chamadas.append(1)
        raise RuntimeError("rede fora")

    monkeypatch.setattr(conversao_ia, "_consultar_llm", explode)

    assert (
        conversao_ia.estimar_equivalencia_de_embalagem(
            nome="polvilho doce",
            unidade_compra="pacote",
        )
        is None
    )
    # Falha transitoria nao entra no cache: proxima chamada tenta de novo.
    conversao_ia.estimar_equivalencia_de_embalagem(
        nome="polvilho doce",
        unidade_compra="pacote",
    )
    assert len(chamadas) == 2


def test_resultado_e_cacheado_por_nome_e_embalagem(monkeypatch):
    chamadas = []

    def responde(**kwargs):
        chamadas.append(1)
        return {"quantidade": 1, "unidade": "kg", "confianca": 0.8}

    monkeypatch.setattr(conversao_ia, "_consultar_llm", responde)

    for _ in range(3):
        assert (
            conversao_ia.estimar_equivalencia_de_embalagem(
                nome="Farinha de Trigo Especial",
                unidade_compra="pacote",
            )
            == "1kg"
        )
    assert len(chamadas) == 1


def test_sem_nome_nao_consulta_llm(monkeypatch):
    def nao_pode_chamar(**kwargs):
        raise AssertionError("LLM nao deveria ser consultado sem nome de ingrediente")

    monkeypatch.setattr(conversao_ia, "_consultar_llm", nao_pode_chamar)

    assert (
        conversao_ia.estimar_equivalencia_de_embalagem(nome="  ", unidade_compra="pacote")
        is None
    )
