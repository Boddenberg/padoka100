"""Leitura contextual opcional para relatorios dos planos IA e Admin."""

import json
import logging

from app.core.config import get_settings
from app.infra.openai.client import get_openai_client

logger = logging.getLogger(__name__)


def _fallback(conteudo: dict, *, motivo: str | None = None) -> dict:
    indicadores = conteudo["indicadores"]
    comparacao = conteudo["comparacao"]["faturamento"]
    if comparacao["tendencia"] == "alta":
        movimento = "O faturamento cresceu em relacao ao periodo anterior."
    elif comparacao["tendencia"] == "queda":
        movimento = "O faturamento recuou em relacao ao periodo anterior."
    else:
        movimento = "O faturamento ficou estavel ou ainda nao tem base de comparacao."
    acoes = [
        oportunidade["titulo"] + ". " + oportunidade["descricao"]
        for oportunidade in conteudo.get("oportunidades", [])[:4]
    ]
    if not acoes:
        acoes = [
            "Registre producao, vendas e custos por pelo menos sete dias para receber "
            "recomendacoes mais especificas."
        ]
    return {
        "disponivel": False,
        "modelo": "analise-local",
        "resumo": (
            f"Foram vendidas {indicadores['unidades_vendidas']} unidades, com "
            f"eficiencia de {indicadores['eficiencia_venda_percentual']:.1f}%. {movimento}"
        ),
        "principais_achados": [
            destaque["titulo"] + ": " + str(destaque["descricao"])
            for destaque in conteudo.get("destaques", [])[:4]
        ],
        "acoes_recomendadas": acoes,
        "pontos_atencao": [
            alerta["titulo"] + ". " + alerta["descricao"]
            for alerta in conteudo.get("alertas", [])[:4]
        ],
        "perguntas_estrategicas": [
            "Quais dias merecem uma producao diferente da media?",
            "O mix atual favorece produtos de boa margem e baixo desperdicio?",
        ],
        "limitacao": motivo
        or "A IA estava indisponivel; a leitura acima foi calculada sem modelo generativo.",
    }


def gerar_leitura(conteudo: dict) -> dict:
    settings = get_settings()
    if not settings.openai_text_configured:
        return _fallback(conteudo)

    resumo_para_ia = {
        "periodo": conteudo["periodo"],
        "indicadores": conteudo["indicadores"],
        "comparacao": conteudo["comparacao"],
        "produtos": conteudo["produtos"][:15],
        "serie_diaria": conteudo["serie_diaria"],
        "desempenho_semana": conteudo["desempenho_semana"],
        "horarios": conteudo["horarios"],
        "alertas_calculados": conteudo["alertas"],
        "oportunidades_calculadas": conteudo["oportunidades"],
        "qualidade_dados": conteudo["qualidade_dados"],
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "resumo",
            "principais_achados",
            "acoes_recomendadas",
            "pontos_atencao",
            "perguntas_estrategicas",
        ],
        "properties": {
            "resumo": {"type": "string"},
            "principais_achados": {"type": "array", "items": {"type": "string"}},
            "acoes_recomendadas": {"type": "array", "items": {"type": "string"}},
            "pontos_atencao": {"type": "array", "items": {"type": "string"}},
            "perguntas_estrategicas": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }
    try:
        resposta = get_openai_client().responses.create(
            model=settings.openai_text_model_resolved,
            instructions=(
                "Voce e um analista de negocios para uma pequena padaria familiar. "
                "Use somente os dados recebidos, sem inventar causas ou numeros. "
                "Diferencie correlacao de causa, sinalize amostras pequenas e transforme "
                "os achados em acoes simples, especificas e acolhedoras. Responda em "
                "portugues brasileiro, sem jargao e sem markdown."
            ),
            input=json.dumps(resumo_para_ia, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "leitura_analytics_padoka",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        leitura = json.loads(resposta.output_text)
        return {
            "disponivel": True,
            "modelo": settings.openai_text_model_resolved,
            **leitura,
            "limitacao": None,
        }
    except Exception:  # noqa: BLE001 - o relatorio nao falha junto com a IA
        logger.exception("Falha na leitura de IA do relatorio de Analytics")
        return _fallback(conteudo, motivo="Leitura local usada por indisponibilidade da IA.")
