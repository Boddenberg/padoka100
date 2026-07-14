from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel


class RequisicaoGerarVendasFake(ApiModel):
    usuario_id: UUID | None = None
    usuario_email: str | None = Field(default=None, min_length=3, max_length=254)
    usuario_nome: str | None = Field(default=None, min_length=1, max_length=120)
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
    somente_simular: bool = False
    probabilidade_reaproveitar_sobra: float = Field(default=0.65, ge=0, le=1)
    percentual_reaproveitamento_min: float = Field(default=0.25, ge=0, le=1)
    percentual_reaproveitamento_max: float = Field(default=1.0, ge=0, le=1)
    taxa_cancelamento: float = Field(default=0.04, ge=0, le=0.5)
    tipos_entrada: list[Literal["manual", "audio", "ia"]] = Field(
        default_factory=lambda: ["manual", "audio", "ia"],
        min_length=1,
    )
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
        seletores = [self.usuario_id, self.usuario_email, self.usuario_nome]
        if sum(valor is not None for valor in seletores) > 1:
            raise ValueError(
                "Informe apenas um seletor de usuario: usuario_id, usuario_email ou usuario_nome."
            )
        if self.percentual_reaproveitamento_min > self.percentual_reaproveitamento_max:
            raise ValueError(
                "percentual_reaproveitamento_min nao pode ser maior que "
                "percentual_reaproveitamento_max."
            )
        self.tipos_entrada = list(dict.fromkeys(self.tipos_entrada))
        if self.usuario_email:
            self.usuario_email = self.usuario_email.strip().lower()
        if self.usuario_nome:
            self.usuario_nome = self.usuario_nome.strip()
        return self


class ProdutoSeedSaida(ApiModel):
    id: UUID
    nome: str
    origem: Literal["existente", "seed"] = "existente"


class UsuarioSeedSaida(ApiModel):
    id: UUID
    email: str
    nome: str | None = None


class DiaFakeSaida(ApiModel):
    id: UUID
    data_venda: date
    produtos_produzidos: int
    vendas_criadas: int
    itens_venda_criados: int
    unidades_produzidas: int
    unidades_vendidas: int
    vendas_canceladas: int = 0
    cenario: Literal[
        "normal",
        "alta_demanda",
        "baixa_demanda",
        "excesso_producao",
        "esgotamento",
    ] = "normal"
    unidades_sobra_recebidas: int = 0
    unidades_sobra_reaproveitadas: int = 0
    unidades_sobra_descartadas: int = 0
    unidades_sobrando: int = 0
    observacoes_fechamento: str | None = None


class RespostaGerarVendasFake(ApiModel):
    lote_id: UUID
    seed: int
    somente_simulacao: bool = False
    usuario: UsuarioSeedSaida
    periodo_inicio: date
    periodo_fim: date
    total_dias: int
    total_vendas: int
    total_itens_venda: int
    total_unidades_produzidas: int
    total_unidades_vendidas: int
    total_vendas_canceladas: int = 0
    total_unidades_sobra_reaproveitadas: int = 0
    total_unidades_sobra_descartadas: int = 0
    total_unidades_sobrando: int = 0
    produtos_usados: list[ProdutoSeedSaida]
    dias: list[DiaFakeSaida]
    avisos: list[str] = Field(default_factory=list)
