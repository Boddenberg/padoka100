from datetime import date
from uuid import UUID

from app.core.errors import NotFoundError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.payload import to_db_payload
from app.infra.supabase.result import inserted_one, one_or_none, updated_one
from supabase import Client


class ProdutoRepository:
    """Acesso a produtos sempre restrito ao dono informado.

    ``usuario_id`` e transicional-opcional enquanto os modulos consumidores
    migram para o modelo multiusuario; sem ele, nenhum filtro de dono e
    aplicado (comportamento legado).
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

    def listar_produtos(self, *, somente_ativos: bool) -> list[dict]:
        consulta = self._escopo(
            self.client.table("produtos").select("*").order("ordem_exibicao").order("nome")
        )
        if somente_ativos:
            consulta = consulta.eq("situacao", "ativo")
        return consulta.execute().data

    def buscar_produto(self, produto_id: UUID | str) -> dict:
        produto = one_or_none(
            self._escopo(self.client.table("produtos").select("*").eq("id", str(produto_id)))
            .limit(1)
            .execute()
            .data
        )
        if not produto:
            raise NotFoundError("Produto", str(produto_id))
        return produto

    def inserir_produto(self, dados: dict) -> dict:
        if self.usuario_id:
            dados = {**dados, "usuario_id": self.usuario_id}
        return inserted_one(self.client.table("produtos").insert(to_db_payload(dados)).execute())

    def atualizar_produto(self, produto_id: UUID | str, dados: dict) -> dict:
        return updated_one(
            self._escopo(
                self.client.table("produtos")
                .update(to_db_payload(dados))
                .eq("id", str(produto_id))
            ).execute(),
            resource="Produto",
            resource_id=str(produto_id),
        )

    def buscar_produto_por_slug(self, slug: str) -> dict | None:
        return one_or_none(
            self._escopo(self.client.table("produtos").select("id").eq("slug", slug))
            .limit(1)
            .execute()
            .data
        )


class PrecoProdutoRepository:
    """Versoes de preco sao escopadas pelo produto: quem constroi este
    repositorio precisa ter validado o dono do produto antes (via
    ``ProdutoRepository.buscar_produto``)."""

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_supabase_client()

    def listar_versoes(self, produto_id: UUID | str, *, desc: bool = False) -> list[dict]:
        return (
            self.client.table("versoes_preco_produto")
            .select("*")
            .eq("produto_id", str(produto_id))
            .order("vigente_desde", desc=desc)
            .execute()
            .data
        )

    def inserir(self, dados: dict) -> dict:
        return inserted_one(
            self.client.table("versoes_preco_produto").insert(to_db_payload(dados)).execute()
        )

    def atualizar_vigencia(self, preco_id: UUID | str, vigente_ate: date) -> None:
        (
            self.client.table("versoes_preco_produto")
            .update(to_db_payload({"vigente_ate": vigente_ate}))
            .eq("id", str(preco_id))
            .execute()
        )

    def buscar_vigente(
        self,
        produto_id: UUID | str,
        data_alvo: date,
        *,
        obrigatorio: bool,
    ) -> dict | None:
        preco = one_or_none(
            self.client.table("versoes_preco_produto")
            .select("*")
            .eq("produto_id", str(produto_id))
            .lte("vigente_desde", data_alvo.isoformat())
            .or_(f"vigente_ate.is.null,vigente_ate.gte.{data_alvo.isoformat()}")
            .order("vigente_desde", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if obrigatorio and not preco:
            raise NotFoundError("Preco vigente do produto", str(produto_id))
        return preco
