"""Regras puras de ingrediente do assistente de custeio.

As regras de nome aqui sao propositalmente diferentes das de
``app.modules.custos.domain.ingredientes`` (insumos ja cadastrados): o
assistente ignora descritores de preparo (picado, moido...) que nao fazem
sentido para insumo persistido.
"""

import re
from decimal import Decimal

from app.modules.custos.assistant.valores import decimal_ou_none, normalizar_chave
from app.modules.custos.domain.status import consolidar_status as consolidar_status

STATUS_CUSTO_VALIDOS = {"CONFIRMADO", "ESTIMADO", "PENDENTE", "PRECISA_REVISAR"}
TIPOS_CUSTO_ADICIONAL = {"embalagem", "transporte", "indireto", "outro"}
APLICACOES_CUSTO = {"por_receita", "por_unidade"}
DESCRITORES_INGREDIENTE = {
    "branca",
    "brancas",
    "branco",
    "brancos",
    "especial",
    "especiais",
    "extra",
    "grande",
    "grandes",
    "iodada",
    "iodado",
    "ralado",
    "ralada",
    "refinada",
    "refinado",
    "picado",
    "picada",
    "fatiado",
    "fatiada",
    "moido",
    "moida",
    "triturado",
    "triturada",
    "tradicional",
    "tradicionais",
}
STOPWORDS_INGREDIENTE = {
    "a",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "o",
    "os",
    "ou",
    "para",
    "sem",
    "tipo",
}
INGREDIENTES_GENERICOS_PARA_MATCH = {"queijo"}


def status_de_custo(valor, *, padrao: str = "PENDENTE") -> str:
    status = str(valor or padrao).strip().upper()
    return status if status in STATUS_CUSTO_VALIDOS else padrao


def tipo_custo_adicional(valor) -> str:
    valor_normalizado = str(valor or "outro").strip().lower()
    return valor_normalizado if valor_normalizado in TIPOS_CUSTO_ADICIONAL else "outro"


def chave_ingrediente(item: dict) -> str:
    if item.get("insumo_id"):
        return f"id:{item['insumo_id']}"
    return f"nome:{normalizar_chave(item.get('nome') or '')}"


def chave_custo_adicional(item: dict) -> str:
    return f"{item.get('tipo') or 'outro'}:{normalizar_chave(item.get('nome') or '')}"


def nomes_ingredientes_compativeis(nome_a: str | None, nome_b: str | None) -> bool:
    if not nome_a or not nome_b:
        return False
    normalizado_a = normalizar_nome_ingrediente(nome_a)
    normalizado_b = normalizar_nome_ingrediente(nome_b)
    if not normalizado_a or not normalizado_b:
        return False
    if normalizado_a == normalizado_b:
        return True

    tokens_a = set(normalizado_a.split())
    tokens_b = set(normalizado_b.split())
    tokens_menores = tokens_a if len(tokens_a) <= len(tokens_b) else tokens_b
    tokens_maiores = tokens_b if len(tokens_a) <= len(tokens_b) else tokens_a
    if tokens_menores and tokens_menores <= tokens_maiores:
        return bool(tokens_menores - INGREDIENTES_GENERICOS_PARA_MATCH)

    if len(tokens_a) < 2 and len(tokens_b) < 2:
        return False
    comuns = tokens_a & tokens_b
    if not comuns:
        return False
    cobertura_menor = len(comuns) / min(len(tokens_a), len(tokens_b))
    cobertura_maior = len(comuns) / max(len(tokens_a), len(tokens_b))
    return cobertura_menor >= 0.75 and cobertura_maior >= 0.45


def normalizar_nome_ingrediente(nome: str) -> str:
    texto = normalizar_chave(nome)
    substituicoes = {
        "mucarela": "mussarela",
        "mozarela": "mussarela",
        "mozzarella": "mussarela",
        "ovos": "ovo",
        "queijos": "queijo",
    }
    tokens = []
    for token in texto.split():
        token = substituicoes.get(token, token)
        if token in STOPWORDS_INGREDIENTE or token in DESCRITORES_INGREDIENTE:
            continue
        tokens.append(token)
    return " ".join(tokens)


def escolher_nome_ingrediente(nome_atual: str | None, nome_novo: str | None) -> str | None:
    if not nome_atual:
        return nome_novo
    if not nome_novo:
        return nome_atual
    tokens_atual = set(normalizar_nome_ingrediente(nome_atual).split())
    tokens_novo = set(normalizar_nome_ingrediente(nome_novo).split())
    if len(tokens_novo) > len(tokens_atual):
        return nome_novo
    return nome_atual


def tem_dados_de_compra_completos(item: dict) -> bool:
    return (
        decimal_ou_none(item.get("quantidade_comprada")) is not None
        and bool(item.get("unidade_compra"))
        and decimal_ou_none(item.get("preco_total")) is not None
    )


def tem_algum_dado_de_compra(item: dict) -> bool:
    return any(
        item.get(chave) is not None
        for chave in ("quantidade_comprada", "unidade_compra", "preco_total")
    )


def texto_indica_quantidade_alternativa(valor) -> bool:
    if valor is None:
        return False
    texto = normalizar_chave(str(valor))
    return bool(
        re.search(r"\b(?:ou|ate)\b\s*\d", texto)
        or re.search(r"\d+(?:[,.]\d+)?\s*(?:ou|a|ate|-)\s*\d", texto)
    )


def extrair_numeros_de_texto(texto: str) -> list[Decimal]:
    numeros = []
    for match in re.finditer(r"(\d+)\s*/\s*(\d+)", texto):
        denominador = Decimal(match.group(2))
        if denominador:
            numeros.append(Decimal(match.group(1)) / denominador)
    numeros.extend(
        Decimal(match.group(1).replace(",", "."))
        for match in re.finditer(r"(\d+(?:[,.]\d+)?)", texto)
    )
    return numeros


def inferir_unidade_da_quantidade_ambigua(texto: str, ingrediente: dict) -> str | None:
    texto_normalizado = normalizar_chave(texto)
    for unidade in (
        "ovos",
        "ovo",
        "unidades",
        "unidade",
        "gramas",
        "g",
        "kg",
        "ml",
        "l",
        "copos",
        "copo",
        "xicaras",
        "xicara",
        "colheres de sopa",
        "colher de sopa",
        "colheres de cha",
        "colher de cha",
    ):
        if unidade in texto_normalizado:
            return unidade
    if "ovo" in normalizar_nome_ingrediente(ingrediente.get("nome") or ""):
        return "ovos"
    return ingrediente.get("unidade_usada")
