"""Validacao de propriedade da entidade que recebe midia.

Regra central: um usuario so anexa midia a entidades da propria conta.
Entidades globais (notificacao) sao validadas pela capacidade admin na rota;
aqui apenas os tipos privados sao verificados.
"""

from uuid import UUID

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
from app.shared.db import first_or_none


def validar_propriedade_da_entidade(
    tipo_entidade: str,
    entidade_id: UUID | str,
    usuario_id: UUID | str | None,
) -> None:
    """Garante que a entidade alvo pertence ao usuario; NotFound caso contrario.

    Sem ``usuario_id`` (fluxos internos legados/admin) nenhuma checagem e
    aplicada — as rotas publicas sempre informam o usuario autenticado.
    """
    if not usuario_id:
        return

    validador = _VALIDADORES.get(tipo_entidade)
    if validador:
        validador(entidade_id, str(usuario_id))


def _validar_produto(entidade_id: UUID | str, usuario_id: str) -> None:
    from app.modules.produtos import public as produtos_public

    produtos_public.buscar_produto(UUID(str(entidade_id)), usuario_id=usuario_id)


def _validar_local(entidade_id: UUID | str, usuario_id: str) -> None:
    from app.modules.locais import servico as servico_de_locais

    servico_de_locais.buscar_local(entidade_id, usuario_id=usuario_id)


def _validar_dia_de_venda(entidade_id: UUID | str, usuario_id: str) -> None:
    from app.modules.dias_de_venda import servico as servico_de_dias

    servico_de_dias.buscar_linha_dia_de_venda(
        get_supabase_client(),
        entidade_id,
        usuario_id=usuario_id,
    )


def _validar_venda(entidade_id: UUID | str, usuario_id: str) -> None:
    from app.modules.vendas import servico as servico_de_vendas

    servico_de_vendas.buscar_venda(UUID(str(entidade_id)), usuario_id=usuario_id)


def _validar_usuario(entidade_id: UUID | str, usuario_id: str) -> None:
    if str(entidade_id) != usuario_id:
        raise NotFoundError("Usuario", str(entidade_id))


def _validar_interacao_ia(entidade_id: UUID | str, usuario_id: str) -> None:
    _validar_linha_com_dono("interacoes_ia", "Interacao de IA", entidade_id, usuario_id)


def _validar_sessao_custeio(entidade_id: UUID | str, usuario_id: str) -> None:
    _validar_linha_com_dono(
        "sessoes_custeio_assistido",
        "Sessao de custeio",
        entidade_id,
        usuario_id,
    )


def _validar_linha_com_dono(
    tabela: str,
    recurso: str,
    entidade_id: UUID | str,
    usuario_id: str,
) -> None:
    linha = first_or_none(
        get_supabase_client()
        .table(tabela)
        .select("id")
        .eq("id", str(entidade_id))
        .eq("usuario_id", usuario_id)
        .limit(1)
        .execute()
        .data
    )
    if not linha:
        raise NotFoundError(recurso, str(entidade_id))


_VALIDADORES = {
    "produto": _validar_produto,
    "local": _validar_local,
    "dia_de_venda": _validar_dia_de_venda,
    "venda": _validar_venda,
    "usuario": _validar_usuario,
    "interacao_ia": _validar_interacao_ia,
    "sessao_custeio": _validar_sessao_custeio,
}
