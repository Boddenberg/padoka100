"""Equivalencia de embalagem estimada por LLM (somente conversao, nunca custo).

Toda a matematica de custeio e feita pelo backend. Este modulo so e consultado
quando a compra esta em embalagem generica (pacote, caixa, un...) e nenhum dado
deterministico (equivalencia explicita no texto ou tabela local) resolve o
tamanho. O LLM responde apenas a equivalencia de UMA embalagem (ex.: 1 pacote
de polvilho = 500 g); a resposta e validada, cacheada e devolvida como unidade
canonica (ex.: '500g') para o calculo local. Qualquer falha vira None e o
custeio segue com as regras deterministicas.
"""

import json
from decimal import Decimal, InvalidOperation
from threading import Lock

from app.core.config import get_settings
from app.core.errors import BadRequestError, MissingConfigurationError
from app.db.openai import get_openai_client
from app.modules.custos.domain.ingredientes import normalizar_nome_insumo
from app.modules.custos.domain.unidades import decimal_unidade_str, resolver_unidade

UNIDADES_ACEITAS = {
    "g": "g",
    "kg": "kg",
    "ml": "ml",
    "l": "l",
    "un": "unidade",
    "unidade": "unidade",
    "unidades": "unidade",
}
CONFIANCA_MINIMA = Decimal("0.5")
# Rejeita respostas absurdas do modelo: nenhuma embalagem de padaria passa de
# 100 kg / 100 l / 100000 unidades.
FATOR_BASE_MAXIMO = Decimal("100000")

_cache: dict[tuple[str, str], str | None] = {}
_cache_lock = Lock()


def estimar_equivalencia_de_embalagem(
    *,
    nome: str | None,
    unidade_compra: str | None,
    observacoes: str | None = None,
) -> str | None:
    """Retorna a unidade canonica da embalagem ('500g', '1l', '30unidade') ou None."""
    nome_normalizado = normalizar_nome_insumo(str(nome or ""))
    if not nome_normalizado:
        return None
    chave = (nome_normalizado, str(unidade_compra or "").strip().lower())
    with _cache_lock:
        if chave in _cache:
            return _cache[chave]

    try:
        resposta = _consultar_llm(
            nome=nome,
            unidade_compra=unidade_compra,
            observacoes=observacoes,
        )
    except Exception:
        # Falha transitoria (rede, chave ausente): nao cacheia para poder
        # tentar de novo; o custeio segue sem a equivalencia.
        return None

    unidade = _unidade_canonica_da_resposta(resposta)
    with _cache_lock:
        _cache[chave] = unidade
    return unidade


def limpar_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _consultar_llm(
    *,
    nome: str | None,
    unidade_compra: str | None,
    observacoes: str | None,
) -> dict:
    settings = get_settings()
    if not settings.openai_text_configured:
        raise MissingConfigurationError(
            "OpenAI Texto",
            ["OPENAI_API_KEY", "OPENAI_TEXT_MODEL"],
        )
    resposta = get_openai_client().responses.create(
        model=settings.openai_text_model_resolved,
        instructions=(
            "Voce informa o conteudo tipico de embalagens de ingredientes no "
            "varejo brasileiro para o custeio de uma padaria. Responda somente "
            "a equivalencia de UMA embalagem (ex.: 1 pacote de polvilho = 500 g). "
            "Nunca calcule custo e nunca invente preco. Se o tamanho tipico nao "
            "for conhecido com confianca razoavel, devolva quantidade e unidade "
            "nulas e confianca baixa."
        ),
        input=json.dumps(
            {
                "ingrediente": nome,
                "embalagem": unidade_compra,
                "observacoes": observacoes,
                "pergunta": (
                    f"Quanto contem tipicamente 1 {unidade_compra or 'embalagem'} "
                    f"de {nome} no varejo brasileiro?"
                ),
            },
            ensure_ascii=False,
        ),
        text={"format": _formato_json_equivalencia()},
    )
    return json.loads(resposta.output_text)


def _formato_json_equivalencia() -> dict:
    return {
        "type": "json_schema",
        "name": "equivalencia_embalagem_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["quantidade", "unidade", "confianca"],
            "properties": {
                "quantidade": {"type": ["number", "null"]},
                "unidade": {
                    "type": ["string", "null"],
                    "description": "Somente g, kg, ml, l ou unidades.",
                },
                "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "strict": True,
    }


def _unidade_canonica_da_resposta(resposta: dict) -> str | None:
    if not isinstance(resposta, dict):
        return None
    quantidade = resposta.get("quantidade")
    unidade = str(resposta.get("unidade") or "").strip().lower()
    if quantidade is None or unidade not in UNIDADES_ACEITAS:
        return None
    try:
        valor = Decimal(str(quantidade))
        confianca = Decimal(str(resposta.get("confianca") or 0))
    except (InvalidOperation, ValueError):
        return None
    if valor <= 0 or confianca < CONFIANCA_MINIMA:
        return None
    unidade_canonica = f"{decimal_unidade_str(valor)}{UNIDADES_ACEITAS[unidade]}"
    try:
        _, fator = resolver_unidade(unidade_canonica)
    except BadRequestError:
        return None
    if fator <= 0 or fator > FATOR_BASE_MAXIMO:
        return None
    return unidade_canonica
