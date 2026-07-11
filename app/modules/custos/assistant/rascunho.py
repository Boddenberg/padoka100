"""Normalizacao e mesclagem pura do rascunho de custeio do assistente."""

import re
from decimal import Decimal
from uuid import UUID

from app.modules.custos.assistant.ingredientes import (
    APLICACOES_CUSTO,
    chave_custo_adicional,
    escolher_nome_ingrediente,
    extrair_numeros_de_texto,
    inferir_unidade_da_quantidade_ambigua,
    nomes_ingredientes_compativeis,
    status_de_custo,
    tem_algum_dado_de_compra,
    texto_indica_quantidade_alternativa,
    tipo_custo_adicional,
)
from app.modules.custos.assistant.valores import (
    decimal_ou_none,
    decimal_str_limpa,
    decimal_str_ou_none,
    deduplicar_textos,
    float_ou_none,
    lista_de_textos,
    lista_ou_vazia,
    normalizar_chave,
    normalizar_unidade_de_entrada,
    normalizar_unidade_texto,
    texto_ou_none,
    uuid_str_ou_none,
)


def normalizar_rascunho(
    dados: dict | None,
    *,
    produto_id: UUID | str | None = None,
    contexto: str | None = None,
) -> dict:
    dados = dados or {}
    if not isinstance(dados, dict):
        dados = {}
    if "rascunho" in dados and isinstance(dados["rascunho"], dict):
        dados = dados["rascunho"]

    produto_dados = dados.get("produto") if isinstance(dados.get("produto"), dict) else {}
    produto_resolvido = uuid_str_ou_none(
        produto_id
        or dados.get("produto_id")
        or dados.get("produtoId")
        or produto_dados.get("id")
    )
    receita_dados = dados.get("receita") if isinstance(dados.get("receita"), dict) else {}
    preparo_dados = dados.get("preparo") if isinstance(dados.get("preparo"), dict) else {}

    rascunho = {
        "produto_id": produto_resolvido,
        "receita": {
            "nome": texto_ou_none(receita_dados.get("nome") or dados.get("nome_receita")),
            "rendimento": decimal_str_ou_none(
                receita_dados.get("rendimento") or dados.get("rendimento")
            ),
            "unidade_rendimento": texto_ou_none(
                receita_dados.get("unidade_rendimento")
                or receita_dados.get("unidadeRendimento")
                or dados.get("unidade_rendimento")
            )
            or "unidade",
            "status": status_de_custo(receita_dados.get("status"), padrao="PENDENTE"),
            "observacoes": texto_ou_none(
                receita_dados.get("observacoes") or dados.get("observacoes")
            ),
        },
        "ingredientes": [
            normalizar_ingrediente(item)
            for item in lista_ou_vazia(dados.get("ingredientes"))
        ],
        "custos_adicionais": [
            normalizar_custo_adicional(item)
            for item in lista_ou_vazia(
                dados.get("custos_adicionais") or dados.get("custosAdicionais")
            )
        ],
        "preparo": {
            "modo_preparo": texto_ou_none(
                preparo_dados.get("modo_preparo")
                or preparo_dados.get("modoPreparo")
                or dados.get("modo_preparo")
            ),
            "tempo_preparo_minutos": decimal_str_ou_none(
                preparo_dados.get("tempo_preparo_minutos")
                or preparo_dados.get("tempoPreparoMinutos")
            ),
            "tempo_forno_minutos": decimal_str_ou_none(
                preparo_dados.get("tempo_forno_minutos")
                or preparo_dados.get("tempoFornoMinutos")
            ),
            "temperatura_forno": texto_ou_none(
                preparo_dados.get("temperatura_forno") or preparo_dados.get("temperaturaForno")
            ),
            "observacoes": texto_ou_none(preparo_dados.get("observacoes")),
        },
        "avisos": deduplicar_textos(lista_de_textos(dados.get("avisos"))),
        "perguntas_sugeridas": deduplicar_textos(
            lista_de_textos(dados.get("perguntas_sugeridas"))
        ),
        "fontes": lista_ou_vazia(dados.get("fontes")),
    }
    if contexto:
        rascunho["fontes"].append({"tipo": "contexto", "texto": contexto})
    return rascunho


def normalizar_ingrediente(item: dict) -> dict:
    quantidade_usada = (
        item.get("quantidade_usada")
        or item.get("quantidadeUsada")
        or item.get("quantidade")
    )
    unidade_usada_original = (
        item.get("unidade_usada") or item.get("unidadeUsada") or item.get("unidade")
    )
    unidade_compra_original = item.get("unidade_compra") or item.get("unidadeCompra")
    unidade_usada = normalizar_unidade_de_entrada(unidade_usada_original)
    unidade_compra = normalizar_unidade_de_entrada(unidade_compra_original)
    normalizado = {
        "insumo_id": uuid_str_ou_none(item.get("insumo_id") or item.get("insumoId")),
        "nome": texto_ou_none(item.get("nome") or item.get("nome_insumo") or item.get("insumo")),
        "categoria": texto_ou_none(item.get("categoria")),
        "quantidade_comprada": decimal_str_ou_none(
            item.get("quantidade_comprada") or item.get("quantidadeComprada")
        ),
        "unidade_compra": unidade_compra,
        "preco_total": decimal_str_ou_none(item.get("preco_total") or item.get("precoTotal")),
        "quantidade_usada": decimal_str_ou_none(quantidade_usada),
        "unidade_usada": texto_ou_none(unidade_usada),
        "status": status_de_custo(item.get("status"), padrao="PENDENTE"),
        "observacoes": texto_ou_none(item.get("observacoes")),
        "confianca": float_ou_none(item.get("confianca")),
        "salvar_como_insumo": item.get("salvar_como_insumo", True),
    }
    inferir_unidade_de_compra_pelo_nome(normalizado)
    evitar_equivalencia_duplicada(normalizado, "quantidade_usada", "unidade_usada")
    evitar_equivalencia_duplicada(normalizado, "quantidade_comprada", "unidade_compra")
    resolver_quantidade_ambigua_no_rascunho(
        normalizado,
        quantidade_original=quantidade_usada,
        unidade_original=unidade_usada_original,
    )
    return normalizado


def resolver_quantidade_ambigua_no_rascunho(
    item: dict,
    *,
    quantidade_original,
    unidade_original,
) -> None:
    texto_original = " ".join(
        str(valor).strip()
        for valor in (quantidade_original, unidade_original)
        if valor is not None and str(valor).strip()
    )
    if not texto_indica_quantidade_alternativa(texto_original):
        return
    numeros = extrair_numeros_de_texto(texto_original)
    if len(numeros) < 2:
        return
    quantidade_escolhida = max(numeros)
    item["quantidade_usada"] = decimal_str_limpa(quantidade_escolhida)
    item["unidade_usada"] = (
        inferir_unidade_da_quantidade_ambigua(texto_original, item)
        or item.get("unidade_usada")
    )
    item["quantidade_usada_original"] = texto_original
    item["quantidade_usada_ambigua"] = True
    item["quantidade_usada_estimativa"] = decimal_str_limpa(quantidade_escolhida)


def normalizar_custo_adicional(item: dict) -> dict:
    tipo = tipo_custo_adicional(item.get("tipo"))
    aplicacao = item.get("aplicacao") or item.get("modo_aplicacao") or item.get("modoAplicacao")
    if aplicacao not in APLICACOES_CUSTO:
        aplicacao = "por_unidade" if tipo == "embalagem" else "por_receita"
    return {
        "tipo": tipo,
        "nome": texto_ou_none(item.get("nome")) or tipo,
        "valor": decimal_str_ou_none(item.get("valor")),
        "aplicacao": aplicacao,
        "status": status_de_custo(item.get("status"), padrao="ESTIMADO"),
        "observacoes": texto_ou_none(item.get("observacoes")),
        "confianca": float_ou_none(item.get("confianca")),
    }


def inferir_unidade_de_compra_pelo_nome(item: dict) -> None:
    unidade_compra = normalizar_unidade_texto(item.get("unidade_compra"))
    if unidade_compra not in {"un", "und", "unidade", "unidades"}:
        return
    equivalencia = equivalencia_explicita_na_unidade(item.get("nome"))
    if not equivalencia:
        return
    item["unidade_compra"] = equivalencia["unidade_canonica"]


def evitar_equivalencia_duplicada(item: dict, quantidade_chave: str, unidade_chave: str) -> None:
    quantidade = decimal_ou_none(item.get(quantidade_chave))
    equivalencia = equivalencia_explicita_na_unidade(item.get(unidade_chave))
    if quantidade is None or not equivalencia:
        return
    if quantidade == equivalencia["fator_base"]:
        item[unidade_chave] = equivalencia["unidade_base"]


def equivalencia_explicita_na_unidade(valor: str | None) -> dict | None:
    if not valor:
        return None
    unidade_normalizada = normalizar_chave(valor)
    if texto_indica_quantidade_alternativa(unidade_normalizada):
        return None
    padrao = re.compile(
        r"(\d+(?:[,.]\d+)?)\s*"
        r"(kg|quilo|quilos|kilograma|kilogramas|g|grama|gramas|"
        r"ml|mililitro|mililitros|l|lt|litro|litros|"
        r"un|und|unidade|unidades|ovo|ovos)\b"
    )
    match = padrao.search(unidade_normalizada)
    if not match:
        return None
    quantidade = Decimal(match.group(1).replace(",", "."))
    unidade = match.group(2)
    if unidade in {"kg", "quilo", "quilos", "kilograma", "kilogramas"}:
        tipo, unidade_base, multiplicador, unidade_canonica = "massa", "g", "1000", "kg"
    elif unidade in {"g", "grama", "gramas"}:
        tipo, unidade_base, multiplicador, unidade_canonica = "massa", "g", "1", "g"
    elif unidade in {"ml", "mililitro", "mililitros"}:
        tipo, unidade_base, multiplicador, unidade_canonica = "volume", "ml", "1", "ml"
    elif unidade in {"l", "lt", "litro", "litros"}:
        tipo, unidade_base, multiplicador, unidade_canonica = "volume", "ml", "1000", "l"
    else:
        tipo, unidade_base, multiplicador, unidade_canonica = (
            "unidade",
            "unidades",
            "1",
            "unidade",
        )
    fator_base = quantidade * Decimal(multiplicador)
    return {
        "tipo": tipo,
        "fator_base": fator_base,
        "unidade_base": unidade_base,
        "unidade_canonica": f"{decimal_str_limpa(quantidade)}{unidade_canonica}",
    }


def mesclar_rascunhos(atual: dict, novo: dict) -> dict:
    atual = normalizar_rascunho(atual, produto_id=atual.get("produto_id"))
    novo = normalizar_rascunho(novo, produto_id=novo.get("produto_id") or atual.get("produto_id"))
    resultado = {
        **atual,
        "produto_id": novo.get("produto_id") or atual.get("produto_id"),
        "receita": mesclar_dict_sem_nones(atual["receita"], novo["receita"]),
        "preparo": mesclar_dict_sem_nones(atual["preparo"], novo["preparo"]),
        "ingredientes": mesclar_ingredientes(
            atual["ingredientes"],
            novo["ingredientes"],
        ),
        "custos_adicionais": mesclar_listas_por_chave(
            atual["custos_adicionais"],
            novo["custos_adicionais"],
            chave_custo_adicional,
        ),
        "avisos": deduplicar_textos(atual.get("avisos", []) + novo.get("avisos", [])),
        "perguntas_sugeridas": deduplicar_textos(
            atual.get("perguntas_sugeridas", []) + novo.get("perguntas_sugeridas", [])
        ),
        "fontes": atual.get("fontes", []) + novo.get("fontes", []),
    }
    return resultado


def mesclar_dict_sem_nones(atual: dict, novo: dict) -> dict:
    resultado = dict(atual)
    for chave, valor in novo.items():
        if valor is not None and valor != []:
            resultado[chave] = valor
    return resultado


def mesclar_listas_por_chave(atual: list[dict], nova: list[dict], chave_fn) -> list[dict]:
    resultado = [dict(item) for item in atual]
    posicoes = {chave_fn(item): indice for indice, item in enumerate(resultado) if chave_fn(item)}
    for item in nova:
        chave = chave_fn(item)
        if chave and chave in posicoes:
            indice = posicoes[chave]
            resultado[indice] = mesclar_dict_sem_nones(resultado[indice], item)
        else:
            if chave:
                posicoes[chave] = len(resultado)
            resultado.append(item)
    return resultado


def mesclar_ingredientes(atual: list[dict], nova: list[dict]) -> list[dict]:
    resultado = [dict(item) for item in atual]
    for item_novo in nova:
        indice = encontrar_ingrediente_compativel(resultado, item_novo)
        if indice is None:
            resultado.append(item_novo)
            continue
        resultado[indice] = mesclar_ingrediente(resultado[indice], item_novo)
    return resultado


def encontrar_ingrediente_compativel(
    ingredientes: list[dict],
    item_novo: dict,
) -> int | None:
    novo_insumo_id = item_novo.get("insumo_id")
    for indice, item_atual in enumerate(ingredientes):
        if novo_insumo_id and item_atual.get("insumo_id") == novo_insumo_id:
            return indice

    for indice, item_atual in enumerate(ingredientes):
        if nomes_ingredientes_compativeis(item_atual.get("nome"), item_novo.get("nome")):
            return indice
    return None


def mesclar_ingrediente(atual: dict, novo: dict) -> dict:
    resultado = mesclar_dict_sem_nones(atual, novo)

    novo_tem_dados_de_compra = tem_algum_dado_de_compra(novo)
    if novo_tem_dados_de_compra and (
        atual.get("quantidade_usada") is not None or atual.get("unidade_usada") is not None
    ):
        resultado["nome"] = atual.get("nome") or novo.get("nome")
    else:
        resultado["nome"] = escolher_nome_ingrediente(atual.get("nome"), novo.get("nome"))

    if novo_tem_dados_de_compra:
        for chave in ("quantidade_usada", "unidade_usada"):
            if atual.get(chave) is not None and novo.get(chave) is not None:
                resultado[chave] = atual[chave]
    return resultado
