from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel, CorrecaoDiaFechadoSaida, EventoLinhaDoTempoSaida


class ResumoProdutoNoDia(ApiModel):
    produto_id: UUID
    nome_produto: str
    url_imagem_produto: str | None = None
    participou_da_venda: bool = True
    esgotado: bool = False
    quantidade_produzida: int = 0
    quantidade_sobra_aproveitada: int = 0
    quantidade_sobra_descartada: int = 0
    quantidade_disponivel: int = 0
    quantidade_vendida: int = 0
    quantidade_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")


class ResumoDoDiaDeVenda(ApiModel):
    dia_de_venda_id: UUID
    dia_de_venda_ids: list[UUID] = Field(default_factory=list)
    quantidade_aberturas: int = 1
    data_venda: date
    data: date
    nome_local: str | None = None
    situacao: str
    status: str
    total_produzido: int = 0
    total_sobra_aproveitada: int = 0
    total_sobra_descartada: int = 0
    total_disponivel: int = 0
    total_vendido: int = 0
    itens_vendidos: int = 0
    total_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    faturamento_total: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")
    produtos: list[ResumoProdutoNoDia] = Field(default_factory=list)
    produtos_produzidos: list[ResumoProdutoNoDia] = Field(default_factory=list)
    produtos_vendidos: list[ResumoProdutoNoDia] = Field(default_factory=list)
    produtos_sobrando: list[ResumoProdutoNoDia] = Field(default_factory=list)
    produtos_esgotados: list[ResumoProdutoNoDia] = Field(default_factory=list)
    historico: list[EventoLinhaDoTempoSaida] = Field(default_factory=list)
    correcoes: list[CorrecaoDiaFechadoSaida] = Field(default_factory=list)


class ResumoDoPeriodo(ApiModel):
    data_inicio: date
    data_fim: date
    produto_id: UUID | None = None
    total_produzido: int = 0
    total_sobra_aproveitada: int = 0
    total_sobra_descartada: int = 0
    total_disponivel: int = 0
    total_vendido: int = 0
    total_sobra: int = 0
    faturamento_bruto: Decimal = Decimal("0")
    custo_estimado: Decimal = Decimal("0")
    lucro_estimado: Decimal = Decimal("0")
    dias: list[ResumoDoDiaDeVenda] = Field(default_factory=list)
