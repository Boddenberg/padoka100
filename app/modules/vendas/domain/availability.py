def calcular_quantidade_disponivel(
    itens_producao: list[dict],
    decisoes_sobra: list[dict],
) -> int:
    return sum(item["quantidade_produzida"] for item in itens_producao) + sum(
        decisao["quantidade_usada_hoje"] for decisao in decisoes_sobra
    )


def calcular_quantidade_vendida(itens_venda: list[dict]) -> int:
    return sum(item["quantidade"] for item in itens_venda)


def esgotou_com_a_venda(
    *,
    quantidade_disponivel: int,
    quantidade_vendida_atual: int,
    quantidade_vendida_nesta_venda: int,
) -> bool:
    if quantidade_disponivel <= 0:
        return False
    quantidade_vendida_antes = quantidade_vendida_atual - quantidade_vendida_nesta_venda
    return quantidade_vendida_antes < quantidade_disponivel <= quantidade_vendida_atual
