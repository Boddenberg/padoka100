"""Conversao e custeio por unidade de medida (puro, sem rede).

Trata unidades base (massa/volume/unidade), equivalencias informadas no texto
(ex.: "1kg", "500 g") e unidades com ruido, alem do arredondamento monetario.
Tambem estima conversoes entre tipos diferentes (volume x massa x unidade)
usando densidades medias e pesos tipicos, para que o custeio nunca trave por
incompatibilidade de unidades.
"""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import BadRequestError
from app.modules.custos.domain.ingredientes import normalizar_nome_insumo

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
# Densidades medias (g por ml) usadas para converter volume <-> massa quando a
# receita e a compra usam tipos diferentes (ex.: colher de sopa x kg). A ordem
# importa: a primeira regra cujos termos estejam todos no nome do ingrediente
# vence.
DENSIDADE_PADRAO_G_POR_ML = Decimal("1")
DENSIDADES_G_POR_ML_POR_INGREDIENTE = (
    ({"leite", "condensado"}, Decimal("1.30")),
    ({"creme", "leite"}, Decimal("1.00")),
    ({"leite", "po"}, Decimal("0.50")),
    ({"leite"}, Decimal("1.03")),
    ({"farinha"}, Decimal("0.55")),
    ({"polvilho"}, Decimal("0.55")),
    ({"amido"}, Decimal("0.55")),
    ({"maizena"}, Decimal("0.55")),
    ({"acucar"}, Decimal("0.85")),
    ({"sal"}, Decimal("1.20")),
    ({"oleo"}, Decimal("0.92")),
    ({"azeite"}, Decimal("0.91")),
    ({"manteiga"}, Decimal("0.95")),
    ({"margarina"}, Decimal("0.95")),
    ({"mel"}, Decimal("1.40")),
    ({"chocolate", "po"}, Decimal("0.50")),
    ({"cacau"}, Decimal("0.50")),
    ({"achocolatado"}, Decimal("0.50")),
    ({"queijo", "ralado"}, Decimal("0.40")),
    ({"parmesao"}, Decimal("0.40")),
    ({"coco", "ralado"}, Decimal("0.35")),
    ({"fermento"}, Decimal("0.75")),
    ({"aveia"}, Decimal("0.40")),
    ({"agua"}, Decimal("1.00")),
)
# Pesos tipicos (g) de itens contados por unidade, para converter "3 ovos" em
# massa quando a compra foi em kg/g (ou vice-versa).
PESOS_TIPICOS_G_POR_UNIDADE = (
    ({"ovo"}, Decimal("50")),
    ({"dente"}, Decimal("5")),
    ({"alho"}, Decimal("5")),
    ({"banana"}, Decimal("100")),
    ({"limao"}, Decimal("100")),
    ({"laranja"}, Decimal("180")),
    ({"cebola"}, Decimal("150")),
    ({"tomate"}, Decimal("120")),
    ({"batata"}, Decimal("200")),
    ({"cenoura"}, Decimal("100")),
)
AVISO_ESTIMATIVA_DE_CUSTO = (
    "O custo e uma estimativa aproximada: algumas medidas foram convertidas "
    "com valores medios (densidade, medidas caseiras ou tamanho de embalagem). "
    "O valor real pode variar um pouco."
)
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
    # Unidade desconhecida vale como "1 unidade/embalagem" para nunca travar o
    # registro de uma compra; a estimativa de uso avisa sobre a aproximacao.
    _, fator, _ = resolver_unidade_flexivel(unidade)
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


def estimar_custo_ingrediente(
    custo_unitario_base: Decimal,
    quantidade_usada: Decimal,
    unidade_usada: str | None,
    unidade_compra: str | None,
    *,
    nome_ingrediente: str | None = None,
) -> dict:
    """Estima o custo do ingrediente sem nunca levantar erro de conversao.

    Ao contrario de calcular_custo_ingrediente, unidades de tipos diferentes
    sao convertidas por aproximacao (densidade media, peso tipico do item ou
    embalagem inteira). O retorno traz o custo, a quantidade na unidade base
    da compra (para exibir a formula), se o calculo e aproximado e os avisos
    que explicam cada aproximacao adotada.
    """
    avisos: list[str] = []
    nome = str(nome_ingrediente or "").strip() or "ingrediente"
    custo_unitario = Decimal(str(custo_unitario_base))
    quantidade = Decimal(str(quantidade_usada if quantidade_usada is not None else 0))

    tipo_uso, fator_uso, aviso_uso = resolver_unidade_flexivel(unidade_usada)
    tipo_compra, fator_compra, aviso_compra = resolver_unidade_flexivel(unidade_compra)
    for aviso in (aviso_uso, aviso_compra):
        if aviso:
            avisos.append(f"{nome}: {aviso}")
    aproximado = bool(avisos)

    if quantidade <= 0:
        avisos.append(f"{nome}: quantidade usada invalida; considerei custo zero.")
        return {
            "custo": Decimal("0.00"),
            "quantidade_base": Decimal("0"),
            "unidade_base": unidade_base_para_tipo(tipo_compra),
            "aproximado": True,
            "avisos": avisos,
        }

    if tipo_uso == tipo_compra:
        quantidade_base = quantidade * fator_uso
    elif {tipo_uso, tipo_compra} == {"massa", "volume"}:
        densidade, conhecida = densidade_aproximada_g_por_ml(nome_ingrediente)
        if tipo_uso == "volume":
            quantidade_base = quantidade * fator_uso * densidade
        else:
            quantidade_base = quantidade * fator_uso / densidade
        origem = (
            f"densidade aproximada de {decimal_unidade_str(densidade)} g/ml"
            if conhecida
            else "densidade media de 1 g/ml"
        )
        aproximado = True
        avisos.append(
            f"{nome}: converti '{unidade_usada}' para '{unidade_compra}' usando {origem}."
        )
    elif tipo_uso == "unidade":
        peso = peso_tipico_por_unidade_g(nome_ingrediente, unidade_usada)
        if peso is not None:
            gramas = quantidade * fator_uso * peso
            if tipo_compra == "volume":
                densidade, _ = densidade_aproximada_g_por_ml(nome_ingrediente)
                quantidade_base = gramas / densidade
            else:
                quantidade_base = gramas
            avisos.append(
                f"{nome}: considerei 1 {unidade_usada or 'unidade'} = "
                f"{decimal_unidade_str(peso)} g."
            )
        else:
            quantidade_base = quantidade * fator_uso * fator_compra
            avisos.append(
                f"{nome}: considerei 1 {unidade_usada or 'unidade'} usada = "
                f"1 {unidade_compra} comprado. Informe a equivalencia "
                "(ex.: '1 pacote = 500g') para melhorar a estimativa."
            )
        aproximado = True
    else:
        peso = peso_tipico_por_unidade_g(nome_ingrediente, unidade_compra)
        if peso is not None and peso > 0:
            gramas_usadas = quantidade * fator_uso
            if tipo_uso == "volume":
                densidade, _ = densidade_aproximada_g_por_ml(nome_ingrediente)
                gramas_usadas = gramas_usadas * densidade
            quantidade_base = gramas_usadas / peso
            avisos.append(
                f"{nome}: considerei 1 {unidade_compra or 'unidade'} comprado = "
                f"{decimal_unidade_str(peso)} g."
            )
        else:
            quantidade_base = Decimal("1")
            avisos.append(
                f"{nome}: sem a equivalencia da embalagem, considerei que a "
                f"receita consome 1 {unidade_compra or 'embalagem'} inteira. "
                "Informe o peso ou volume da embalagem (ex.: '1 pacote = 1kg') "
                "para melhorar a estimativa."
            )
        aproximado = True

    return {
        "custo": arredondar_moeda(custo_unitario * quantidade_base),
        "quantidade_base": arredondar_quantidade(quantidade_base),
        "unidade_base": unidade_base_para_tipo(tipo_compra),
        "aproximado": aproximado,
        "avisos": avisos,
    }


def resolver_unidade_flexivel(unidade: str | None) -> tuple[str, Decimal, str | None]:
    """Resolve a unidade sem levantar erro: desconhecida vira 1 unidade/embalagem."""
    if unidade is None or not str(unidade).strip():
        return (
            "unidade",
            Decimal("1"),
            "unidade nao informada; considerei 1 unidade/embalagem",
        )
    try:
        tipo, fator = resolver_unidade(unidade)
    except BadRequestError:
        return (
            "unidade",
            Decimal("1"),
            f"unidade '{unidade}' nao reconhecida; considerei 1 unidade/embalagem",
        )
    return tipo, fator, None


def densidade_aproximada_g_por_ml(nome_ingrediente: str | None) -> tuple[Decimal, bool]:
    tokens = _tokens_de_ingrediente(nome_ingrediente)
    for termos, densidade in DENSIDADES_G_POR_ML_POR_INGREDIENTE:
        if termos <= tokens:
            return densidade, True
    return DENSIDADE_PADRAO_G_POR_ML, False


def peso_tipico_por_unidade_g(
    nome_ingrediente: str | None,
    unidade: str | None = None,
) -> Decimal | None:
    tokens = _tokens_de_ingrediente(nome_ingrediente, unidade)
    for termos, peso in PESOS_TIPICOS_G_POR_UNIDADE:
        if termos <= tokens:
            return peso
    return None


def _tokens_de_ingrediente(*textos: str | None) -> set[str]:
    texto = " ".join(str(texto) for texto in textos if texto and str(texto).strip())
    tokens = set(normalizar_nome_insumo(texto).split())
    singulares = {token[:-1] for token in tokens if token.endswith("s") and len(token) > 3}
    return tokens | singulares


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
