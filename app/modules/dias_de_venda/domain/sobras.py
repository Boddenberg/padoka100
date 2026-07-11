"""Calculo puro de sobras pendentes e montagem/validacao de decisoes de sobra.

Nao acessa Supabase: recebe as linhas ja carregadas e devolve estruturas
prontas para persistir. Assim toda a regra de sobra roda sem rede e e testavel.
"""

from app.core.errors import BadRequestError
from app.modules.dias_de_venda.esquemas import RequisicaoDecisaoSobra


def somar_sobras_ja_decididas_por_produto(decisoes_origem: list[dict]) -> dict[str, int]:
    totais_por_produto: dict[str, int] = {}
    for decisao in decisoes_origem:
        produto_id = decisao["produto_id"]
        totais_por_produto[produto_id] = (
            totais_por_produto.get(produto_id, 0) + decisao["quantidade_sobra_origem"]
        )
    return totais_por_produto


def calcular_sobras_pendentes(
    itens_producao: list[dict],
    itens_venda: list[dict],
    decisoes_sobra_usadas: list[dict],
    sobras_ja_decididas_por_produto: dict[str, int],
) -> list[dict]:
    vendidos_por_produto: dict[str, int] = {}
    for item in itens_venda:
        produto_id = item["produto_id"]
        vendidos_por_produto[produto_id] = (
            vendidos_por_produto.get(produto_id, 0) + item["quantidade"]
        )

    disponiveis_por_produto: dict[str, dict] = {}
    for item in itens_producao:
        produto_id = item["produto_id"]
        disponiveis_por_produto[produto_id] = {
            "produto_id": produto_id,
            "nome_produto": item["nome_produto_no_momento"],
            "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
            "quantidade_disponivel": item["quantidade_produzida"],
        }

    for decisao in decisoes_sobra_usadas:
        quantidade_usada = decisao["quantidade_usada_hoje"]
        if quantidade_usada <= 0:
            continue
        produto_id = decisao["produto_id"]
        if produto_id not in disponiveis_por_produto:
            disponiveis_por_produto[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": decisao["nome_produto_no_momento"],
                "url_imagem_produto": decisao.get("url_imagem_produto_no_momento"),
                "quantidade_disponivel": 0,
            }
        disponiveis_por_produto[produto_id]["quantidade_disponivel"] += quantidade_usada

    sobras = []
    for item in disponiveis_por_produto.values():
        quantidade_sobra = item["quantidade_disponivel"] - vendidos_por_produto.get(
            item["produto_id"],
            0,
        )
        quantidade_sobra -= sobras_ja_decididas_por_produto.get(item["produto_id"], 0)
        if quantidade_sobra <= 0:
            continue
        sobras.append(
            {
                "produto_id": item["produto_id"],
                "nome_produto": item["nome_produto"],
                "url_imagem_produto": item.get("url_imagem_produto"),
                "quantidade_sobra": quantidade_sobra,
                "quantidade_sugerida_para_usar": quantidade_sobra,
            }
        )
    return sorted(sobras, key=lambda item: item["nome_produto"])


def montar_linhas_decisoes_sobra(
    *,
    dia_origem: dict,
    dia_destino: dict,
    sobras_pendentes: list[dict],
    decisoes: list[RequisicaoDecisaoSobra],
) -> list[dict]:
    """Valida as decisoes contra as sobras pendentes e devolve as linhas a inserir.

    Somente itens explicitamente decididos entram no dia: produto pendente sem
    decisao recebe ``quantidade_usada_hoje = 0`` (sobra registrada como nao
    usada). A lista de sobras disponiveis nunca vira lista de consumo. Produto
    decidido que nao esta pendente continua sendo rejeitado.
    """
    if not decisoes:
        raise BadRequestError("Informe a decisao para cada sobra pendente.")

    sobras_por_produto = {sobra["produto_id"]: sobra for sobra in sobras_pendentes}
    decisoes_por_produto: dict[str, RequisicaoDecisaoSobra] = {}
    for decisao in decisoes:
        produto_id = str(decisao.produto_id)
        if produto_id in decisoes_por_produto:
            raise BadRequestError("Ha decisao de sobra repetida para o mesmo produto.")
        decisoes_por_produto[produto_id] = decisao

    produtos_extras = set(decisoes_por_produto) - set(sobras_por_produto)
    if produtos_extras:
        raise BadRequestError(
            "Ha decisao de sobra para produto sem sobra pendente.",
            {"produtos_sem_sobra_pendente": sorted(produtos_extras)},
        )

    linhas = []
    for produto_id, sobra in sobras_por_produto.items():
        decisao = decisoes_por_produto.get(produto_id)
        quantidade_sobra = sobra["quantidade_sobra"]
        if decisao is None:
            quantidade_usada = 0
            quantidade_nao_usada = quantidade_sobra
            observacoes = None
        else:
            quantidade_usada = decisao.quantidade_usada_hoje
            quantidade_nao_usada = decisao.quantidade_nao_usada_hoje
            observacoes = decisao.observacoes
            if quantidade_nao_usada is None:
                quantidade_nao_usada = quantidade_sobra - quantidade_usada
        if quantidade_nao_usada < 0:
            raise BadRequestError(
                "A quantidade usada hoje nao pode ser maior que a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                },
            )
        if quantidade_usada + quantidade_nao_usada != quantidade_sobra:
            raise BadRequestError(
                "A soma entre sobra usada hoje e nao usada hoje deve fechar a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                    "quantidade_nao_usada_hoje": quantidade_nao_usada,
                },
            )

        linhas.append(
            {
                "dia_origem_id": dia_origem["id"],
                "dia_destino_id": dia_destino["id"],
                "produto_id": produto_id,
                "nome_produto_no_momento": sobra["nome_produto"],
                "url_imagem_produto_no_momento": sobra.get("url_imagem_produto"),
                "quantidade_sobra_origem": quantidade_sobra,
                "quantidade_usada_hoje": quantidade_usada,
                "quantidade_nao_usada_hoje": quantidade_nao_usada,
                "observacoes": observacoes,
            }
        )
    return linhas
