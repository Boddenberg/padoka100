from typing import Final

PLANO_BASICO: Final = "basico"
PLANO_ANALITICO: Final = "analitico"
PLANO_IA: Final = "ia"
PLANO_ADMIN: Final = "admin"

PLANOS_VALIDOS: Final = (PLANO_BASICO, PLANO_ANALITICO, PLANO_IA, PLANO_ADMIN)

CAPACIDADES_BASICAS: Final = frozenset(
    {
        "perfil.editar",
        "notificacoes.ler",
        "catalogo.ler",
        "catalogo.editar",
        "dias.operar",
        "vendas.operar",
        "relatorios.basicos",
        "midia.enviar",
    }
)

CAPACIDADES_ANALITICAS: Final = CAPACIDADES_BASICAS | frozenset(
    {
        "historico.ler",
        "relatorios.avancados",
        "custos.usar",
        "compras.usar",
    }
)

CAPACIDADES_IA: Final = CAPACIDADES_ANALITICAS | frozenset(
    {
        "ia.operacional",
        "ia.analitica",
        "custos.assistente",
    }
)

CAPACIDADES_ADMIN: Final = CAPACIDADES_IA | frozenset(
    {
        "admin.gerenciar",
        "usuarios.gerenciar",
        "notificacoes.admin",
        "rag.gerenciar",
        "seed.gerar",
    }
)

CAPACIDADES_POR_PLANO: Final = {
    PLANO_BASICO: CAPACIDADES_BASICAS,
    PLANO_ANALITICO: CAPACIDADES_ANALITICAS,
    PLANO_IA: CAPACIDADES_IA,
    PLANO_ADMIN: CAPACIDADES_ADMIN,
}

TODAS_CAPACIDADES: Final = CAPACIDADES_ADMIN


def plano_do_usuario(usuario: dict | None) -> str:
    plano = str((usuario or {}).get("plano") or PLANO_BASICO).strip().lower()
    return plano if plano in CAPACIDADES_POR_PLANO else PLANO_BASICO


def capacidades_do_usuario(usuario: dict | None) -> frozenset[str]:
    papel = str((usuario or {}).get("papel") or "").strip().lower()
    plano = plano_do_usuario(usuario)
    if plano == PLANO_ADMIN or papel == "administrador":
        return TODAS_CAPACIDADES
    return CAPACIDADES_POR_PLANO[plano]


def usuario_tem_capacidade(usuario: dict | None, capacidade: str) -> bool:
    return capacidade in capacidades_do_usuario(usuario)
