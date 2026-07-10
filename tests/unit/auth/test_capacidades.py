from app.modules.auth.domain.capacidades import (
    CAPACIDADES_POR_PLANO,
    TODAS_CAPACIDADES,
    capacidades_do_usuario,
    usuario_tem_capacidade,
)


def test_plano_basico_libera_operacao_essencial():
    caps = capacidades_do_usuario({"plano": "basico", "papel": "usuario"})

    assert "vendas.operar" in caps
    assert "catalogo.editar" in caps
    assert "relatorios.basicos" in caps
    assert "relatorios.avancados" not in caps
    assert "custos.usar" not in caps
    assert "ia.operacional" not in caps


def test_plano_analitico_inclui_relatorios_e_custos_sem_ia():
    caps = capacidades_do_usuario({"plano": "analitico", "papel": "usuario"})

    assert "vendas.operar" in caps
    assert "relatorios.avancados" in caps
    assert "custos.usar" in caps
    assert "ia.operacional" not in caps
    assert "ia.analitica" not in caps


def test_plano_ia_inclui_ia_operacional_e_analitica():
    caps = capacidades_do_usuario({"plano": "ia", "papel": "usuario"})

    assert "ia.operacional" in caps
    assert "ia.analitica" in caps
    assert "custos.assistente" in caps


def test_admin_recebe_todas_as_capacidades():
    usuario = {"plano": "admin", "papel": "administrador"}

    assert usuario_tem_capacidade(usuario, "admin.gerenciar")
    assert capacidades_do_usuario(usuario) == TODAS_CAPACIDADES


def test_dono_de_padaria_nao_vira_admin_interno_sem_plano_admin():
    caps = capacidades_do_usuario({"plano": "basico", "papel": "dono"})

    assert "admin.gerenciar" not in caps
    assert caps == CAPACIDADES_POR_PLANO["basico"]


def test_plano_desconhecido_cai_para_basico():
    caps = capacidades_do_usuario({"plano": "inexistente", "papel": "usuario"})

    assert caps == CAPACIDADES_POR_PLANO["basico"]
