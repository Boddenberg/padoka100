import unittest

from app.modules.auth import servico


class SupabaseAuthProfileTests(unittest.TestCase):
    def test_monta_dados_de_usuario_supabase_para_primeiro_dono(self):
        dados = servico.montar_dados_usuario_supabase(
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": " DONA@PADOKA.COM ",
                "user_metadata": {
                    "name": "Dona Maria",
                    "phone": "(11) 99999-0000",
                    "avatar_url": "https://cdn.example/avatar.png",
                },
            },
            primeiro_usuario=True,
        )

        self.assertEqual(dados["supabase_auth_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(dados["email"], "dona@padoka.com")
        self.assertEqual(dados["nome"], "Dona Maria")
        self.assertEqual(dados["telefone"], "(11) 99999-0000")
        self.assertEqual(dados["foto_url"], "https://cdn.example/avatar.png")
        self.assertEqual(dados["papel"], "dono")
        self.assertEqual(dados["situacao"], "ativo")
        self.assertNotIn("senha_hash", dados)

    def test_monta_dados_de_usuario_supabase_para_usuario_comum(self):
        dados = servico.montar_dados_usuario_supabase(
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "email": "atendente@padoka.com",
                "user_metadata": {"full_name": "Atendente Padoka"},
            },
            primeiro_usuario=False,
        )

        self.assertEqual(dados["nome"], "Atendente Padoka")
        self.assertEqual(dados["papel"], "usuario")


if __name__ == "__main__":
    unittest.main()
