import unittest

from app.modules.auth import capacidades


class AccessPlansTests(unittest.TestCase):
    def test_plano_basico_libera_operacao_essencial(self):
        usuario = {"plano": "basico", "papel": "usuario"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertIn("vendas.operar", caps)
        self.assertIn("catalogo.editar", caps)
        self.assertIn("relatorios.basicos", caps)
        self.assertNotIn("relatorios.avancados", caps)
        self.assertNotIn("custos.usar", caps)
        self.assertNotIn("ia.operacional", caps)

    def test_plano_analitico_inclui_relatorios_e_custos_sem_ia(self):
        usuario = {"plano": "analitico", "papel": "usuario"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertIn("vendas.operar", caps)
        self.assertIn("relatorios.avancados", caps)
        self.assertIn("custos.usar", caps)
        self.assertNotIn("ia.operacional", caps)
        self.assertNotIn("ia.analitica", caps)

    def test_plano_ia_inclui_ia_operacional_e_analitica(self):
        usuario = {"plano": "ia", "papel": "usuario"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertIn("ia.operacional", caps)
        self.assertIn("ia.analitica", caps)
        self.assertIn("custos.assistente", caps)

    def test_admin_recebe_todas_as_capacidades(self):
        usuario = {"plano": "admin", "papel": "administrador"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertTrue(capacidades.usuario_tem_capacidade(usuario, "admin.gerenciar"))
        self.assertEqual(caps, capacidades.TODAS_CAPACIDADES)

    def test_dono_de_padaria_nao_vira_admin_interno_sem_plano_admin(self):
        usuario = {"plano": "basico", "papel": "dono"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertNotIn("admin.gerenciar", caps)
        self.assertEqual(caps, capacidades.CAPACIDADES_POR_PLANO["basico"])

    def test_plano_desconhecido_cai_para_basico(self):
        usuario = {"plano": "inexistente", "papel": "usuario"}

        caps = capacidades.capacidades_do_usuario(usuario)

        self.assertEqual(caps, capacidades.CAPACIDADES_POR_PLANO["basico"])


if __name__ == "__main__":
    unittest.main()
