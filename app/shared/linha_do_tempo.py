from typing import Any
from uuid import UUID

from app.shared.db import to_db_payload
from supabase import Client

TIPOS_EVENTO_PUBLICOS = {
    "dia_de_venda_aberto": "DIA_VENDA_ABERTO",
    "dia_venda_aberto": "DIA_VENDA_ABERTO",
    "dia_de_venda_fechado": "DIA_VENDA_FECHADO",
    "dia_venda_fechado": "DIA_VENDA_FECHADO",
    "item_producao_adicionado": "PRODUTO_ADICIONADO",
    "item_producao_atualizado": "PRODUTO_ADICIONADO",
    "produto_adicionado": "PRODUTO_ADICIONADO",
    "produto_removido": "PRODUTO_REMOVIDO",
    "venda_registrada": "VENDA_REALIZADA",
    "venda_realizada": "VENDA_REALIZADA",
    "venda_cancelada": "VENDA_CANCELADA",
    "produto_esgotado": "PRODUTO_ESGOTADO",
    "correcao_dia_fechado": "CORRECAO_DIA_FECHADO",
}


def registrar_evento_na_linha_do_tempo(
    client: Client,
    *,
    tipo_evento: str,
    titulo: str,
    tipo_entidade: str,
    entidade_id: UUID | str | None = None,
    dia_de_venda_id: UUID | str | None = None,
    usuario_id: UUID | str | None = None,
    detalhes: dict[str, Any] | None = None,
) -> None:
    tipo_publico = normalizar_tipo_evento_publico(tipo_evento)
    dados = to_db_payload(
        {
            "tipo_evento": tipo_publico,
            "titulo": titulo,
            "tipo_entidade": tipo_entidade,
            "entidade_id": entidade_id,
            "dia_de_venda_id": dia_de_venda_id,
            "usuario_id": usuario_id,
            "detalhes": detalhes or {},
        }
    )
    client.table("eventos_linha_do_tempo").insert(dados).execute()


def normalizar_tipo_evento_publico(tipo_evento: str) -> str:
    if tipo_evento in TIPOS_EVENTO_PUBLICOS.values():
        return tipo_evento
    tipo_normalizado = tipo_evento.lower().replace("-", "_")
    return TIPOS_EVENTO_PUBLICOS.get(tipo_normalizado, tipo_normalizado.upper())


def montar_evento_publico(evento: dict) -> dict:
    tipo_publico = normalizar_tipo_evento_publico(evento["tipo_evento"])
    dados = evento.get("detalhes") or {}
    return {
        **evento,
        "tipo_evento": tipo_publico,
        "tipo": tipo_publico,
        "dataHora": evento["criado_em"],
        "dados": dados,
    }


def montar_evento_publico_enxuto(evento: dict) -> dict:
    tipo_publico = normalizar_tipo_evento_publico(evento["tipo_evento"])
    return {
        "id": evento["id"],
        "tipo": tipo_publico,
        "titulo": evento.get("titulo") or tipo_publico,
        "detalhes": _resumir_detalhes_evento(evento.get("detalhes") or {}),
        "dataHora": evento["criado_em"],
    }


def _resumir_detalhes_evento(detalhes: dict[str, Any]) -> dict[str, Any]:
    resumo = {}
    nome_produto = _buscar_valor_em_detalhes(
        detalhes,
        {
            "nome_produto",
            "nome_produto_no_momento",
            "produto",
            "nome",
        },
    )
    quantidade = _buscar_valor_em_detalhes(
        detalhes,
        {
            "quantidade",
            "quantidade_produzida",
            "quantidade_vendida",
            "quantidade_sobra",
            "quantidade_usada",
        },
    )
    if nome_produto is not None:
        resumo["nome_produto"] = nome_produto
    if quantidade is not None:
        resumo["quantidade"] = quantidade
    return resumo


def _buscar_valor_em_detalhes(valor: Any, chaves: set[str], *, profundidade: int = 0) -> Any:
    if profundidade > 4:
        return None
    if isinstance(valor, dict):
        for chave in chaves:
            item = valor.get(chave)
            if _valor_resumivel(item):
                return item
            if isinstance(item, dict):
                aninhado = _buscar_valor_em_detalhes(item, chaves, profundidade=profundidade + 1)
                if _valor_resumivel(aninhado):
                    return aninhado
        for item in valor.values():
            aninhado = _buscar_valor_em_detalhes(item, chaves, profundidade=profundidade + 1)
            if _valor_resumivel(aninhado):
                return aninhado
    if isinstance(valor, list):
        for item in valor[:5]:
            aninhado = _buscar_valor_em_detalhes(item, chaves, profundidade=profundidade + 1)
            if _valor_resumivel(aninhado):
                return aninhado
    return None


def _valor_resumivel(valor: Any) -> bool:
    return isinstance(valor, str | int | float | bool) and str(valor).strip() != ""
