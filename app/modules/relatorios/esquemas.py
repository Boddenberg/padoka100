from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class ResumoProdutoNoDia(ApiModel):
    produto_id: UUID
    nome_produto: str
    url_imagem_produto: str | None = None
    quantidade_produzida: int = 0
    quantidade_sobra_aproveitada: int = 0
    quantidade_disponivel: int = 0
    quantidade_vendida: int = 0
    quantidade_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")


class ResumoDoDiaDeVenda(ApiModel):
    dia_de_venda_id: UUID
    data_venda: date
    nome_local: str | None = None
    situacao: str
    total_produzido: int = 0
    total_sobra_aproveitada: int = 0
    total_disponivel: int = 0
    total_vendido: int = 0
    total_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")
    produtos: list[ResumoProdutoNoDia] = Field(default_factory=list)


class ResumoDoPeriodo(ApiModel):
    data_inicio: date
    data_fim: date
    total_produzido: int = 0
    total_sobra_aproveitada: int = 0
    total_disponivel: int = 0
    total_vendido: int = 0
    total_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")
    dias: list[ResumoDoDiaDeVenda] = Field(default_factory=list)
