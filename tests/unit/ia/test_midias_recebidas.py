from app.modules.ia import midias_recebidas, servico
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"
INTERACAO = "33333333-3333-3333-3333-333333333333"
MIDIA = "44444444-4444-4444-4444-444444444444"


def test_listar_midias_recebidas_filtra_por_usuario_e_item(monkeypatch):
    cliente = ClienteFake(
        {
            "ia_midias_recebidas": [
                {
                    "id": MIDIA,
                    "usuario_id": USUARIO_A,
                    "usuario_nome_cadastrado": "Ana Padoka",
                    "item": "audio",
                    "interacao_ia_id": INTERACAO,
                    "midia_id": None,
                    "nome_arquivo": "comando.webm",
                    "url_publica": None,
                    "tipo_conteudo": "audio/webm",
                    "criado_em": "2026-07-13T12:00:00+00:00",
                }
            ]
        }
    )
    monkeypatch.setattr(midias_recebidas, "get_supabase_client", lambda: cliente)

    resultado = servico.listar_midias_recebidas_por_ia(
        item="audio",
        usuario_id=USUARIO_A,
    )

    consulta = consulta_da_tabela(cliente, "ia_midias_recebidas")
    assert ("item", "audio") in consulta.filtros
    assert ("usuario_id", USUARIO_A) in consulta.filtros
    assert resultado == [
        {
            "id": MIDIA,
            "usuario_id": USUARIO_A,
            "usuario_nome_cadastrado": "Ana Padoka",
            "data": "2026-07-13T12:00:00+00:00",
            "item": "audio",
            "interacao_ia_id": INTERACAO,
            "midia_id": None,
            "nome_arquivo": "comando.webm",
            "url_publica": None,
            "tipo_conteudo": "audio/webm",
        }
    ]


def test_registrar_midia_recebida_grava_snapshot_do_usuario(monkeypatch):
    cliente = ClienteFake()
    monkeypatch.setattr(midias_recebidas, "get_supabase_client", lambda: cliente)

    midias_recebidas.registrar(
        item="foto",
        usuario_id=USUARIO_A,
        usuario_nome="Ana Padoka",
        interacao_ia_id=INTERACAO,
        midia_id=MIDIA,
        nome_arquivo="cardapio.jpg",
        url_publica="https://storage.local/cardapio.jpg",
        tipo_conteudo="image/jpeg",
    )

    consulta = consulta_da_tabela(cliente, "ia_midias_recebidas")
    assert consulta.operacao == "insert"
    assert consulta.payload == {
        "usuario_id": USUARIO_A,
        "usuario_nome_cadastrado": "Ana Padoka",
        "item": "foto",
        "interacao_ia_id": INTERACAO,
        "midia_id": MIDIA,
        "nome_arquivo": "cardapio.jpg",
        "url_publica": "https://storage.local/cardapio.jpg",
        "tipo_conteudo": "image/jpeg",
    }
