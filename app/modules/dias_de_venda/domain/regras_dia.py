"""Decisoes puras sobre abertura de dia de venda."""

from app.modules.dias_de_venda.esquemas import RequisicaoIniciarDiaDeVenda


def dia_parece_seed_analytics(dia: dict) -> bool:
    texto = " ".join(
        [
            str(dia.get("nome_local_no_momento") or ""),
            str(dia.get("observacoes") or ""),
        ]
    ).lower()
    return "seed analytics" in texto or "seed_analytics" in texto


def requisicao_indica_nova_abertura(
    requisicao: RequisicaoIniciarDiaDeVenda,
    *,
    dia_atual_existente: dict | None,
) -> bool:
    if not dia_atual_existente:
        return False
    return any(
        [
            bool(requisicao.itens_producao),
            requisicao.observacoes is not None,
            requisicao.local_id is not None,
            requisicao.nome_local is not None,
        ]
    )
