from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class ProdutoBase(ApiModel):
    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = None
    descricao_visual: str | None = None
    url_imagem_principal: str | None = None
    cor_botao: str | None = None
    ordem_exibicao: int = 0


class RequisicaoCriarProduto(ProdutoBase):
    preco_venda: Decimal = Field(ge=0)
    preco_custo: Decimal = Field(default=0, ge=0)
    vigente_desde: date = Field(default_factory=date.today)
    motivo_preco: str | None = "Preco inicial"


class RequisicaoAtualizarProduto(ApiModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    descricao: str | None = None
    descricao_visual: str | None = None
    url_imagem_principal: str | None = None
    cor_botao: str | None = None
    ordem_exibicao: int | None = None
    situacao: str | None = Field(default=None, pattern="^(ativo|inativo)$")


class RequisicaoCriarVersaoDePreco(ApiModel):
    preco_venda: Decimal = Field(ge=0)
    preco_custo: Decimal = Field(default=0, ge=0)
    vigente_desde: date = Field(default_factory=date.today)
    motivo: str | None = None


class VersaoDePrecoSaida(ApiModel):
    id: UUID
    produto_id: UUID
    preco_venda: Decimal
    preco_custo: Decimal
    moeda: str
    vigente_desde: date
    vigente_ate: date | None = None
    motivo: str | None = None
    criado_em: datetime


class ProdutoSaida(ProdutoBase):
    id: UUID
    slug: str | None = None
    situacao: str
    preco_atual: VersaoDePrecoSaida | None = None
    criado_em: datetime
    atualizado_em: datetime
