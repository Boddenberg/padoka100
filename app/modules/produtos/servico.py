from datetime import date
from uuid import UUID

from app.modules.produtos.domain.formatting import (
    formatar_produtos_para_lista_http as formatar_produtos_para_lista_http_domain,
)
from app.modules.produtos.esquemas import (
    RequisicaoAtualizarProduto,
    RequisicaoCriarProduto,
    RequisicaoCriarVersaoDePreco,
)
from app.modules.produtos.use_cases.atualizar_produto import (
    atualizar_produto as atualizar_produto_use_case,
)
from app.modules.produtos.use_cases.buscar_preco_vigente import (
    buscar_preco_vigente as buscar_preco_vigente_use_case,
)
from app.modules.produtos.use_cases.buscar_produto import buscar_produto as buscar_produto_use_case
from app.modules.produtos.use_cases.buscar_snapshot import (
    buscar_snapshot_do_produto as buscar_snapshot_do_produto_use_case,
)
from app.modules.produtos.use_cases.criar_produto import criar_produto as criar_produto_use_case
from app.modules.produtos.use_cases.criar_versao_de_preco import (
    criar_versao_de_preco as criar_versao_de_preco_use_case,
)
from app.modules.produtos.use_cases.listar_produtos import (
    listar_produtos as listar_produtos_use_case,
)
from app.modules.produtos.use_cases.listar_versoes_de_preco import (
    listar_versoes_de_preco as listar_versoes_de_preco_use_case,
)


def listar_produtos(
    *,
    somente_ativos: bool = True,
    data_preco: date | None = None,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    return listar_produtos_use_case(
        somente_ativos=somente_ativos,
        data_preco=data_preco,
        usuario_id=usuario_id,
    )


def formatar_produtos_para_lista_http(
    produtos: list[dict],
    *,
    somente_ativos: bool,
) -> list[dict]:
    return formatar_produtos_para_lista_http_domain(
        produtos,
        somente_ativos=somente_ativos,
    )


def buscar_produto(
    produto_id: UUID,
    *,
    data_preco: date | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    return buscar_produto_use_case(produto_id, data_preco=data_preco, usuario_id=usuario_id)


def criar_produto(
    requisicao: RequisicaoCriarProduto,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    return criar_produto_use_case(requisicao, usuario_id=usuario_id)


def atualizar_produto(
    produto_id: UUID,
    requisicao: RequisicaoAtualizarProduto,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    return atualizar_produto_use_case(produto_id, requisicao, usuario_id=usuario_id)


def listar_versoes_de_preco(
    produto_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    return listar_versoes_de_preco_use_case(produto_id, usuario_id=usuario_id)


def criar_versao_de_preco(
    produto_id: UUID,
    requisicao: RequisicaoCriarVersaoDePreco,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    return criar_versao_de_preco_use_case(produto_id, requisicao, usuario_id=usuario_id)


def buscar_preco_vigente(produto_id: UUID | str, data_alvo: date) -> dict:
    return buscar_preco_vigente_use_case(produto_id, data_alvo)


def buscar_snapshot_do_produto(
    produto_id: UUID | str,
    data_alvo: date,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    return buscar_snapshot_do_produto_use_case(produto_id, data_alvo, usuario_id=usuario_id)
