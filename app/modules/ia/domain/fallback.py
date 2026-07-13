"""Interpretador de comandos sem OpenAI (fallback) e normalizacao de intencao.

Recebe o texto do comando e o catalogo de produtos e devolve uma intencao
estruturada (acao + itens + pistas). Puro: nao acessa rede.
"""

import re
from decimal import Decimal, InvalidOperation

from app.modules.ia.domain.acoes import (
    ACAO_ABRIR_DIA_DE_VENDA,
    ACAO_CANCELAR_ITEM_VENDA,
    ACAO_CANCELAR_VENDA,
    ACAO_CRIAR_PRODUTO,
    ACAO_CRIAR_PRODUTOS,
    ACAO_DESCONHECIDO,
    ACAO_FECHAR_DIA_DE_VENDA,
    ACAO_REGISTRAR_PRODUCAO,
    ACAO_REGISTRAR_VENDA,
    ACOES_SUPORTADAS,
)
from app.modules.ia.domain.texto import (
    buscar_quantidade_antes,
    extrair_data_do_texto,
    extrair_uuid_do_texto,
    formatar_itens,
    normalizar,
    normalizar_confianca,
    normalizar_data,
    normalizar_quantidade,
    normalizar_texto_opcional,
    normalizar_uuid_str,
)
from app.modules.ia.domain.vocabulario import (
    PALAVRAS_DE_CANCELAMENTO,
    PALAVRAS_DE_VENDA,
    PALAVRAS_FORTES_DE_PRODUCAO,
    PALAVRAS_FRACAS_DE_PRODUCAO,
    PALAVRAS_IGNORADAS_DE_PRODUTO,
)


def interpretar_com_fallback(texto: str, produtos: list[dict]) -> dict:
    texto_normalizado = normalizar(texto)
    produto = interpretar_produto_com_fallback(texto, texto_normalizado)
    if produto is not None:
        return {
            "acao": ACAO_CRIAR_PRODUTO,
            "data_venda": extrair_data_do_texto(texto),
            "nome_local": None,
            "venda_id": extrair_uuid_do_texto(texto),
            "usar_ultima_venda": False,
            "motivo_cancelamento": None,
            "observacoes": None,
            "itens": [],
            "produto": produto,
            "produtos": [],
            "itens_nao_identificados": [],
            "mensagem_assistente": mensagem_inicial_da_acao(ACAO_CRIAR_PRODUTO, []),
        }

    itens = interpretar_itens_com_fallback(texto_normalizado, produtos)
    acao = detectar_acao_com_fallback(texto_normalizado, bool(itens))
    itens_nao_identificados = []
    acoes_com_produtos = {
        ACAO_REGISTRAR_VENDA,
        ACAO_REGISTRAR_PRODUCAO,
        ACAO_CANCELAR_ITEM_VENDA,
    }
    if acao in acoes_com_produtos and not itens:
        itens_nao_identificados.append(texto)
    if acao == ACAO_DESCONHECIDO and not itens:
        itens_nao_identificados.append(texto)

    return {
        "acao": acao,
        "data_venda": extrair_data_do_texto(texto),
        "nome_local": None,
        "venda_id": extrair_uuid_do_texto(texto),
        "usar_ultima_venda": "ultima" in texto_normalizado or "desfazer" in texto_normalizado,
        "motivo_cancelamento": "Cancelado via IA" if acao == ACAO_CANCELAR_VENDA else None,
        "observacoes": None,
        "itens": itens,
        "produto": None,
        "produtos": [],
        "itens_nao_identificados": itens_nao_identificados,
        "mensagem_assistente": mensagem_inicial_da_acao(acao, itens),
    }


def detectar_acao_com_fallback(texto_normalizado: str, tem_itens: bool) -> str:
    if texto_indica_cadastro_produto(texto_normalizado):
        return ACAO_CRIAR_PRODUTO
    if "fechar" in texto_normalizado and "dia" in texto_normalizado:
        return ACAO_FECHAR_DIA_DE_VENDA
    if "abrir" in texto_normalizado and "dia" in texto_normalizado:
        return ACAO_ABRIR_DIA_DE_VENDA
    if texto_indica_cancelamento(texto_normalizado):
        if tem_itens:
            return ACAO_CANCELAR_ITEM_VENDA
        return ACAO_CANCELAR_VENDA
    if texto_indica_producao(texto_normalizado):
        return ACAO_REGISTRAR_PRODUCAO
    if texto_indica_venda(texto_normalizado):
        return ACAO_REGISTRAR_VENDA
    return ACAO_REGISTRAR_VENDA if tem_itens else ACAO_DESCONHECIDO


def interpretar_itens_com_fallback(texto_normalizado: str, produtos: list[dict]) -> list[dict]:
    tokens = texto_normalizado.split()
    itens = []

    for produto in produtos:
        tokens_produto = [
            token
            for token in normalizar(produto["nome"]).split()
            if token not in PALAVRAS_IGNORADAS_DE_PRODUTO
        ]
        if not tokens_produto or not all(token in tokens for token in tokens_produto):
            continue
        primeira_posicao = min(tokens.index(token) for token in tokens_produto)
        quantidade = buscar_quantidade_antes(tokens, primeira_posicao)
        itens.append(
            {
                "produto_id": produto["id"],
                "nome_produto": produto["nome"],
                "quantidade": quantidade,
                "confianca": 0.65,
            }
        )

    return itens


def interpretar_produto_com_fallback(
    texto: str,
    texto_normalizado: str | None = None,
) -> dict | None:
    texto_normalizado = texto_normalizado or normalizar(texto)
    if not texto_indica_cadastro_produto(texto_normalizado):
        return None

    return {
        "nome": extrair_nome_produto_do_texto(texto),
        "descricao": None,
        "descricao_visual": None,
        "url_imagem_principal": None,
        "cor_botao": None,
        "ordem_exibicao": None,
        "preco_venda": extrair_preco_do_texto(texto),
        "preco_custo": None,
        "vigente_desde": extrair_data_do_texto(texto),
    }


def texto_indica_cadastro_produto(texto_normalizado: str) -> bool:
    tokens = set(texto_normalizado.split())
    verbos = {
        "cadastrar",
        "cadastre",
        "cadastra",
        "criar",
        "crie",
        "cria",
        "adicionar",
        "adicione",
        "adiciona",
        "incluir",
        "inclua",
        "inclui",
    }
    alvos = {"produto", "produtos", "item", "itens", "sabor", "sabores"}
    if not tokens & verbos:
        return bool({"produto", "item", "sabor"} & tokens and {"novo", "nova"} & tokens)
    if "dia" in tokens:
        return False
    if tokens & alvos or {"novo", "nova"} & tokens:
        return True
    menciona_venda_sem_preco = bool({"venda", "vendas"} & tokens) and not bool(
        {"preco", "valor"} & tokens
    )
    return not menciona_venda_sem_preco


def extrair_nome_produto_do_texto(texto: str) -> str | None:
    texto_sem_prefixo = re.sub(
        r"^\s*(?:cadastre|cadastra|cadastrar|crie|cria|criar|adicione|adiciona|"
        r"adicionar|inclua|inclui|incluir)\s+",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto_sem_prefixo = re.sub(
        r"^\s*(?:(?:um|uma|o|a)\s+)?(?:(?:novo|nova)\s+)?"
        r"(?:produto|item|sabor)?\s*(?:chamado|chamada|de nome)?\s*",
        "",
        texto_sem_prefixo,
        flags=re.IGNORECASE,
    )
    marcador_preco = re.search(
        r"\s+(?:por|a|pre[cç]o(?:\s+de\s+venda)?|valor|custa|custando|"
        r"vendendo\s+por|venda\s+por)\s+(?:r\$\s*)?\d",
        texto_sem_prefixo,
        flags=re.IGNORECASE,
    )
    if marcador_preco:
        texto_sem_prefixo = texto_sem_prefixo[: marcador_preco.start()]
    nome = re.sub(r"\s+", " ", texto_sem_prefixo.strip(" .,:;-"))
    return nome or None


def extrair_preco_do_texto(texto: str) -> Decimal | None:
    padroes = [
        r"r\$\s*(\d+(?:[,.]\d{1,2})?)",
        r"\b(?:por|a|pre[cç]o(?:\s+de\s+venda)?|valor|custa|custando|"
        r"vendendo\s+por|venda\s+por)\s*(?:r\$\s*)?(\d+(?:[,.]\d{1,2})?)",
        r"\b(\d+(?:[,.]\d{1,2})?)\s*reais?\b",
    ]
    for padrao in padroes:
        resultado = re.search(padrao, texto, flags=re.IGNORECASE)
        if resultado:
            return normalizar_decimal_monetario(resultado.group(1))
    return None


def normalizar_decimal_monetario(valor) -> Decimal | None:
    if valor is None:
        return None
    texto = str(valor).strip().replace(",", ".")
    try:
        decimal = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    if decimal < 0:
        return None
    return decimal.quantize(Decimal("0.01"))


def agrupar_itens_por_produto(itens: list[dict]) -> list[dict]:
    itens_por_produto = {}
    for item in itens:
        produto_id = str(item["produto_id"])
        existente = itens_por_produto.get(produto_id)
        if existente:
            existente["quantidade"] += item["quantidade"]
            existente["confianca"] = max(existente["confianca"], item["confianca"])
            continue
        itens_por_produto[produto_id] = dict(item)
    return list(itens_por_produto.values())


def corrigir_acao_pelo_texto(
    acao: str,
    texto_original: str | None,
    *,
    tem_itens: bool,
) -> str:
    if not texto_original:
        return acao

    texto_normalizado = normalizar(texto_original)
    if not texto_normalizado:
        return acao

    if "fechar" in texto_normalizado and "dia" in texto_normalizado:
        return ACAO_FECHAR_DIA_DE_VENDA
    if "abrir" in texto_normalizado and "dia" in texto_normalizado:
        return ACAO_ABRIR_DIA_DE_VENDA
    if texto_indica_cadastro_produto(texto_normalizado):
        return ACAO_CRIAR_PRODUTO
    if texto_indica_cancelamento(texto_normalizado):
        return ACAO_CANCELAR_ITEM_VENDA if tem_itens else ACAO_CANCELAR_VENDA

    indica_producao = texto_indica_producao(texto_normalizado)
    indica_venda = texto_indica_venda(texto_normalizado)
    if indica_producao and indica_venda:
        return ACAO_DESCONHECIDO
    if indica_producao:
        return ACAO_REGISTRAR_PRODUCAO
    if indica_venda:
        return ACAO_REGISTRAR_VENDA
    return acao


def texto_indica_cancelamento(texto_normalizado: str) -> bool:
    tokens = set(texto_normalizado.split())
    return bool(tokens & PALAVRAS_DE_CANCELAMENTO)


def texto_indica_producao(texto_normalizado: str) -> bool:
    tokens = set(texto_normalizado.split())
    if tokens & PALAVRAS_FORTES_DE_PRODUCAO:
        return True
    return bool(tokens & PALAVRAS_FRACAS_DE_PRODUCAO) and not texto_indica_venda(texto_normalizado)


def texto_indica_venda(texto_normalizado: str) -> bool:
    tokens = set(texto_normalizado.split())
    if tokens & PALAVRAS_DE_VENDA:
        return True
    if {"venda", "vendas"} & tokens:
        return not bool(tokens & PALAVRAS_FORTES_DE_PRODUCAO)
    return False


def normalizar_interpretacao(
    interpretacao: dict,
    produtos: list[dict],
    *,
    texto_original: str | None = None,
) -> dict:
    produtos_por_id = {str(produto["id"]): produto for produto in produtos}
    itens = []
    itens_nao_identificados = list(interpretacao.get("itens_nao_identificados") or [])
    for item in interpretacao.get("itens") or []:
        produto_id = str(item.get("produto_id") or "")
        produto = produtos_por_id.get(produto_id)
        if not produto:
            nome_nao_identificado = item.get("nome_produto") or produto_id
            if nome_nao_identificado:
                itens_nao_identificados.append(str(nome_nao_identificado))
            continue
        quantidade = normalizar_quantidade(item.get("quantidade"))
        if quantidade <= 0:
            itens_nao_identificados.append(produto["nome"])
            continue
        itens.append(
            {
                "produto_id": produto["id"],
                "nome_produto": produto["nome"],
                "quantidade": quantidade,
                "confianca": normalizar_confianca(item.get("confianca")),
            }
        )

    itens = agrupar_itens_por_produto(itens)

    acao = interpretacao.get("acao")
    if acao not in ACOES_SUPORTADAS:
        acao = ACAO_DESCONHECIDO
    acao = corrigir_acao_pelo_texto(acao, texto_original, tem_itens=bool(itens))

    return {
        "acao": acao,
        "data_venda": normalizar_data(interpretacao.get("data_venda")),
        "nome_local": normalizar_texto_opcional(interpretacao.get("nome_local")),
        "venda_id": normalizar_uuid_str(interpretacao.get("venda_id")),
        "usar_ultima_venda": bool(interpretacao.get("usar_ultima_venda")),
        "motivo_cancelamento": normalizar_texto_opcional(interpretacao.get("motivo_cancelamento")),
        "observacoes": normalizar_texto_opcional(interpretacao.get("observacoes")),
        "itens": itens,
        "produto": normalizar_produto_interpretado(interpretacao.get("produto")),
        "produtos": normalizar_produtos_interpretados(interpretacao.get("produtos")),
        "itens_nao_identificados": itens_nao_identificados,
        "mensagem_assistente": normalizar_texto_opcional(interpretacao.get("mensagem_assistente"))
        or mensagem_inicial_da_acao(acao, itens),
    }


def normalizar_produto_interpretado(produto: dict | None) -> dict | None:
    if not isinstance(produto, dict):
        return None
    return {
        "nome": normalizar_texto_opcional(produto.get("nome")),
        "descricao": normalizar_texto_opcional(produto.get("descricao")),
        "descricao_visual": normalizar_texto_opcional(produto.get("descricao_visual")),
        "url_imagem_principal": normalizar_texto_opcional(produto.get("url_imagem_principal")),
        "cor_botao": normalizar_texto_opcional(produto.get("cor_botao")),
        "ordem_exibicao": normalizar_inteiro_opcional(produto.get("ordem_exibicao")),
        "preco_venda": normalizar_decimal_monetario(produto.get("preco_venda")),
        "preco_custo": normalizar_decimal_monetario(produto.get("preco_custo")),
        "vigente_desde": normalizar_data(produto.get("vigente_desde")),
    }


def normalizar_produtos_interpretados(produtos: list[dict] | None) -> list[dict]:
    if not isinstance(produtos, list):
        return []
    normalizados = []
    for produto in produtos:
        normalizado = normalizar_produto_interpretado(produto)
        if normalizado:
            normalizados.append(normalizado)
    return normalizados


def normalizar_inteiro_opcional(valor) -> int | None:
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def mensagem_inicial_da_acao(acao: str, itens: list[dict]) -> str:
    if acao == ACAO_CRIAR_PRODUTO:
        return "Confira antes de cadastrar o produto."
    if acao == ACAO_CRIAR_PRODUTOS:
        return "Confira antes de cadastrar os produtos."
    if acao == ACAO_REGISTRAR_VENDA and itens:
        return f"Confira a venda: {formatar_itens(itens)}."
    if acao == ACAO_REGISTRAR_PRODUCAO and itens:
        return f"Confira a producao: {formatar_itens(itens)}."
    if acao == ACAO_CANCELAR_ITEM_VENDA and itens:
        return f"Confira os itens a cancelar: {formatar_itens(itens)}."
    if acao == ACAO_CANCELAR_VENDA:
        return "Confira antes de cancelar a venda."
    if acao == ACAO_ABRIR_DIA_DE_VENDA:
        return "Confira antes de abrir o dia de venda."
    if acao == ACAO_FECHAR_DIA_DE_VENDA:
        return "Confira antes de fechar o dia de venda."
    return "Nao consegui identificar uma acao segura nesse comando."


def comando_pede_ultima_venda(texto_original: str, interpretacao: dict) -> bool:
    if comando_menciona_cancelamento_por_valor(texto_original) or comando_parece_em_lote(
        texto_original
    ):
        return False

    texto = normalizar(texto_original)
    tokens = set(texto.split())
    pediu_ultima = bool({"ultima", "ultimo"} & tokens) and bool({"venda", "vendas"} & tokens)
    pediu_desfazer = bool({"desfazer", "desfaz", "desfaca"} & tokens)
    return pediu_ultima or pediu_desfazer


def mensagem_cancelamento_sem_alvo_claro(texto_original: str) -> str:
    if comando_menciona_cancelamento_por_valor(texto_original):
        return (
            "Entendi que voce quer cancelar vendas de R$ 0,00, mas nao vou escolher "
            "vendas por valor sozinho. Toque na venda certa ou diga: cancele a ultima venda."
        )
    if comando_parece_em_lote(texto_original):
        return (
            "Entendi que voce quer cancelar mais de uma venda, mas preciso fazer uma por vez. "
            "Toque na venda certa ou diga: cancele a ultima venda."
        )
    return (
        "Entendi que voce quer cancelar uma venda, mas preciso saber qual. "
        "Toque na venda certa ou diga: cancele a ultima venda."
    )


def comando_menciona_cancelamento_por_valor(texto_original: str) -> bool:
    texto = normalizar(texto_original)
    tokens = set(texto.split())
    menciona_zero = "zero" in tokens or "0" in tokens
    menciona_dinheiro = bool({"real", "reais", "r", "rs"} & tokens)
    if menciona_zero and menciona_dinheiro:
        return True
    return bool(
        re.search(
            r"\br\$\s*0(?:[,.]00)?\b|\b0(?:[,.]00)?\s*reais?\b|\bzero\s+reais?\b",
            texto_original,
            flags=re.IGNORECASE,
        )
    )


def comando_parece_em_lote(texto_original: str) -> bool:
    tokens = set(normalizar(texto_original).split())
    return bool({"vendas", "todas", "todos", "varias", "varios"} & tokens)
