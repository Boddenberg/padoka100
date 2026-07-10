def formatar_produtos_para_lista_http(
    produtos: list[dict],
    *,
    somente_ativos: bool,
) -> list[dict]:
    if somente_ativos:
        return [_formatar_produto_ativo_para_lista(produto) for produto in produtos]
    return [_formatar_produto_catalogo_para_lista(produto) for produto in produtos]


def _formatar_produto_ativo_para_lista(produto: dict) -> dict:
    return {
        "id": produto["id"],
        "nome": produto["nome"],
        "url_imagem_principal": produto.get("url_imagem_principal"),
        "preco_atual": _formatar_preco_para_lista(produto.get("preco_atual"), ativo=True),
    }


def _formatar_produto_catalogo_para_lista(produto: dict) -> dict:
    return {
        "id": produto["id"],
        "nome": produto["nome"],
        "descricao": produto.get("descricao"),
        "url_imagem_principal": produto.get("url_imagem_principal"),
        "cor_botao": produto.get("cor_botao"),
        "ordem_exibicao": produto.get("ordem_exibicao"),
        "situacao": produto.get("situacao"),
        "preco_atual": _formatar_preco_para_lista(produto.get("preco_atual"), ativo=False),
    }


def _formatar_preco_para_lista(preco: dict | None, *, ativo: bool) -> dict | None:
    if not preco:
        return None
    if ativo:
        return {"preco_venda": preco.get("preco_venda")}
    return {
        "preco_venda": preco.get("preco_venda"),
        "preco_custo": preco.get("preco_custo"),
        "origem": preco.get("origem"),
    }
