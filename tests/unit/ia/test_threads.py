from app.modules.ia import servico, threads
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"
INTERACAO_1 = "33333333-3333-3333-3333-333333333333"
INTERACAO_2 = "33333333-3333-3333-3333-333333333334"
MIDIA = "44444444-4444-4444-4444-444444444444"
THREAD = "55555555-5555-5555-5555-555555555555"


def test_listar_threads_agrupa_interacoes_e_midias(monkeypatch):
    cliente = ClienteFake(
        {
            "interacoes_ia": [
                {
                    "id": INTERACAO_2,
                    "thread_id": THREAD,
                    "usuario_id": USUARIO_A,
                    "tipo_entrada": "audio",
                    "texto_original": "cadastre pao de sal por um real",
                    "acao_interpretada": {"acao": "criar_produto"},
                    "dados_confirmacao": {
                        "acao": "criar_produto",
                        "precisa_confirmacao": True,
                        "mensagem_confirmacao": (
                            "Entendi que devo cadastrar pao de sal por R$ 1,00. Confirma?"
                        ),
                    },
                    "situacao": "confirmada",
                    "resolvido_em": "2026-07-13T12:02:00+00:00",
                    "criado_em": "2026-07-13T12:01:00+00:00",
                },
                {
                    "id": INTERACAO_1,
                    "thread_id": THREAD,
                    "usuario_id": USUARIO_A,
                    "tipo_entrada": "audio",
                    "texto_original": "cadastro pao por real",
                    "acao_interpretada": {
                        "acao": "desconhecido",
                        "mensagem_assistente": "Nao entendi com seguranca.",
                    },
                    "dados_confirmacao": {
                        "acao": "desconhecido",
                        "precisa_confirmacao": False,
                        "mensagem_confirmacao": "Nao entendi com seguranca.",
                    },
                    "situacao": "rejeitada",
                    "motivo_rejeicao": "Resposta ficou nada a ver",
                    "resolvido_em": "2026-07-13T12:00:30+00:00",
                    "criado_em": "2026-07-13T12:00:00+00:00",
                },
            ],
            "ia_midias_recebidas": [
                {
                    "id": MIDIA,
                    "thread_id": THREAD,
                    "usuario_id": USUARIO_A,
                    "usuario_nome_cadastrado": "Ana Padoka",
                    "item": "audio",
                    "interacao_ia_id": INTERACAO_2,
                    "midia_id": None,
                    "nome_arquivo": "audio.webm",
                    "url_publica": "https://storage.local/audio.webm",
                    "tipo_conteudo": "audio/webm",
                    "resposta_ia": "Entendi que devo cadastrar pao de sal por R$ 1,00. Confirma?",
                    "criado_em": "2026-07-13T12:01:10+00:00",
                }
            ],
        }
    )
    monkeypatch.setattr(threads, "get_supabase_client", lambda: cliente)

    resultado = servico.listar_threads_de_ia(thread_id=THREAD, usuario_id=USUARIO_A)

    consulta_interacoes = consulta_da_tabela(cliente, "interacoes_ia")
    assert ("thread_id", THREAD) in consulta_interacoes.filtros
    assert ("usuario_id", USUARIO_A) in consulta_interacoes.filtros
    assert resultado[0]["thread_id"] == THREAD
    assert resultado[0]["desfecho"] == "confirmada"
    assert resultado[0]["total_interacoes"] == 2
    assert resultado[0]["total_midias"] == 1
    assert resultado[0]["usuario_nome_cadastrado"] == "Ana Padoka"
    assert resultado[0]["interacoes"][0]["situacao"] == "rejeitada"
    assert resultado[0]["interacoes"][1]["midias"][0]["id"] == MIDIA


def test_rejeitar_comando_marca_interacao_com_motivo(monkeypatch):
    cliente = ClienteFake(
        {
            "interacoes_ia": [
                {
                    "id": INTERACAO_1,
                    "thread_id": THREAD,
                    "usuario_id": USUARIO_A,
                    "tipo_entrada": "texto",
                    "texto_original": "cadastre pao",
                    "dados_confirmacao": {
                        "acao": "criar_produto",
                        "precisa_confirmacao": True,
                    },
                    "situacao": "interpretada",
                    "criado_em": "2026-07-13T12:00:00+00:00",
                }
            ]
        }
    )
    monkeypatch.setattr(servico, "get_supabase_client", lambda: cliente)

    resultado = servico.rejeitar_comando(
        INTERACAO_1,
        motivo="Resposta ficou errada",
        usuario_id=USUARIO_A,
    )

    consulta_update = cliente.consultas[-1]
    assert consulta_update.tabela == "interacoes_ia"
    assert consulta_update.payload["situacao"] == "rejeitada"
    assert consulta_update.payload["motivo_rejeicao"] == "Resposta ficou errada"
    assert "resolvido_em" in consulta_update.payload
    assert resultado["thread_id"] == THREAD
    assert resultado["resultado"]["rejeitada"] is True
