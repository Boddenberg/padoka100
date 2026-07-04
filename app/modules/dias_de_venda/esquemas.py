from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class RequisicaoCriarItemProducao(ApiModel):
    produto_id: UUID
    quantidade_produzida: int = Field(ge=0)
    observacoes: str | None = None


class ItemProducaoSaida(ApiModel):
    id: UUID
    dia_de_venda_id: UUID
    produto_id: UUID
    nome_produto_no_momento: str
    url_imagem_produto_no_momento: str | None = None
    versao_preco_id: UUID | None = None
    preco_venda_unitario_no_momento: Decimal
    preco_custo_unitario_no_momento: Decimal
    quantidade_produzida: int
    observacoes: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class RequisicaoCriarDiaDeVenda(ApiModel):
    data_venda: date = Field(default_factory=date.today)
    local_id: UUID | None = None
    nome_local: str | None = None
    observacoes: str | None = None
    itens_producao: list[RequisicaoCriarItemProducao] = Field(default_factory=list)


class RequisicaoAtualizarDiaDeVenda(ApiModel):
    local_id: UUID | None = None
    nome_local: str | None = None
    observacoes: str | None = None


class RequisicaoFecharDiaDeVenda(ApiModel):
    observacoes: str | None = None


class DiaDeVendaSaida(ApiModel):
    id: UUID
    data_venda: date
    local_id: UUID | None = None
    nome_local_no_momento: str | None = None
    observacoes: str | None = None
    situacao: str
    aberto_em: datetime
    fechado_em: datetime | None = None
    criado_em: datetime
    atualizado_em: datetime
    itens_producao: list[ItemProducaoSaida] = Field(default_factory=list)
