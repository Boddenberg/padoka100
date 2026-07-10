"""Normalizacao e formatacao pura de texto para a IA.

Funcoes sem rede: normalizam numeros/datas/uuids, extraem pistas do comando e
formatam mensagens. Base do interpretador de fallback e das confirmacoes.
"""

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.modules.ia.domain.vocabulario import NUMEROS_POR_EXTENSO
from app.shared.datas import data_operacional_hoje


def normalizar(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor.lower())
    valor_ascii = normalizado.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", valor_ascii).strip()


def normalizar_quantidade(valor) -> int:
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return 0


def normalizar_confianca(valor) -> float:
    try:
        return min(max(float(valor), 0), 1)
    except (TypeError, ValueError):
        return 0


def normalizar_texto_opcional(valor) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def normalizar_data(valor) -> str | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except ValueError:
        return None


def normalizar_uuid_str(valor) -> str | None:
    if not valor:
        return None
    try:
        return str(UUID(str(valor)))
    except ValueError:
        return None


def data_ou_none(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def data_ou_hoje(valor: str | None) -> date:
    return data_ou_none(valor) or data_operacional_hoje()


def extrair_data_do_texto(texto: str) -> str | None:
    texto_normalizado = normalizar(texto)
    tokens = set(texto_normalizado.split())
    hoje = data_operacional_hoje()
    if "hoje" in tokens:
        return hoje.isoformat()
    if "ontem" in tokens:
        return (hoje - timedelta(days=1)).isoformat()
    if "amanha" in tokens:
        return (hoje + timedelta(days=1)).isoformat()

    resultado_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto)
    if resultado_iso:
        try:
            return date.fromisoformat(resultado_iso.group(0)).isoformat()
        except ValueError:
            return None

    resultado_br = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", texto)
    if resultado_br:
        dia = int(resultado_br.group(1))
        mes = int(resultado_br.group(2))
        ano_texto = resultado_br.group(3)
        ano = hoje.year if not ano_texto else int(ano_texto)
        if ano < 100:
            ano += 2000
        try:
            return date(ano, mes, dia).isoformat()
        except ValueError:
            return None

    return None


def extrair_uuid_do_texto(texto: str) -> str | None:
    resultado = re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        texto,
    )
    return resultado.group(0) if resultado else None


def buscar_quantidade_antes(tokens: list[str], posicao: int) -> int:
    janela = tokens[max(0, posicao - 6) : posicao]
    for token in reversed(janela):
        if token.isdigit():
            return max(int(token), 1)
        if token in NUMEROS_POR_EXTENSO:
            return NUMEROS_POR_EXTENSO[token]
        resultado = re.match(r"(\d+)x?", token)
        if resultado:
            return max(int(resultado.group(1)), 1)
    return 1


def formatar_data(data_valor: str) -> str:
    data = date.fromisoformat(data_valor)
    return data.strftime("%d/%m/%Y")


def formatar_moeda(valor: Decimal) -> str:
    texto = f"{valor:.2f}".replace(".", ",")
    return f"R$ {texto}"


def formatar_itens(itens: list[dict]) -> str:
    if not itens:
        return "nenhum item"
    return ", ".join(f"{item['quantidade']}x {item['nome_produto']}" for item in itens)


def formatar_itens_da_venda(venda: dict) -> str:
    itens = [
        {
            "quantidade": item["quantidade"],
            "nome_produto": item["nome_produto_no_momento"],
        }
        for item in venda.get("itens", [])
    ]
    return formatar_itens(itens)


def total_da_venda(venda: dict) -> Decimal:
    total = Decimal("0")
    for item in venda.get("itens") or []:
        total += Decimal(str(item.get("valor_total_venda") or 0))
    return total


def formatar_resumo_da_venda(venda: dict) -> str:
    itens = venda.get("itens") or []
    if not itens:
        return "sem itens registrados, total R$ 0,00"
    return f"{formatar_itens_da_venda(venda)}, total {formatar_moeda(total_da_venda(venda))}"
