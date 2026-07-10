from app.modules.ia.domain.analise import (
    extrair_json_da_analise,
    gerar_analise_estruturada_local,
    gerar_analise_local,
    normalizar_analise_estruturada,
    rotulo_periodo_da_analise,
)

DADOS = {
    "periodo": {"inicio": "2026-01-01", "fim": "2026-01-07"},
    "faturamentoTotal": "150.50",
    "quantidadeTotalProduzida": 100,
    "quantidadeTotalVendida": 80,
    "quantidadeTotalSobrando": 20,
    "correcoesRetroativas": [],
    "produtos": [
        {
            "produtoId": "p1",
            "produto": "Pao Frances",
            "totalVendido": 50,
            "totalSobrando": 5,
            "faturamento": "75.00",
        },
        {
            "produtoId": "p2",
            "produto": "Bolo",
            "totalVendido": 30,
            "totalSobrando": 15,
            "faturamento": "75.50",
        },
    ],
    "dias": [{"produtosEsgotados": ["Pao Frances"]}],
}


def test_extrair_json_da_analise_aceita_cerca_de_codigo():
    assert extrair_json_da_analise('```json\n{"resumo": "ok"}\n```') == {"resumo": "ok"}
    assert extrair_json_da_analise('prefixo {"a": 1} sufixo') == {"a": 1}
    assert extrair_json_da_analise("sem json") == {}
    assert extrair_json_da_analise("") == {}


def test_rotulo_periodo_usa_datas_formatadas():
    assert rotulo_periodo_da_analise(DADOS) == "01/01/2026 a 07/01/2026"
    assert rotulo_periodo_da_analise({"periodo": {"rotulo": "semana 1"}}) == "semana 1"
    assert rotulo_periodo_da_analise({}) == "periodo informado"


def test_analise_estruturada_local_ordena_e_resume():
    estrutura = gerar_analise_estruturada_local(DADOS, None)
    assert estrutura["mais_venderam"][0]["produto"] == "Pao Frances"
    assert estrutura["mais_sobraram"][0]["produto"] == "Bolo"
    assert "faturamento total de R$ 150.50" in estrutura["resumo"]
    assert any("esgotados" in ponto for ponto in estrutura["pontos_atencao"])
    assert estrutura["analise"]


def test_analise_estruturada_local_com_pergunta_gera_aviso():
    estrutura = gerar_analise_estruturada_local(DADOS, "qual o melhor dia?")
    assert any("pergunta especifica" in ponto for ponto in estrutura["pontos_atencao"])


def test_normalizar_analise_mescla_json_da_ia():
    texto_ia = '{"resumo": "Resumo da IA", "sugestoes": ["fazer mais pao"]}'
    estrutura = normalizar_analise_estruturada(DADOS, texto_ia, pergunta=None)
    assert estrutura["resumo"] == "Resumo da IA"
    assert estrutura["sugestoes"] == ["fazer mais pao"]
    # campos nao presentes no JSON continuam vindo da analise local
    assert estrutura["mais_venderam"][0]["produto"] == "Pao Frances"


def test_normalizar_analise_texto_livre_vira_analise():
    estrutura = normalizar_analise_estruturada(DADOS, "texto corrido da IA", pergunta=None)
    assert estrutura["analise"] == "texto corrido da IA"


def test_gerar_analise_local_texto():
    texto = gerar_analise_local(DADOS, None)
    assert "Faturamento total: R$ 150.50." in texto
    assert "Pao Frances" in texto
