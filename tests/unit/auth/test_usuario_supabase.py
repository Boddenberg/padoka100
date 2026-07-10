from app.modules.auth.domain.usuario_supabase import montar_dados_usuario_supabase


def test_monta_dados_de_usuario_supabase_para_primeiro_dono():
    dados = montar_dados_usuario_supabase(
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

    assert dados["supabase_auth_id"] == "11111111-1111-1111-1111-111111111111"
    assert dados["email"] == "dona@padoka.com"
    assert dados["nome"] == "Dona Maria"
    assert dados["telefone"] == "(11) 99999-0000"
    assert dados["foto_url"] == "https://cdn.example/avatar.png"
    assert dados["papel"] == "dono"
    assert dados["situacao"] == "ativo"
    assert "senha_hash" not in dados


def test_monta_dados_de_usuario_supabase_para_usuario_comum():
    dados = montar_dados_usuario_supabase(
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "email": "atendente@padoka.com",
            "user_metadata": {"full_name": "Atendente Padoka"},
        },
        primeiro_usuario=False,
    )

    assert dados["nome"] == "Atendente Padoka"
    assert dados["papel"] == "usuario"


def test_nome_cai_para_email_sem_metadata():
    dados = montar_dados_usuario_supabase(
        {"id": "33333333-3333-3333-3333-333333333333", "email": "x@padoka.com"},
        primeiro_usuario=False,
    )
    assert dados["nome"] == "x@padoka.com"


def test_servico_reexporta_mapeamento_para_compatibilidade():
    from app.modules.auth import servico

    assert servico.montar_dados_usuario_supabase is montar_dados_usuario_supabase
