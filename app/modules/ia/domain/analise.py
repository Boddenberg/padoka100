"""Analise local pura de periodo de vendas.

Gera a analise estruturada padrao a partir dos dados consolidados e
normaliza a resposta de texto/JSON vinda da IA, sem depender de OpenAI.
"""

import json
import re
from decimal import Decimal

from app.modules.ia.domain.texto import formatar_data


def normalizar_analise_estruturada(
    dados: dict,
    analise_texto: str,
    *,
    pergunta: str | None,
) -> dict:
    estrutura = gerar_analise_estruturada_local(dados, pergunta)
    extraida = extrair_json_da_analise(analise_texto)
    if extraida:
        campos_extraidos = normalizar_campos_da_analise(extraida)
        analise_extraida = campos_extraidos.pop("analise", "")
        for campo, valor in campos_extraidos.items():
            if valor:
                estrutura[campo] = valor
        estrutura["analise"] = analise_extraida or montar_texto_da_analise_estruturada(estrutura)
    elif analise_texto:
        estrutura["analise"] = analise_texto

    if not estrutura.get("analise"):
        estrutura["analise"] = montar_texto_da_analise_estruturada(estrutura)
    return estrutura


def extrair_json_da_analise(texto: str) -> dict:
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return {}
    if texto_limpo.startswith("```"):
        texto_limpo = re.sub(r"^```(?:json)?", "", texto_limpo, flags=re.IGNORECASE).strip()
        texto_limpo = re.sub(r"```$", "", texto_limpo).strip()
    try:
        resultado = json.loads(texto_limpo)
    except json.JSONDecodeError:
        inicio = texto_limpo.find("{")
        fim = texto_limpo.rfind("}")
        if inicio < 0 or fim <= inicio:
            return {}
        try:
            resultado = json.loads(texto_limpo[inicio : fim + 1])
        except json.JSONDecodeError:
            return {}
    return resultado if isinstance(resultado, dict) else {}


def normalizar_campos_da_analise(dados: dict) -> dict:
    estrutura = {
        "resumo": normalizar_texto(dados.get("resumo")),
        "principais_achados": normalizar_lista_de_textos(dados.get("principais_achados")),
        "mais_venderam": normalizar_lista_de_objetos(dados.get("mais_venderam")),
        "mais_sobraram": normalizar_lista_de_objetos(dados.get("mais_sobraram")),
        "sugestoes": normalizar_lista_de_textos(dados.get("sugestoes")),
        "pontos_atencao": normalizar_lista_de_textos(dados.get("pontos_atencao")),
    }
    analise = normalizar_texto(dados.get("analise"))
    if analise:
        estrutura["analise"] = analise
    return estrutura


def normalizar_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor.strip()
    return str(valor).strip()


def normalizar_lista_de_textos(valor) -> list[str]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        valor = [valor]
    return [texto for item in valor if (texto := normalizar_texto(item))]


def normalizar_lista_de_objetos(valor) -> list[dict]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        valor = [valor]
    itens = []
    for item in valor:
        if isinstance(item, dict):
            itens.append(item)
        elif texto := normalizar_texto(item):
            itens.append({"descricao": texto})
    return itens


def rotulo_periodo_da_analise(dados: dict) -> str:
    periodo = dados.get("periodo") or {}
    rotulo = normalizar_texto(periodo.get("rotulo"))
    if rotulo:
        return rotulo

    inicio = periodo.get("inicio")
    fim = periodo.get("fim")
    if inicio and fim:
        return f"{formatar_data(str(inicio))} a {formatar_data(str(fim))}"
    return "periodo informado"


def gerar_analise_estruturada_local(dados: dict, pergunta: str | None) -> dict:
    produtos = dados["produtos"]
    produtos_mais_vendidos = [
        {
            "produto_id": produto["produtoId"],
            "produto": produto["produto"],
            "quantidade_vendida": produto["totalVendido"],
            "faturamento": produto["faturamento"],
        }
        for produto in sorted(produtos, key=lambda item: item["totalVendido"], reverse=True)
        if produto["totalVendido"] > 0
    ][:5]
    produtos_mais_sobraram = [
        {
            "produto_id": produto["produtoId"],
            "produto": produto["produto"],
            "quantidade_sobra": produto["totalSobrando"],
        }
        for produto in sorted(produtos, key=lambda item: item["totalSobrando"], reverse=True)
        if produto["totalSobrando"] > 0
    ][:5]
    dias = dados.get("dias", [])
    produtos_esgotados = [
        nome
        for dia in dias
        for nome in dia.get("produtosEsgotados", [])
    ]
    periodo = rotulo_periodo_da_analise(dados)
    resumo = (
        f"Periodo de {periodo}: "
        f"faturamento total de R$ {Decimal(str(dados['faturamentoTotal'])):.2f}, "
        f"{dados['quantidadeTotalVendida']} unidades vendidas e "
        f"{dados['quantidadeTotalSobrando']} unidades sobrando."
    )
    principais_achados = [
        f"Total produzido: {dados['quantidadeTotalProduzida']} unidades.",
        f"Total vendido: {dados['quantidadeTotalVendida']} unidades.",
        f"Total sobrando: {dados['quantidadeTotalSobrando']} unidades.",
    ]
    if produtos_mais_vendidos:
        produto = produtos_mais_vendidos[0]
        principais_achados.append(
            "Produto mais vendido: "
            f"{produto['produto']} ({produto['quantidade_vendida']} unidades)."
        )
    if produtos_mais_sobraram:
        produto = produtos_mais_sobraram[0]
        principais_achados.append(
            f"Maior sobra: {produto['produto']} ({produto['quantidade_sobra']} unidades)."
        )

    sugestoes = []
    if produtos_mais_sobraram:
        produto = produtos_mais_sobraram[0]
        sugestoes.append(
            f"Revisar a producao de {produto['produto']}, que concentrou a maior sobra."
        )
    if produtos_mais_vendidos:
        produto = produtos_mais_vendidos[0]
        sugestoes.append(
            f"Manter atencao em {produto['produto']}, que teve a maior venda no periodo."
        )
    if not sugestoes:
        sugestoes.append("Registrar mais dias de venda para gerar sugestoes mais confiaveis.")

    pontos_atencao = []
    if dados["correcoesRetroativas"]:
        pontos_atencao.append("Ha correcoes retroativas no periodo analisado.")
    if produtos_esgotados:
        nomes_esgotados = sorted(set(produtos_esgotados))
        pontos_atencao.append(
            "Produtos esgotados no periodo: " + ", ".join(nomes_esgotados) + "."
        )
    if pergunta:
        pontos_atencao.append(
            "A pergunta especifica foi considerada, mas a analise local nao interpreta "
            "filtros livres com a mesma profundidade da IA configurada."
        )

    estrutura = {
        "resumo": resumo,
        "principais_achados": principais_achados,
        "mais_venderam": produtos_mais_vendidos,
        "mais_sobraram": produtos_mais_sobraram,
        "sugestoes": sugestoes,
        "pontos_atencao": pontos_atencao,
    }
    estrutura["analise"] = montar_texto_da_analise_estruturada(estrutura)
    return estrutura


def montar_texto_da_analise_estruturada(estrutura: dict) -> str:
    partes = [normalizar_texto(estrutura.get("resumo"))]
    secoes = [
        ("Principais achados", estrutura.get("principais_achados")),
        ("Sugestoes", estrutura.get("sugestoes")),
        ("Pontos de atencao", estrutura.get("pontos_atencao")),
    ]
    for titulo, itens in secoes:
        textos = normalizar_lista_de_textos(itens)
        if textos:
            partes.append(f"{titulo}: " + " ".join(textos))
    return " ".join(parte for parte in partes if parte)


def gerar_analise_local(dados: dict, pergunta: str | None) -> str:
    produtos = dados["produtos"]
    produto_mais_vendido = produtos[0] if produtos else None
    produto_mais_sobra = max(produtos, key=lambda produto: produto["totalSobrando"], default=None)
    periodo = rotulo_periodo_da_analise(dados)
    partes = [
        f"Periodo analisado: {periodo}.",
        f"Faturamento total: R$ {Decimal(str(dados['faturamentoTotal'])):.2f}.",
        f"Total produzido: {dados['quantidadeTotalProduzida']}.",
        f"Total vendido: {dados['quantidadeTotalVendida']}.",
        f"Total sobrando: {dados['quantidadeTotalSobrando']}.",
    ]
    if produto_mais_vendido:
        partes.append(
            "Produto mais vendido: "
            f"{produto_mais_vendido['produto']} ({produto_mais_vendido['totalVendido']} unidades)."
        )
    if produto_mais_sobra:
        partes.append(
            "Produto com maior sobra: "
            f"{produto_mais_sobra['produto']} ({produto_mais_sobra['totalSobrando']} unidades)."
        )
    if dados["correcoesRetroativas"]:
        partes.append("Ha correcoes retroativas no periodo; revise os dias corrigidos.")
    if pergunta:
        partes.append(
            "A pergunta especifica foi registrada, mas a analise local nao interpreta filtros "
            "em linguagem natural. Configure OpenAI para resposta contextual completa."
        )
    return " ".join(partes)
