from uuid import UUID

from app.core.errors import ConflictError
from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)
from app.modules.produtos.domain.price_origin import normalizar_origem_preco
from app.modules.produtos.domain.pricing import (
    buscar_preco_anterior,
    buscar_proximo_preco,
    calcular_vigencia_ate_da_nova_versao,
    calcular_vigencia_ate_da_versao_anterior,
    preco_cobre_data,
)
from app.modules.produtos.esquemas import RequisicaoCriarVersaoDePreco
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def criar_versao_de_preco(
    produto_id: UUID,
    requisicao: RequisicaoCriarVersaoDePreco,
    *,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    produto = repo.buscar_produto(produto_id)
    versoes_existentes = preco_repo.listar_versoes(produto_id)
    if any(
        versao["vigente_desde"] == requisicao.vigente_desde.isoformat()
        for versao in versoes_existentes
    ):
        raise ConflictError(
            "Ja existe um preco cadastrado para esse produto nessa data.",
            {"produto_id": str(produto_id), "vigente_desde": requisicao.vigente_desde.isoformat()},
        )

    origem_preco, gerado_por_ia = normalizar_origem_preco(
        requisicao.origem,
        requisicao.gerado_por_ia,
    )
    versao_anterior = buscar_preco_anterior(versoes_existentes, requisicao.vigente_desde)
    proxima_versao = buscar_proximo_preco(versoes_existentes, requisicao.vigente_desde)
    nova_vigencia_ate = calcular_vigencia_ate_da_nova_versao(proxima_versao)
    if versao_anterior and preco_cobre_data(versao_anterior, requisicao.vigente_desde):
        preco_repo.atualizar_vigencia(
            versao_anterior["id"],
            calcular_vigencia_ate_da_versao_anterior(requisicao.vigente_desde),
        )

    preco = preco_repo.inserir(
        {
            "produto_id": produto_id,
            "preco_venda": requisicao.preco_venda,
            "preco_custo": requisicao.preco_custo,
            "vigente_desde": requisicao.vigente_desde,
            "vigente_ate": nova_vigencia_ate,
            "motivo": requisicao.motivo,
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
        }
    )
    registrar_evento_na_linha_do_tempo(
        repo.client,
        tipo_evento="preco_produto_alterado",
        titulo=f"Preco alterado: {produto['nome']}",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={
            "novo_preco": preco,
            "vigente_desde": requisicao.vigente_desde.isoformat(),
            "motivo": requisicao.motivo,
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
        },
    )
    return preco
