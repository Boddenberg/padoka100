from tests.integration.conftest import API_KEY_DE_TESTE, registrar_e_logar

ADMIN_HEADERS = {"X-API-Key": API_KEY_DE_TESTE}


def test_usuario_cria_report_e_admin_lista_com_remetente(client, banco):
    usuario = registrar_e_logar(client, "reporter@padoka.com", "Maria Reporter")

    criar = client.post(
        "/api/v1/reports",
        data={
            "tipo": "erro",
            "mensagem": "O botao de fechar o dia nao funciona.",
            "contexto": "Venda",
        },
        files={"arquivos": ("print.png", b"conteudo-fake", "image/png")},
        headers=usuario["headers"],
    )
    assert criar.status_code == 201, criar.text
    corpo = criar.json()
    assert corpo["tipo"] == "erro"
    assert corpo["status"] == "novo"
    assert corpo["mensagem"] == "O botao de fechar o dia nao funciona."
    assert len(corpo["anexos"]) == 1
    assert corpo["anexos"][0]["tipo"] == "imagem"

    lista = client.get("/api/v1/admin/reports", headers=ADMIN_HEADERS)
    assert lista.status_code == 200, lista.text
    reports = lista.json()
    assert len(reports) == 1
    report = reports[0]
    assert report["usuario_nome"] == "Maria Reporter"
    assert report["usuario_email"] == "reporter@padoka.com"
    assert report["contexto"] == "Venda"
    assert len(report["anexos"]) == 1

    report_id = report["id"]
    atualizar = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={"status": "resolvido"},
        headers=ADMIN_HEADERS,
    )
    assert atualizar.status_code == 200, atualizar.text
    assert atualizar.json()["status"] == "resolvido"


def test_report_sem_mensagem_e_sem_anexo_e_rejeitado(client, banco):
    usuario = registrar_e_logar(client, "vazio@padoka.com", "Vazio")
    resposta = client.post(
        "/api/v1/reports",
        data={"tipo": "recado"},
        headers=usuario["headers"],
    )
    assert resposta.status_code == 400, resposta.text


def test_report_exige_sessao_de_usuario(client, banco):
    # X-API-Key nao representa uma conta de verdade: report exige sessao de usuario.
    resposta = client.post(
        "/api/v1/reports",
        data={"tipo": "recado", "mensagem": "oi"},
        headers=ADMIN_HEADERS,
    )
    assert resposta.status_code == 403, resposta.text


def test_admin_reports_exige_capacidade(client, banco):
    usuario = registrar_e_logar(client, "comum@padoka.com", "Comum")
    resposta = client.get("/api/v1/admin/reports", headers=usuario["headers"])
    assert resposta.status_code == 403, resposta.text
