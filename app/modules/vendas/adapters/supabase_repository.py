from collections import defaultdict
from uuid import UUID

from app.core.errors import NotFoundError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.payload import to_db_payload
from app.infra.supabase.result import inserted_one, one_or_none, updated_one
from supabase import Client


class VendaRepository:
    """Acesso a vendas restrito ao dono informado.

    ``usuario_id`` e transicional-opcional enquanto os modulos consumidores
    migram para o modelo multiusuario.
    """

    def __init__(
        self,
        client: Client | None = None,
        *,
        usuario_id: UUID | str | None = None,
    ) -> None:
        self.client = client or get_supabase_client()
        self.usuario_id = str(usuario_id) if usuario_id else None

    def _escopo(self, consulta):
        if self.usuario_id:
            consulta = consulta.eq("usuario_id", self.usuario_id)
        return consulta

    def inserir(self, dados: dict) -> dict:
        if self.usuario_id:
            dados = {**dados, "usuario_id": self.usuario_id}
        return inserted_one(self.client.table("vendas").insert(to_db_payload(dados)).execute())

    def listar_por_dia(self, dia_de_venda_id: UUID | str) -> list[dict]:
        return (
            self._escopo(
                self.client.table("vendas")
                .select("*")
                .eq("dia_de_venda_id", str(dia_de_venda_id))
            )
            .order("ocorrido_em", desc=True)
            .execute()
            .data
        )

    def listar_ativas_por_dia(self, dia_de_venda_id: UUID | str) -> list[dict]:
        return (
            self._escopo(
                self.client.table("vendas")
                .select("id")
                .eq("dia_de_venda_id", str(dia_de_venda_id))
                .eq("situacao", "ativa")
            )
            .execute()
            .data
        )

    def buscar(self, venda_id: UUID | str) -> dict:
        venda = one_or_none(
            self._escopo(self.client.table("vendas").select("*").eq("id", str(venda_id)))
            .limit(1)
            .execute()
            .data
        )
        if not venda:
            raise NotFoundError("Venda", str(venda_id))
        return venda

    def cancelar(self, venda_id: UUID | str, dados: dict) -> dict:
        return updated_one(
            self._escopo(
                self.client.table("vendas")
                .update(to_db_payload(dados))
                .eq("id", str(venda_id))
            ).execute(),
            resource="Venda",
            resource_id=str(venda_id),
        )


class ItemVendaRepository:
    """Itens de venda herdam o escopo da venda ja validada pelo chamador."""

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase_client()

    def inserir_muitos(self, itens: list[dict]) -> None:
        self.client.table("itens_venda").insert([to_db_payload(item) for item in itens]).execute()

    def anexar_itens(self, vendas: list[dict]) -> list[dict]:
        venda_ids = [venda["id"] for venda in vendas]
        if not venda_ids:
            return []
        itens = (
            self.client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )
        itens_agrupados = defaultdict(list)
        for item in itens:
            itens_agrupados[item["venda_id"]].append(item)
        for venda in vendas:
            venda["itens"] = itens_agrupados[venda["id"]]
        return vendas

    def listar_quantidades_por_produto(
        self,
        venda_ids: list[str],
        produto_id: UUID | str,
    ) -> list[dict]:
        if not venda_ids:
            return []
        return (
            self.client.table("itens_venda")
            .select("quantidade")
            .in_("venda_id", venda_ids)
            .eq("produto_id", str(produto_id))
            .execute()
            .data
        )


class DisponibilidadeVendaRepository:
    """Producao e sobras herdam o escopo do dia ja validado pelo chamador."""

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase_client()

    def listar_itens_producao(
        self,
        dia_de_venda_id: UUID | str,
        produto_id: UUID | str,
    ) -> list[dict]:
        return (
            self.client.table("itens_producao")
            .select("quantidade_produzida")
            .eq("dia_de_venda_id", str(dia_de_venda_id))
            .eq("produto_id", str(produto_id))
            .execute()
            .data
        )

    def listar_decisoes_sobra(
        self,
        dia_de_venda_id: UUID | str,
        produto_id: UUID | str,
    ) -> list[dict]:
        return (
            self.client.table("decisoes_sobra")
            .select("quantidade_usada_hoje")
            .eq("dia_destino_id", str(dia_de_venda_id))
            .eq("produto_id", str(produto_id))
            .execute()
            .data
        )
