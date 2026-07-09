from datetime import date
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel


class RequisicaoGerarVendasFake(ApiModel):
    data_inicio: date | None = None
    data_fim: date | None = None
    datas: list[date] = Field(default_factory=list)
    quantidade_dias: int = Field(default=14, ge=1, le=120)
    produto_ids: list[UUID] = Field(default_factory=list)
    produtos_por_dia_min: int = Field(default=2, ge=1, le=20)
    produtos_por_dia_max: int = Field(default=6, ge=1, le=30)
    vendas_por_dia_min: int = Field(default=18, ge=0, le=500)
    vendas_por_dia_max: int = Field(default=55, ge=0, le=800)
    itens_por_venda_min: int = Field(default=1, ge=1, le=20)
    itens_por_venda_max: int = Field(default=3, ge=1, le=30)
    quantidade_producao_min: int = Field(default=30, ge=1, le=5000)
    quantidade_producao_max: int = Field(default=180, ge=1, le=10000)
    quantidade_item_venda_min: int = Field(default=1, ge=1, le=1000)
    quantidade_item_venda_max: int = Field(default=8, ge=1, le=2000)
    fechar_dias: bool = True
    limpar_seed_anterior: bool = False
    criar_produtos_fake_se_necessario: bool = True
    nome_local: str = Field(default="Seed Analytics", min_length=1, max_length=120)
    marcador: str = Field(default="SEED_ANALYTICS", min_length=3, max_length=80)
    observacao_base: str | None = Field(default=None, max_length=500)
    seed: int | None = None

    @model_validator(mode="after")
    def validar_intervalos(self) -> "RequisicaoGerarVendasFake":
        pares = [
            ("produtos_por_dia", self.produtos_por_dia_min, self.produtos_por_dia_max),
            ("vendas_por_dia", self.vendas_por_dia_min, self.vendas_por_dia_max),
            ("itens_por_venda", self.itens_por_venda_min, self.itens_por_venda_max),
            ("quantidade_producao", self.quantidade_producao_min, self.quantidade_producao_max),
            (
                "quantidade_item_venda",
                self.quantidade_item_venda_min,
                self.quantidade_item_venda_max,
            ),
        ]
        for nome, minimo, maximo in pares:
            if minimo > maximo:
                raise ValueError(f"{nome}_min nao pode ser maior que {nome}_max.")
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValueError("data_inicio nao pode ser maior que data_fim.")
        return self


class ProdutoSeedSaida(ApiModel):
    id: UUID
    nome: str


class DiaFakeSaida(ApiModel):
    id: UUID
    data_venda: date
    produtos_produzidos: int
    vendas_criadas: int
    itens_venda_criados: int
    unidades_produzidas: int
    unidades_vendidas: int
    observacoes_fechamento: str | None = None


class RespostaGerarVendasFake(ApiModel):
    lote_id: UUID
    seed: int
    periodo_inicio: date
    periodo_fim: date
    total_dias: int
    total_vendas: int
    total_itens_venda: int
    total_unidades_produzidas: int
    total_unidades_vendidas: int
    produtos_usados: list[ProdutoSeedSaida]
    dias: list[DiaFakeSaida]
    avisos: list[str] = Field(default_factory=list)
