from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel

STATUS_CUSTO_PATTERN = "^(CONFIRMADO|ESTIMADO|PENDENTE|PRECISA_REVISAR)$"


class RequisicaoCriarInsumo(ApiModel):
    nome: str = Field(min_length=1, max_length=120)
    categoria: str | None = Field(default=None, max_length=80)
    quantidade_comprada: Decimal = Field(gt=0)
    unidade_compra: str = Field(min_length=1, max_length=20)
    preco_total: Decimal = Field(ge=0)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class RequisicaoAtualizarInsumo(ApiModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    categoria: str | None = Field(default=None, max_length=80)
    quantidade_comprada: Decimal | None = Field(default=None, gt=0)
    unidade_compra: str | None = Field(default=None, min_length=1, max_length=20)
    preco_total: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class InsumoSaida(ApiModel):
    id: UUID
    nome: str
    categoria: str | None = None
    quantidade_comprada: Decimal
    unidade_compra: str
    preco_total: Decimal
    custo_por_unidade: Decimal
    status: str
    observacoes: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class RequisicaoIngredienteReceita(ApiModel):
    insumo_id: UUID | None = None
    nome: str = Field(min_length=1, max_length=120)
    quantidade_usada: Decimal = Field(gt=0)
    unidade: str = Field(min_length=1, max_length=20)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class RequisicaoCriarReceita(ApiModel):
    nome: str | None = Field(default=None, max_length=120)
    rendimento: Decimal = Field(gt=0)
    unidade_rendimento: str = Field(default="unidade", min_length=1, max_length=30)
    status: str = Field(default="PENDENTE", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None
    ingredientes: list[RequisicaoIngredienteReceita] = Field(default_factory=list)


class RequisicaoCriarCustoAdicional(ApiModel):
    receita_id: UUID | None = None
    tipo: str = Field(pattern="^(embalagem|transporte|indireto|outro)$")
    nome: str = Field(min_length=1, max_length=120)
    valor: Decimal = Field(ge=0)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class IngredienteReceitaSaida(ApiModel):
    id: UUID
    receita_id: UUID
    insumo_id: UUID | None = None
    nome_insumo_no_momento: str
    quantidade_usada: Decimal
    unidade: str
    custo_unitario_no_momento: Decimal | None = None
    custo_total_estimado: Decimal | None = None
    status: str
    observacoes: str | None = None
    criado_em: datetime


class ReceitaSaida(ApiModel):
    id: UUID
    produto_id: UUID
    nome: str | None = None
    rendimento: Decimal
    unidade_rendimento: str
    status: str
    observacoes: str | None = None
    criado_em: datetime
    atualizado_em: datetime
    ingredientes: list[IngredienteReceitaSaida] = Field(default_factory=list)


class CustoAdicionalSaida(ApiModel):
    id: UUID
    produto_id: UUID
    receita_id: UUID | None = None
    tipo: str
    nome: str
    valor: Decimal
    status: str
    observacoes: str | None = None
    criado_em: datetime


class CalculoCustoProdutoSaida(ApiModel):
    produto_id: UUID
    produto: str
    receita_id: UUID | None = None
    custo_total_receita: Decimal
    rendimento: Decimal | None = None
    custo_por_unidade: Decimal | None = None
    custos_incluidos: dict
    status: str
    ingredientes: list[IngredienteReceitaSaida] = Field(default_factory=list)
    custos_adicionais: list[CustoAdicionalSaida] = Field(default_factory=list)
    pendencias: list[str] = Field(default_factory=list)
