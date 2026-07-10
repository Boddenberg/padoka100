"""Conversao e custeio por unidade de medida (puro, sem rede).

Trata unidades base (massa/volume/unidade), equivalencias informadas no texto
(ex.: "1kg", "500 g") e unidades com ruido, alem do arredondamento monetario.
"""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import BadRequestError

UNIDADES_BASE = {
    "kg": ("massa", Decimal("1000")),
    "quilo": ("massa", Decimal("1000")),
    "quilos": ("massa", Decimal("1000")),
    "kilograma": ("massa", Decimal("1000")),
    "kilogramas": ("massa", Decimal("1000")),
    "g": ("massa", Decimal("1")),
    "grama": ("massa", Decimal("1")),
    "gramas": ("massa", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "lt": ("volume", Decimal("1000")),
    "litro": ("volume", Decimal("1000")),
    "litros": ("volume", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "mililitro": ("volume", Decimal("1")),
    "mililitros": ("volume", Decimal("1")),
    "copo": ("volume", Decimal("200")),
    "copos": ("volume", Decimal("200")),
    "copo americano": ("volume", Decimal("200")),
    "copos americanos": ("volume", Decimal("200")),
    "xicara": ("volume", Decimal("240")),
    "xicaras": ("volume", Decimal("240")),
    "colher sopa": ("volume", Decimal("15")),
    "colheres sopa": ("volume", Decimal("15")),
    "colher de sopa": ("volume", Decimal("15")),
    "colheres de sopa": ("volume", Decimal("15")),
    "colher cha": ("volume", Decimal("5")),
    "colheres cha": ("volume", Decimal("5")),
    "colher de cha": ("volume", Decimal("5")),
    "colheres de cha": ("volume", Decimal("5")),
    "prato cheio": ("massa", Decimal("350")),
    "pratos cheios": ("massa", Decimal("350")),
    "un": ("unidade", Decimal("1")),
    "und": ("unidade", Decimal("1")),
    "unidade": ("unidade", Decimal("1")),
    "unidades": ("unidade", Decimal("1")),
    "ovo": ("unidade", Decimal("1")),
    "ovos": ("unidade", Decimal("1")),
    "barra": ("unidade", Decimal("1")),
    "barras": ("unidade", Decimal("1")),
    "bisnaga": ("unidade", Decimal("1")),
    "bisnagas": ("unidade", Decimal("1")),
    "caixa": ("unidade", Decimal("1")),
    "caixas": ("unidade", Decimal("1")),
    "caixinha": ("unidade", Decimal("1")),
    "caixinhas": ("unidade", Decimal("1")),
    "cx": ("unidade", Decimal("1")),
    "dente": ("unidade", Decimal("1")),
    "dentes": ("unidade", Decimal("1")),
    "emb": ("unidade", Decimal("1")),
    "embalagem": ("unidade", Decimal("1")),
    "embalagens": ("unidade", Decimal("1")),
    "fatia": ("unidade", Decimal("1")),
    "fatias": ("unidade", Decimal("1")),
    "folha": ("unidade", Decimal("1")),
    "folhas": ("unidade", Decimal("1")),
    "frasco": ("unidade", Decimal("1")),
    "frascos": ("unidade", Decimal("1")),
    "frasquinho": ("unidade", Decimal("1")),
    "frasquinhos": ("unidade", Decimal("1")),
    "garrafa": ("unidade", Decimal("1")),
    "garrafas": ("unidade", Decimal("1")),
    "garrafinha": ("unidade", Decimal("1")),
    "garrafinhas": ("unidade", Decimal("1")),
    "lata": ("unidade", Decimal("1")),
    "latas": ("unidade", Decimal("1")),
    "latinha": ("unidade", Decimal("1")),
    "latinhas": ("unidade", Decimal("1")),
    "maco": ("unidade", Decimal("1")),
    "macos": ("unidade", Decimal("1")),
    "pacote": ("unidade", Decimal("1")),
    "pacotes": ("unidade", Decimal("1")),
    "pacotinho": ("unidade", Decimal("1")),
    "pacotinhos": ("unidade", Decimal("1")),
    "pitada": ("unidade", Decimal("1")),
    "pitadas": ("unidade", Decimal("1")),
    "porcao": ("unidade", Decimal("1")),
    "porcoes": ("unidade", Decimal("1")),
    "pct": ("unidade", Decimal("1")),
    "pcts": ("unidade", Decimal("1")),
    "pcte": ("unidade", Decimal("1")),
    "pote": ("unidade", Decimal("1")),
    "potes": ("unidade", Decimal("1")),
    "potinho": ("unidade", Decimal("1")),
    "potinhos": ("unidade", Decimal("1")),
    "punhado": ("unidade", Decimal("1")),
    "punhados": ("unidade", Decimal("1")),
    "ramo": ("unidade", Decimal("1")),
    "ramos": ("unidade", Decimal("1")),
    "rolo": ("unidade", Decimal("1")),
    "rolos": ("unidade", Decimal("1")),
    "sache": ("unidade", Decimal("1")),
    "saches": ("unidade", Decimal("1")),
    "saco": ("unidade", Decimal("1")),
    "sacos": ("unidade", Decimal("1")),
    "saquinho": ("unidade", Decimal("1")),
    "saquinhos": ("unidade", Decimal("1")),
    "tablete": ("unidade", Decimal("1")),
    "tabletes": ("unidade", Decimal("1")),
    "vidro": ("unidade", Decimal("1")),
    "vidros": ("unidade", Decimal("1")),
    "duzia": ("unidade", Decimal("12")),
    "duzias": ("unidade", Decimal("12")),
    "cartela": ("unidade", Decimal("30")),
    "cartelas": ("unidade", Decimal("30")),
    "cartela de ovos": ("unidade", Decimal("30")),
    "cartelas de ovos": ("unidade", Decimal("30")),
    "bandeja de ovos": ("unidade", Decimal("30")),
    "bandejas de ovos": ("unidade", Decimal("30")),
}

DESCRICOES_UNIDADES_APROXIMADAS = {
    "copo": "copo = 200 ml",
    "copos": "copo = 200 ml",
    "copo americano": "copo americano = 200 ml",
    "copos americanos": "copo americano = 200 ml",
    "xicara": "xicara = 240 ml",
    "xicaras": "xicara = 240 ml",
    "colher sopa": "colher de sopa = 15 ml",
    "colheres sopa": "colher de sopa = 15 ml",
    "colher de sopa": "colher de sopa = 15 ml",
    "colheres de sopa": "colher de sopa = 15 ml",
    "colher cha": "colher de cha = 5 ml",
    "colheres cha": "colher de cha = 5 ml",
    "colher de cha": "colher de cha = 5 ml",
    "colheres de cha": "colher de cha = 5 ml",
    "prato cheio": "prato cheio = 350 g",
    "pratos cheios": "prato cheio = 350 g",
    "duzia": "duzia = 12 unidades",
    "duzias": "duzia = 12 unidades",
    "cartela": "cartela = 30 unidades",
    "cartelas": "cartela = 30 unidades",
    "cartela de ovos": "cartela de ovos = 30 unidades",
    "cartelas de ovos": "cartela de ovos = 30 unidades",
    "bandeja de ovos": "bandeja de ovos = 30 unidades",
    "bandejas de ovos": "bandeja de ovos = 30 unidades",
}
PADROES_UNIDADES_COM_RUIDO = (
    (r"\bcolher(?:es)?\s*(?:de\s*)?sopa\b", "colher sopa"),
    (r"\bcolher(?:es)?\s*(?:de\s*)?cha\b", "colher cha"),
    (r"\bxicaras?\b", "xicara"),
    (r"\bcopos?\b", "copo"),
    (r"\bpratos?\s+cheios?\b", "prato cheio"),
    (r"\bcartelas?(?:\s+de\s+ovos)?\b", "cartela"),
    (r"\bbandejas?(?:\s+de\s+ovos)?\b", "bandeja de ovos"),
    (r"\bduzias?\b", "duzia"),
    (r"\b(?:pacote|pacotes|pacotinho|pacotinhos|pct|pcts|pcte)\b", "pacote"),
    (r"\b(?:saco|sacos|saquinho|saquinhos)\b", "saco"),
    (r"\b(?:sache|saches)\b", "sache"),
    (r"\b(?:caixa|caixas|caixinha|caixinhas|cx)\b", "caixa"),
    (r"\b(?:emb|embalagem|embalagens)\b", "embalagem"),
    (r"\b(?:frasco|frascos|frasquinho|frasquinhos)\b", "frasco"),
    (r"\b(?:garrafa|garrafas|garrafinha|garrafinhas)\b", "garrafa"),
    (r"\b(?:lata|latas|latinha|latinhas)\b", "lata"),
    (r"\b(?:pote|potes|potinho|potinhos)\b", "pote"),
    (r"\b(?:barra|barras)\b", "barra"),
    (r"\b(?:tablete|tabletes)\b", "tablete"),
    (r"\b(?:bisnaga|bisnagas)\b", "bisnaga"),
    (r"\b(?:vidro|vidros)\b", "vidro"),
    (r"\b(?:rolo|rolos)\b", "rolo"),
    (r"\b(?:fatia|fatias)\b", "fatia"),
    (r"\b(?:maco|macos)\b", "maco"),
    (r"\b(?:ramo|ramos)\b", "ramo"),
    (r"\b(?:folha|folhas)\b", "folha"),
    (r"\b(?:dente|dentes)\b", "dente"),
    (r"\b(?:pitada|pitadas)\b", "pitada"),
    (r"\b(?:punhado|punhados)\b", "punhado"),
    (r"\b(?:porcao|porcoes)\b", "porcao"),
    (r"\b(?:un|und|unidades?|ovos?)\b", "unidade"),
    (r"\b(?:kg|quilo|quilos|kilograma|kilogramas)\b", "kg"),
    (r"\b(?:g|grama|gramas)\b", "g"),
    (r"\b(?:ml|mililitro|mililitros)\b", "ml"),
    (r"\b(?:l|lt|litro|litros)\b", "l"),
)


def calcular_custo_por_unidade(
    preco_total: Decimal,
    quantidade: Decimal,
    unidade: str,
) -> Decimal:
    _, fator = resolver_unidade(unidade)
    quantidade_base = Decimal(str(quantidade)) * fator
    if quantidade_base <= 0:
        raise BadRequestError("Quantidade comprada precisa ser maior que zero.")
    return arredondar_custo_unitario(Decimal(str(preco_total)) / quantidade_base)


def calcular_custo_ingrediente(
    custo_unitario_base: Decimal,
    quantidade_usada: Decimal,
    unidade_usada: str,
    unidade_compra: str,
) -> Decimal:
    tipo_compra, _ = resolver_unidade(unidade_compra)
    tipo_usado, fator_usado = resolver_unidade(unidade_usada)
    if tipo_compra != tipo_usado:
        raise BadRequestError(
            "Unidade do ingrediente incompativel com a unidade de compra.",
            {"unidade_compra": unidade_compra, "unidade_usada": unidade_usada},
        )
    quantidade_base = Decimal(str(quantidade_usada)) * fator_usado
    return arredondar_moeda(custo_unitario_base * quantidade_base)


def resolver_unidade(unidade: str) -> tuple[str, Decimal]:
    unidade_normalizada = normalizar_unidade(unidade)
    unidade_com_equivalencia = resolver_unidade_com_equivalencia_informada(unidade_normalizada)
    if unidade_com_equivalencia:
        return unidade_com_equivalencia
    if unidade_normalizada not in UNIDADES_BASE:
        raise BadRequestError("Unidade de medida ainda nao suportada.", {"unidade": unidade})
    return UNIDADES_BASE[unidade_normalizada]


def normalizar_unidade(unidade: str) -> str:
    texto = unicodedata.normalize("NFKD", str(unidade).strip().lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    unidade_normalizada = re.sub(r"[^a-z0-9]+", " ", texto).strip()
    unidade_com_equivalencia = normalizar_unidade_com_equivalencia_informada(unidade_normalizada)
    if unidade_com_equivalencia:
        return unidade_com_equivalencia
    return extrair_unidade_de_texto_com_ruido(unidade_normalizada) or unidade_normalizada


def normalizar_unidade_com_equivalencia_informada(unidade_normalizada: str) -> str | None:
    if unidade_indica_quantidade_alternativa(unidade_normalizada):
        return None
    padroes = (
        (r"(\d+(?:[,.]\d+)?)\s*(kg|quilo|quilos|kilograma|kilogramas)\b", "kg"),
        (r"(\d+(?:[,.]\d+)?)\s*(g|grama|gramas)\b", "g"),
        (r"(\d+(?:[,.]\d+)?)\s*(ml|mililitro|mililitros)\b", "ml"),
        (r"(\d+(?:[,.]\d+)?)\s*(l|lt|litro|litros)\b", "l"),
        (r"(\d+(?:[,.]\d+)?)\s*(un|und|unidade|unidades)\b", "unidade"),
        (r"(\d+(?:[,.]\d+)?)\s*(ovo|ovos)\b", "ovos"),
    )
    for padrao, unidade in padroes:
        match = re.search(padrao, unidade_normalizada)
        if match:
            quantidade = Decimal(match.group(1).replace(",", "."))
            return f"{decimal_unidade_str(quantidade)}{unidade}"
    return None


def decimal_unidade_str(valor: Decimal) -> str:
    texto = format(valor.normalize(), "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def extrair_unidade_de_texto_com_ruido(texto: str) -> str | None:
    if not texto or texto in UNIDADES_BASE:
        return texto or None
    texto_sem_quantidade = re.sub(r"^\d+(?:[,.]\d+)?\s*", "", texto).strip()
    if texto_sem_quantidade in UNIDADES_BASE:
        return texto_sem_quantidade
    for padrao, unidade in PADROES_UNIDADES_COM_RUIDO:
        if re.search(padrao, texto_sem_quantidade):
            return unidade
    return None


def unidade_base_para_tipo(tipo_unidade: str) -> str:
    if tipo_unidade == "massa":
        return "g"
    if tipo_unidade == "volume":
        return "ml"
    return "unidade"


def formatar_quantidade_para_compra(
    tipo_unidade: str,
    quantidade_base: Decimal,
) -> tuple[str, Decimal]:
    quantidade = Decimal(str(quantidade_base))
    if tipo_unidade == "massa" and quantidade >= Decimal("1000"):
        return "kg", arredondar_quantidade(quantidade / Decimal("1000"))
    if tipo_unidade == "volume" and quantidade >= Decimal("1000"):
        return "l", arredondar_quantidade(quantidade / Decimal("1000"))
    return unidade_base_para_tipo(tipo_unidade), arredondar_quantidade(quantidade)


def resolver_unidade_com_equivalencia_informada(
    unidade_normalizada: str,
) -> tuple[str, Decimal] | None:
    if unidade_indica_quantidade_alternativa(unidade_normalizada):
        return None

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(kg|quilo|quilos|kilograma|kilogramas)\b",
        unidade_normalizada,
    )
    if match:
        return "massa", Decimal(match.group(1).replace(",", ".")) * Decimal("1000")

    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(g|grama|gramas)\b", unidade_normalizada)
    if match:
        return "massa", Decimal(match.group(1).replace(",", "."))

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(ml|mililitro|mililitros)\b",
        unidade_normalizada,
    )
    if match:
        return "volume", Decimal(match.group(1).replace(",", "."))

    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(l|lt|litro|litros)\b", unidade_normalizada)
    if match:
        return "volume", Decimal(match.group(1).replace(",", ".")) * Decimal("1000")

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(un|und|unidade|unidades|ovo|ovos)\b",
        unidade_normalizada,
    )
    if match:
        return "unidade", Decimal(match.group(1).replace(",", "."))

    return None


def unidade_indica_quantidade_alternativa(unidade_normalizada: str) -> bool:
    return bool(
        re.search(r"\b(?:ou|ate)\b\s*\d", unidade_normalizada)
        or re.search(r"\d+(?:[,.]\d+)?\s*(?:ou|a|ate|-)\s*\d", unidade_normalizada)
    )


def unidade_suportada(unidade: str | None) -> bool:
    if not unidade:
        return False
    try:
        resolver_unidade(unidade)
    except BadRequestError:
        return False
    return True


def descrever_unidade_aproximada(unidade: str) -> str | None:
    unidade_normalizada = normalizar_unidade(unidade)
    descricao = descrever_unidade_com_equivalencia_informada(unidade_normalizada)
    if descricao:
        return descricao
    return DESCRICOES_UNIDADES_APROXIMADAS.get(unidade_normalizada)


def descrever_unidade_com_equivalencia_informada(unidade_normalizada: str) -> str | None:
    unidade_resolvida = resolver_unidade_com_equivalencia_informada(unidade_normalizada)
    if not unidade_resolvida:
        return None
    tipo, fator = unidade_resolvida
    if tipo == "massa":
        return f"{unidade_normalizada} = {fator} g"
    if tipo == "volume":
        return f"{unidade_normalizada} = {fator} ml"
    return f"{unidade_normalizada} = {fator} unidades"


def arredondar_moeda(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def arredondar_custo_unitario(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def arredondar_quantidade(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
