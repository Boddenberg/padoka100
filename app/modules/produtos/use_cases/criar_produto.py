from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)
from app.modules.produtos.domain.price_origin import normalizar_origem_preco
from app.modules.produtos.domain.slug import criar_slug_unico
from app.modules.produtos.esquemas import RequisicaoCriarProduto
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def criar_produto(
    requisicao: RequisicaoCriarProduto,
    *,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    origem_preco, gerado_por_ia = normalizar_origem_preco(
        requisicao.origem_preco,
        requisicao.gerado_por_ia,
    )
    produto = repo.inserir_produto(
        {
            "nome": requisicao.nome,
            "slug": criar_slug_unico(
                requisicao.nome,
                buscar_por_slug=repo.buscar_produto_por_slug,
            ),
            "descricao": requisicao.descricao,
            "descricao_visual": requisicao.descricao_visual,
            "url_imagem_principal": requisicao.url_imagem_principal,
            "cor_botao": requisicao.cor_botao,
            "ordem_exibicao": requisicao.ordem_exibicao,
            "situacao": "ativo",
        }
    )
    preco = preco_repo.inserir(
        {
            "produto_id": produto["id"],
            "preco_venda": requisicao.preco_venda,
            "preco_custo": requisicao.preco_custo,
            "vigente_desde": requisicao.vigente_desde,
            "motivo": requisicao.motivo_preco,
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
        }
    )
    registrar_evento_na_linha_do_tempo(
        repo.client,
        tipo_evento="produto_criado",
        titulo=f"Produto criado: {produto['nome']}",
        tipo_entidade="produto",
        entidade_id=produto["id"],
        detalhes={"preco_inicial": preco},
    )
    produto["preco_atual"] = preco
    return produto
