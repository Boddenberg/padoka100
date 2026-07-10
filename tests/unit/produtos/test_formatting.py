from app.modules.produtos.domain.formatting import formatar_produtos_para_lista_http

PRODUTO = {
    "id": "p1",
    "nome": "Pao Frances",
    "descricao": "quentinho",
    "url_imagem_principal": "http://img/1.png",
    "cor_botao": "#fff",
    "ordem_exibicao": 1,
    "situacao": "ativo",
    "preco_atual": {"preco_venda": "1.50", "preco_custo": "0.60", "origem": "manual"},
}


def test_lista_somente_ativos_expoe_campos_minimos():
    (item,) = formatar_produtos_para_lista_http([PRODUTO], somente_ativos=True)
    assert item == {
        "id": "p1",
        "nome": "Pao Frances",
        "url_imagem_principal": "http://img/1.png",
        "preco_atual": {"preco_venda": "1.50"},
    }


def test_lista_catalogo_completo_expoe_todos_os_campos():
    (item,) = formatar_produtos_para_lista_http([PRODUTO], somente_ativos=False)
    assert item["descricao"] == "quentinho"
    assert item["situacao"] == "ativo"
    assert item["preco_atual"] == {
        "preco_venda": "1.50",
        "preco_custo": "0.60",
        "origem": "manual",
    }


def test_lista_sem_preco_atual_retorna_none():
    produto = {**PRODUTO, "preco_atual": None}
    (ativo,) = formatar_produtos_para_lista_http([produto], somente_ativos=True)
    assert ativo["preco_atual"] is None
