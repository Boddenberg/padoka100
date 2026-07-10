"""Normalizacao e comparacao pura de nomes de insumo/ingrediente."""

import re
import unicodedata

DESCRITORES_INGREDIENTE = {
    "branca",
    "brancas",
    "branco",
    "brancos",
    "especial",
    "especiais",
    "extra",
    "fina",
    "fino",
    "grande",
    "grandes",
    "integral",
    "iodada",
    "iodado",
    "ralado",
    "ralada",
    "refinada",
    "refinado",
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


def normalizar_nome_insumo(nome: str | None) -> str:
    texto = unicodedata.normalize("NFKD", str(nome or "").strip().lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9]+", " ", texto).strip()
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


def nomes_insumos_compativeis(nome_a: str | None, nome_b: str | None) -> bool:
    normalizado_a = normalizar_nome_insumo(nome_a)
    normalizado_b = normalizar_nome_insumo(nome_b)
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


def deduplicar_textos(textos: list[str]) -> list[str]:
    resultado = []
    vistos = set()
    for texto in textos:
        chave = re.sub(r"\s+", " ", str(texto).strip().lower())
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(str(texto))
    return resultado
