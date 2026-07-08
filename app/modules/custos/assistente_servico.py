import base64
import io
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.modules.custos import servico as servico_de_custos
from app.modules.custos.assistente_esquemas import (
    RequisicaoAtualizarRascunhoCusteio,
    RequisicaoConfirmarSessaoCusteio,
    RequisicaoCriarSessaoCusteio,
    RequisicaoEntradaFormularioCusteio,
    RequisicaoEntradaTextoCusteio,
)
from app.modules.custos.esquemas import (
    RequisicaoAtualizarInsumo,
    RequisicaoCriarCustoAdicional,
    RequisicaoCriarInsumo,
    RequisicaoCriarReceita,
    RequisicaoIngredienteReceita,
)
from app.modules.midia.servico import enviar_midia_em_bytes
from app.modules.produtos import servico as servico_de_produtos
from app.modules.produtos.esquemas import RequisicaoCriarVersaoDePreco
from app.shared.db import encode_value, first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo

STATUS_CUSTO_VALIDOS = {"CONFIRMADO", "ESTIMADO", "PENDENTE", "PRECISA_REVISAR"}
STATUS_ORDEM = {
    "CONFIRMADO": 0,
    "ESTIMADO": 1,
    "PENDENTE": 2,
    "PRECISA_REVISAR": 3,
}
TIPOS_CUSTO_ADICIONAL = {"embalagem", "transporte", "indireto", "outro"}
APLICACOES_CUSTO = {"por_receita", "por_unidade"}
SESSOES_IMUTAVEIS = {"confirmado", "descartado"}
FINALIDADES_ENTRADA = {"auto", "receita", "compras", "completo"}
DESCRITORES_INGREDIENTE = {
    "ralado",
    "ralada",
    "picado",
    "picada",
    "fatiado",
    "fatiada",
    "moido",
    "moida",
    "triturado",
    "triturada",
}
STOPWORDS_INGREDIENTE = {"de", "da", "do", "das", "dos", "para", "com", "sem", "tipo"}


def criar_sessao(requisicao: RequisicaoCriarSessaoCusteio) -> dict:
    rascunho = _normalizar_rascunho(
        requisicao.rascunho_inicial,
        produto_id=requisicao.produto_id,
        contexto=requisicao.contexto,
    )
    produto_id = requisicao.produto_id or _uuid_ou_none(rascunho.get("produto_id"))
    if produto_id:
        servico_de_produtos.buscar_produto(produto_id)
        rascunho["produto_id"] = str(produto_id)

    estado = _montar_estado_da_sessao(rascunho, produto_id=produto_id)

    sessao = (
        get_supabase_client()
        .table("sessoes_custeio_assistido")
        .insert(
            to_db_payload(
                {
                    "produto_id": produto_id,
                    "situacao": estado["situacao"],
                    "rascunho": rascunho,
                    "perguntas": estado["perguntas"],
                    "pendencias": estado["pendencias"],
                    "avisos": estado["avisos"],
                    "confianca_geral": estado["confianca_geral"],
                    "custo_simulado": estado["custo_simulado"],
                }
            )
        )
        .execute()
        .data[0]
    )
    return _montar_sessao_saida(sessao, entradas=[])


def buscar_sessao(sessao_id: UUID) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    return _montar_sessao_saida(sessao)


def adicionar_entrada_texto(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaTextoCusteio,
) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    _garantir_sessao_mutavel(sessao)
    finalidade = _resolver_finalidade_entrada(
        sessao,
        finalidade=requisicao.finalidade,
        contexto=requisicao.contexto or requisicao.texto,
    )
    extraidos = _extrair_rascunho_de_texto(
        requisicao.texto,
        sessao=sessao,
        contexto=requisicao.contexto,
        finalidade=finalidade,
        permitir_fallback=requisicao.permitir_fallback,
    )
    return _aplicar_entrada(
        sessao=sessao,
        tipo="texto",
        texto_original=requisicao.texto,
        dados_extraidos=extraidos,
        confianca=extraidos.get("confianca"),
        modelo_usado=extraidos.get("modelo_usado"),
    )


def adicionar_entrada_formulario(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaFormularioCusteio,
) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    _garantir_sessao_mutavel(sessao)
    finalidade = _resolver_finalidade_entrada(
        sessao,
        finalidade=requisicao.finalidade,
        contexto=requisicao.contexto,
    )
    rascunho = _normalizar_rascunho(requisicao.dados, produto_id=sessao.get("produto_id"))
    rascunho = _aplicar_finalidade_ao_rascunho_extraido(
        rascunho,
        finalidade=finalidade,
    )
    extraidos = {
        "rascunho": rascunho,
        "perguntas_sugeridas": [],
        "avisos": [],
        "confianca": 1,
        "modelo_usado": "formulario",
        "finalidade": finalidade,
    }
    texto_original = requisicao.contexto or "Entrada manual por formulario."
    return _aplicar_entrada(
        sessao=sessao,
        tipo="formulario",
        texto_original=texto_original,
        dados_extraidos=extraidos,
        confianca=1,
        modelo_usado="formulario",
    )


async def adicionar_entrada_arquivo(
    sessao_id: UUID,
    *,
    tipo: str,
    file: UploadFile,
    contexto: str | None = None,
    finalidade: str = "auto",
    permitir_fallback: bool = True,
) -> dict:
    tipo = tipo.strip().lower()
    if tipo not in {"audio", "imagem"}:
        raise BadRequestError("Tipo de arquivo invalido para custeio.", {"tipo": tipo})

    sessao = _buscar_sessao_bruta(sessao_id)
    _garantir_sessao_mutavel(sessao)
    finalidade_resolvida = _resolver_finalidade_entrada(
        sessao,
        finalidade=finalidade,
        contexto=contexto or file.filename,
    )
    conteudo = await file.read()
    if not conteudo:
        raise BadRequestError("Arquivo vazio.")

    midia = enviar_midia_em_bytes(
        tipo_entidade="sessao_custeio",
        entidade_id=sessao_id,
        conteudo=conteudo,
        nome_arquivo=file.filename,
        tipo_conteudo=file.content_type,
        descricao=f"Entrada de {tipo} para assistente de custeio",
    )

    if tipo == "audio":
        transcricao, modelo_transcricao = _transcrever_audio_de_custeio(
            conteudo=conteudo,
            nome_arquivo=file.filename,
        )
        extraidos = _extrair_rascunho_de_texto(
            transcricao,
            sessao=sessao,
            contexto=contexto,
            finalidade=finalidade_resolvida,
            permitir_fallback=permitir_fallback,
        )
        extraidos["transcricao"] = transcricao
        extraidos["modelo_transcricao"] = modelo_transcricao
        texto_original = transcricao
    else:
        extraidos = _extrair_rascunho_de_imagem(
            conteudo=conteudo,
            tipo_conteudo=file.content_type,
            sessao=sessao,
            contexto=contexto,
            finalidade=finalidade_resolvida,
        )
        texto_original = contexto

    return _aplicar_entrada(
        sessao=sessao,
        tipo=tipo,
        texto_original=texto_original,
        url_arquivo=midia.get("url_publica"),
        nome_arquivo=file.filename,
        tipo_conteudo=file.content_type,
        dados_extraidos=extraidos,
        confianca=extraidos.get("confianca"),
        modelo_usado=extraidos.get("modelo_usado"),
    )


def atualizar_rascunho(
    sessao_id: UUID,
    requisicao: RequisicaoAtualizarRascunhoCusteio,
) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    _garantir_sessao_mutavel(sessao)

    produto_id = requisicao.produto_id or _uuid_ou_none(sessao.get("produto_id"))
    if requisicao.produto_id:
        servico_de_produtos.buscar_produto(requisicao.produto_id)

    rascunho_atual = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id)
    rascunho_novo = _normalizar_rascunho(requisicao.rascunho, produto_id=produto_id)
    if requisicao.modo == "substituir":
        rascunho_final = rascunho_novo
    else:
        rascunho_final = _mesclar_rascunhos(rascunho_atual, rascunho_novo)

    dados_extraidos = {
        "rascunho": rascunho_novo,
        "observacao": requisicao.observacao,
        "confianca": 1,
        "modelo_usado": "edicao-manual",
    }
    return _aplicar_entrada(
        sessao=sessao,
        tipo="correcao",
        texto_original=requisicao.observacao or "Rascunho ajustado manualmente.",
        dados_extraidos=dados_extraidos,
        confianca=1,
        modelo_usado="edicao-manual",
        rascunho_final=rascunho_final,
        produto_id=produto_id,
    )


def confirmar_sessao(
    sessao_id: UUID,
    requisicao: RequisicaoConfirmarSessaoCusteio,
) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    _garantir_sessao_mutavel(sessao)

    produto_id = _uuid_ou_none(sessao.get("produto_id"))
    if not produto_id:
        raise BadRequestError("A sessao precisa estar atrelada a um produto antes de confirmar.")

    rascunho = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id)
    estado = _montar_estado_da_sessao(rascunho, produto_id=produto_id)
    pendencias = estado["pendencias"]
    if pendencias and not requisicao.permitir_pendencias:
        raise BadRequestError(
            "O rascunho ainda possui pendencias antes da confirmacao.",
            {"pendencias": pendencias, "perguntas": estado["perguntas"]},
        )

    receita_draft = rascunho["receita"]
    rendimento = _decimal_obrigatorio(receita_draft.get("rendimento"), "rendimento")
    ingredientes = _montar_ingredientes_para_confirmacao(rascunho["ingredientes"])
    if not ingredientes:
        raise BadRequestError("A receita precisa ter pelo menos um ingrediente.")

    receita = servico_de_custos.criar_receita(
        produto_id,
        RequisicaoCriarReceita(
            nome=receita_draft.get("nome") or None,
            rendimento=rendimento,
            unidade_rendimento=receita_draft.get("unidade_rendimento") or "unidade",
            status=_status_de_custo(receita_draft.get("status"), padrao=estado["status"]),
            observacoes=receita_draft.get("observacoes"),
            ingredientes=ingredientes,
        ),
    )

    custos_adicionais = []
    for custo in rascunho["custos_adicionais"]:
        valor_total = _valor_custo_adicional_para_receita(custo, rendimento)
        if valor_total is None:
            continue
        custos_adicionais.append(
            servico_de_custos.criar_custo_adicional(
                produto_id,
                RequisicaoCriarCustoAdicional(
                    receita_id=UUID(receita["id"]),
                    tipo=_tipo_custo_adicional(custo.get("tipo")),
                    nome=custo.get("nome") or "Custo adicional",
                    valor=valor_total,
                    status=_status_de_custo(custo.get("status"), padrao="ESTIMADO"),
                    observacoes=_observacao_do_custo_adicional(custo),
                ),
            )
        )

    calculo = servico_de_custos.calcular_custo_do_produto(
        produto_id,
        receita_id=UUID(receita["id"]),
    )
    preco_atualizado = None
    if requisicao.atualizar_preco_custo_produto and calculo.get("custo_por_unidade") is not None:
        preco_atualizado = _atualizar_preco_custo_do_produto(
            produto_id=produto_id,
            custo_por_unidade=Decimal(str(calculo["custo_por_unidade"])),
            vigente_desde=requisicao.vigente_desde,
            motivo=requisicao.motivo_preco,
        )

    resultado = {
        "receita": receita,
        "custos_adicionais": custos_adicionais,
        "calculo": calculo,
        "preco_atualizado": preco_atualizado,
    }

    client = get_supabase_client()
    sessao_atualizada = (
        client.table("sessoes_custeio_assistido")
        .update(
            to_db_payload(
                {
                    "situacao": "confirmado",
                    "rascunho": rascunho,
                    "perguntas": [],
                    "pendencias": [],
                    "avisos": estado["avisos"],
                    "confianca_geral": estado["confianca_geral"],
                    "custo_simulado": estado["custo_simulado"],
                    "resultado_confirmacao": resultado,
                    "confirmado_em": datetime.now(UTC),
                }
            )
        )
        .eq("id", str(sessao_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="custo_produto_confirmado",
        titulo="Custo do produto confirmado",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={
            "sessao_custeio_id": str(sessao_id),
            "receita_id": receita["id"],
            "custo_por_unidade": calculo.get("custo_por_unidade"),
        },
    )
    return _montar_sessao_saida(sessao_atualizada)


def descartar_sessao(sessao_id: UUID) -> dict:
    sessao = _buscar_sessao_bruta(sessao_id)
    if sessao["situacao"] == "confirmado":
        raise ConflictError("Uma sessao confirmada nao pode ser descartada.")
    if sessao["situacao"] == "descartado":
        return _montar_sessao_saida(sessao)
    sessao_atualizada = (
        get_supabase_client()
        .table("sessoes_custeio_assistido")
        .update(
            to_db_payload(
                {
                    "situacao": "descartado",
                    "descartado_em": datetime.now(UTC),
                }
            )
        )
        .eq("id", str(sessao_id))
        .execute()
        .data[0]
    )
    return _montar_sessao_saida(sessao_atualizada)


def _buscar_sessao_bruta(sessao_id: UUID) -> dict:
    sessao = first_or_none(
        get_supabase_client()
        .table("sessoes_custeio_assistido")
        .select("*")
        .eq("id", str(sessao_id))
        .limit(1)
        .execute()
        .data
    )
    if not sessao:
        raise NotFoundError("Sessao de custeio", str(sessao_id))
    return sessao


def _listar_entradas(sessao_id: UUID | str) -> list[dict]:
    return (
        get_supabase_client()
        .table("entradas_custeio_assistido")
        .select("*")
        .eq("sessao_id", str(sessao_id))
        .order("criado_em", desc=True)
        .execute()
        .data
    )


def _garantir_sessao_mutavel(sessao: dict) -> None:
    if sessao["situacao"] in SESSOES_IMUTAVEIS:
        raise ConflictError(
            "Essa sessao de custeio nao pode mais ser alterada.",
            {"situacao": sessao["situacao"]},
        )


def _aplicar_entrada(
    *,
    sessao: dict,
    tipo: str,
    texto_original: str | None = None,
    url_arquivo: str | None = None,
    nome_arquivo: str | None = None,
    tipo_conteudo: str | None = None,
    dados_extraidos: dict,
    confianca: float | Decimal | None,
    modelo_usado: str | None,
    rascunho_final: dict | None = None,
    produto_id: UUID | None = None,
) -> dict:
    client = get_supabase_client()
    client.table("entradas_custeio_assistido").insert(
        to_db_payload(
            {
                "sessao_id": sessao["id"],
                "tipo": tipo,
                "texto_original": texto_original,
                "url_arquivo": url_arquivo,
                "nome_arquivo": nome_arquivo,
                "tipo_conteudo": tipo_conteudo,
                "dados_extraidos": dados_extraidos,
                "confianca": confianca,
                "modelo_usado": modelo_usado,
                "situacao": "processada",
            }
        )
    ).execute()

    produto_id_final = produto_id or _uuid_ou_none(sessao.get("produto_id"))
    rascunho_atual = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id_final)
    if rascunho_final is None:
        rascunho_extraido = _normalizar_rascunho(
            dados_extraidos.get("rascunho") or {},
            produto_id=produto_id_final,
        )
        rascunho_final = _mesclar_rascunhos(rascunho_atual, rascunho_extraido)
    else:
        rascunho_final = _normalizar_rascunho(rascunho_final, produto_id=produto_id_final)

    produto_id_extraido = _uuid_ou_none(rascunho_final.get("produto_id"))
    if produto_id_extraido:
        produto_id_final = produto_id_extraido
        servico_de_produtos.buscar_produto(produto_id_final)

    estado = _montar_estado_da_sessao(rascunho_final, produto_id=produto_id_final)
    sessao_atualizada = (
        client.table("sessoes_custeio_assistido")
        .update(
            to_db_payload(
                {
                    "produto_id": produto_id_final,
                    "situacao": estado["situacao"],
                    "rascunho": rascunho_final,
                    "perguntas": estado["perguntas"],
                    "pendencias": estado["pendencias"],
                    "avisos": estado["avisos"],
                    "confianca_geral": estado["confianca_geral"],
                    "custo_simulado": estado["custo_simulado"],
                }
            )
        )
        .eq("id", sessao["id"])
        .execute()
        .data[0]
    )
    return _montar_sessao_saida(sessao_atualizada)


def _montar_sessao_saida(sessao: dict, entradas: list[dict] | None = None) -> dict:
    produto = None
    produto_id = _uuid_ou_none(sessao.get("produto_id"))
    if produto_id:
        try:
            produto = servico_de_produtos.buscar_produto(produto_id)
        except NotFoundError:
            produto = None

    entradas_resolvidas = _listar_entradas(sessao["id"]) if entradas is None else entradas
    pendencias = sessao.get("pendencias") or []
    situacao = sessao["situacao"]
    pode_confirmar = situacao in {"pronto_para_confirmar", "precisa_revisao"} and bool(produto_id)
    pode_confirmar = pode_confirmar and not pendencias
    return encode_value(
        {
            **sessao,
            "produto": produto,
            "pode_confirmar": pode_confirmar,
            "fase": _resolver_fase(sessao, produto_id=produto_id),
            "proxima_acao": _resolver_proxima_acao(sessao, produto_id=produto_id),
            "entradas": entradas_resolvidas,
        }
    )


def _montar_estado_da_sessao(rascunho: dict, *, produto_id: UUID | None) -> dict:
    rascunho_normalizado = _normalizar_rascunho(rascunho, produto_id=produto_id)
    custo_simulado = _simular_custo(rascunho_normalizado, produto_id=produto_id)
    pendencias = custo_simulado["pendencias"]
    avisos = _deduplicar_textos(custo_simulado["avisos"] + rascunho_normalizado.get("avisos", []))
    perguntas = _montar_perguntas(rascunho_normalizado, pendencias)
    confianca = _calcular_confianca_geral(rascunho_normalizado, pendencias)
    status = custo_simulado["status"]
    if pendencias:
        situacao = "precisa_revisao"
    elif not rascunho_normalizado["ingredientes"]:
        situacao = "rascunho"
    else:
        situacao = "pronto_para_confirmar"
    return {
        "situacao": situacao,
        "status": status,
        "perguntas": perguntas,
        "pendencias": pendencias,
        "avisos": avisos,
        "confianca_geral": confianca,
        "custo_simulado": custo_simulado,
    }


def _normalizar_rascunho(
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
    produto_resolvido = _uuid_str_ou_none(
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
            "nome": _texto_ou_none(receita_dados.get("nome") or dados.get("nome_receita")),
            "rendimento": _decimal_str_ou_none(
                receita_dados.get("rendimento") or dados.get("rendimento")
            ),
            "unidade_rendimento": _texto_ou_none(
                receita_dados.get("unidade_rendimento")
                or receita_dados.get("unidadeRendimento")
                or dados.get("unidade_rendimento")
            )
            or "unidade",
            "status": _status_de_custo(receita_dados.get("status"), padrao="PENDENTE"),
            "observacoes": _texto_ou_none(
                receita_dados.get("observacoes") or dados.get("observacoes")
            ),
        },
        "ingredientes": [
            _normalizar_ingrediente(item)
            for item in _lista_ou_vazia(dados.get("ingredientes"))
        ],
        "custos_adicionais": [
            _normalizar_custo_adicional(item)
            for item in _lista_ou_vazia(
                dados.get("custos_adicionais") or dados.get("custosAdicionais")
            )
        ],
        "preparo": {
            "modo_preparo": _texto_ou_none(
                preparo_dados.get("modo_preparo")
                or preparo_dados.get("modoPreparo")
                or dados.get("modo_preparo")
            ),
            "tempo_preparo_minutos": _decimal_str_ou_none(
                preparo_dados.get("tempo_preparo_minutos")
                or preparo_dados.get("tempoPreparoMinutos")
            ),
            "tempo_forno_minutos": _decimal_str_ou_none(
                preparo_dados.get("tempo_forno_minutos")
                or preparo_dados.get("tempoFornoMinutos")
            ),
            "temperatura_forno": _texto_ou_none(
                preparo_dados.get("temperatura_forno") or preparo_dados.get("temperaturaForno")
            ),
            "observacoes": _texto_ou_none(preparo_dados.get("observacoes")),
        },
        "avisos": _deduplicar_textos(_lista_de_textos(dados.get("avisos"))),
        "perguntas_sugeridas": _deduplicar_textos(
            _lista_de_textos(dados.get("perguntas_sugeridas"))
        ),
        "fontes": _lista_ou_vazia(dados.get("fontes")),
    }
    if contexto:
        rascunho["fontes"].append({"tipo": "contexto", "texto": contexto})
    return rascunho


def _normalizar_ingrediente(item: dict) -> dict:
    quantidade_usada = (
        item.get("quantidade_usada")
        or item.get("quantidadeUsada")
        or item.get("quantidade")
    )
    unidade_usada = item.get("unidade_usada") or item.get("unidadeUsada") or item.get("unidade")
    return {
        "insumo_id": _uuid_str_ou_none(item.get("insumo_id") or item.get("insumoId")),
        "nome": _texto_ou_none(item.get("nome") or item.get("nome_insumo") or item.get("insumo")),
        "categoria": _texto_ou_none(item.get("categoria")),
        "quantidade_comprada": _decimal_str_ou_none(
            item.get("quantidade_comprada") or item.get("quantidadeComprada")
        ),
        "unidade_compra": _texto_ou_none(
            item.get("unidade_compra") or item.get("unidadeCompra")
        ),
        "preco_total": _decimal_str_ou_none(item.get("preco_total") or item.get("precoTotal")),
        "quantidade_usada": _decimal_str_ou_none(quantidade_usada),
        "unidade_usada": _texto_ou_none(unidade_usada),
        "status": _status_de_custo(item.get("status"), padrao="PENDENTE"),
        "observacoes": _texto_ou_none(item.get("observacoes")),
        "confianca": _float_ou_none(item.get("confianca")),
        "salvar_como_insumo": item.get("salvar_como_insumo", True),
    }


def _normalizar_custo_adicional(item: dict) -> dict:
    tipo = _tipo_custo_adicional(item.get("tipo"))
    aplicacao = item.get("aplicacao") or item.get("modo_aplicacao") or item.get("modoAplicacao")
    if aplicacao not in APLICACOES_CUSTO:
        aplicacao = "por_unidade" if tipo == "embalagem" else "por_receita"
    return {
        "tipo": tipo,
        "nome": _texto_ou_none(item.get("nome")) or tipo,
        "valor": _decimal_str_ou_none(item.get("valor")),
        "aplicacao": aplicacao,
        "status": _status_de_custo(item.get("status"), padrao="ESTIMADO"),
        "observacoes": _texto_ou_none(item.get("observacoes")),
        "confianca": _float_ou_none(item.get("confianca")),
    }


def _mesclar_rascunhos(atual: dict, novo: dict) -> dict:
    atual = _normalizar_rascunho(atual, produto_id=atual.get("produto_id"))
    novo = _normalizar_rascunho(novo, produto_id=novo.get("produto_id") or atual.get("produto_id"))
    resultado = {
        **atual,
        "produto_id": novo.get("produto_id") or atual.get("produto_id"),
        "receita": _mesclar_dict_sem_nones(atual["receita"], novo["receita"]),
        "preparo": _mesclar_dict_sem_nones(atual["preparo"], novo["preparo"]),
        "ingredientes": _mesclar_ingredientes(
            atual["ingredientes"],
            novo["ingredientes"],
        ),
        "custos_adicionais": _mesclar_listas_por_chave(
            atual["custos_adicionais"],
            novo["custos_adicionais"],
            _chave_custo_adicional,
        ),
        "avisos": _deduplicar_textos(atual.get("avisos", []) + novo.get("avisos", [])),
        "perguntas_sugeridas": _deduplicar_textos(
            atual.get("perguntas_sugeridas", []) + novo.get("perguntas_sugeridas", [])
        ),
        "fontes": atual.get("fontes", []) + novo.get("fontes", []),
    }
    return resultado


def _mesclar_dict_sem_nones(atual: dict, novo: dict) -> dict:
    resultado = dict(atual)
    for chave, valor in novo.items():
        if valor is not None and valor != []:
            resultado[chave] = valor
    return resultado


def _mesclar_listas_por_chave(atual: list[dict], nova: list[dict], chave_fn) -> list[dict]:
    resultado = [dict(item) for item in atual]
    posicoes = {chave_fn(item): indice for indice, item in enumerate(resultado) if chave_fn(item)}
    for item in nova:
        chave = chave_fn(item)
        if chave and chave in posicoes:
            indice = posicoes[chave]
            resultado[indice] = _mesclar_dict_sem_nones(resultado[indice], item)
        else:
            if chave:
                posicoes[chave] = len(resultado)
            resultado.append(item)
    return resultado


def _mesclar_ingredientes(atual: list[dict], nova: list[dict]) -> list[dict]:
    resultado = [dict(item) for item in atual]
    for item_novo in nova:
        indice = _encontrar_ingrediente_compativel(resultado, item_novo)
        if indice is None:
            resultado.append(item_novo)
            continue
        resultado[indice] = _mesclar_ingrediente(resultado[indice], item_novo)
    return resultado


def _encontrar_ingrediente_compativel(
    ingredientes: list[dict],
    item_novo: dict,
) -> int | None:
    novo_insumo_id = item_novo.get("insumo_id")
    for indice, item_atual in enumerate(ingredientes):
        if novo_insumo_id and item_atual.get("insumo_id") == novo_insumo_id:
            return indice

    for indice, item_atual in enumerate(ingredientes):
        if _nomes_ingredientes_compativeis(item_atual.get("nome"), item_novo.get("nome")):
            return indice
    return None


def _mesclar_ingrediente(atual: dict, novo: dict) -> dict:
    resultado = _mesclar_dict_sem_nones(atual, novo)
    resultado["nome"] = _escolher_nome_ingrediente(atual.get("nome"), novo.get("nome"))

    novo_tem_dados_de_compra = _tem_algum_dado_de_compra(novo)
    if novo_tem_dados_de_compra:
        for chave in ("quantidade_usada", "unidade_usada"):
            if atual.get(chave) is not None and novo.get(chave) is not None:
                resultado[chave] = atual[chave]
    return resultado


def _simular_custo(rascunho: dict, *, produto_id: UUID | str | None) -> dict:
    pendencias = []
    avisos = []
    ingredientes_simulados = []
    custos_simulados = []
    statuses = [rascunho["receita"].get("status") or "PENDENTE"]
    rendimento = _decimal_ou_none(rascunho["receita"].get("rendimento"))
    custo_ingredientes = Decimal("0")
    custo_adicional_total = Decimal("0")

    if not produto_id and not rascunho.get("produto_id"):
        pendencias.append("Nenhum produto foi vinculado a sessao de custeio.")
    if not rendimento or rendimento <= 0:
        pendencias.append("Informe o rendimento da receita antes de confirmar.")
    if not rascunho["ingredientes"]:
        pendencias.append("Informe pelo menos um ingrediente da receita.")

    for indice, ingrediente in enumerate(rascunho["ingredientes"], start=1):
        simulado = dict(ingrediente)
        status = _status_de_custo(ingrediente.get("status"), padrao="PENDENTE")
        statuses.append(status)
        custo_total, custo_unitario, pendencia = _simular_ingrediente(ingrediente)
        for campo_unidade in ("unidade_usada", "unidade_compra"):
            descricao = _descrever_conversao_aproximada(ingrediente.get(campo_unidade))
            if descricao:
                avisos.append(
                    f"Ingrediente {ingrediente.get('nome') or indice}: medida caseira "
                    f"convertida como {descricao}. Confirme se esse e o tamanho usado."
                )
        if pendencia:
            pendencias.append(f"Ingrediente {indice}: {pendencia}")
        if custo_total is not None:
            custo_ingredientes += custo_total
        simulado["custo_unitario_base"] = _decimal_str_ou_none(custo_unitario)
        simulado["custo_total_estimado"] = _decimal_str_ou_none(custo_total)
        ingredientes_simulados.append(simulado)

    for custo in rascunho["custos_adicionais"]:
        status = _status_de_custo(custo.get("status"), padrao="ESTIMADO")
        statuses.append(status)
        valor_total = _valor_custo_adicional_para_receita(custo, rendimento)
        simulado = dict(custo)
        simulado["valor_total_receita"] = _decimal_str_ou_none(valor_total)
        if valor_total is not None:
            custo_adicional_total += valor_total
        else:
            pendencias.append(f"Custo adicional {custo.get('nome') or 'sem nome'} sem valor.")
        custos_simulados.append(simulado)

    tipos_custo = {item["tipo"] for item in rascunho["custos_adicionais"]}
    if "embalagem" not in tipos_custo:
        avisos.append("Embalagem ainda nao informada.")
    if "transporte" not in tipos_custo:
        avisos.append("Transporte ainda nao informado.")
    if not any(item["tipo"] == "indireto" for item in rascunho["custos_adicionais"]):
        avisos.append("Custos indiretos como gas, energia ou agua ainda nao informados.")

    custo_total = _arredondar_moeda(custo_ingredientes + custo_adicional_total)
    custo_por_unidade = None
    if rendimento and rendimento > 0:
        custo_por_unidade = _arredondar_moeda(custo_total / rendimento)

    preco_venda = None
    lucro_estimado = None
    margem_estimada = None
    produto_resumo = None
    produto_id_resolvido = _uuid_ou_none(produto_id or rascunho.get("produto_id"))
    if produto_id_resolvido:
        try:
            produto = servico_de_produtos.buscar_produto(produto_id_resolvido)
            produto_resumo = {
                "id": produto["id"],
                "nome": produto["nome"],
            }
            preco_atual = produto.get("preco_atual") or {}
            preco_venda = _decimal_ou_none(preco_atual.get("preco_venda"))
            if preco_venda is not None and custo_por_unidade is not None:
                lucro_estimado = _arredondar_moeda(preco_venda - custo_por_unidade)
                if preco_venda > 0:
                    margem_estimada = _arredondar_percentual(lucro_estimado / preco_venda * 100)
        except NotFoundError:
            pendencias.append("Produto vinculado nao foi encontrado.")

    if pendencias:
        statuses.append("PENDENTE")

    status = _consolidar_status(statuses)
    return encode_value(
        {
            "produto": produto_resumo,
            "custo_ingredientes": _arredondar_moeda(custo_ingredientes),
            "custo_adicional_total": _arredondar_moeda(custo_adicional_total),
            "custo_total_receita": custo_total,
            "rendimento": rendimento,
            "custo_por_unidade": custo_por_unidade,
            "preco_venda_atual": preco_venda,
            "lucro_estimado_por_unidade": lucro_estimado,
            "margem_estimada_percentual": margem_estimada,
            "status": status,
            "ingredientes": ingredientes_simulados,
            "custos_adicionais": custos_simulados,
            "custos_incluidos": {
                "ingredientes": bool(rascunho["ingredientes"]),
                "embalagem": "embalagem" in tipos_custo,
                "transporte": "transporte" in tipos_custo,
                "indiretos": "indireto" in tipos_custo,
            },
            "pendencias": _deduplicar_textos(pendencias),
            "avisos": _deduplicar_textos(avisos),
        }
    )


def _simular_ingrediente(ingrediente: dict) -> tuple[Decimal | None, Decimal | None, str | None]:
    nome = ingrediente.get("nome") or "sem nome"
    quantidade_usada = _decimal_ou_none(ingrediente.get("quantidade_usada"))
    unidade_usada = ingrediente.get("unidade_usada")
    if not nome:
        return None, None, "nome nao informado."
    if not quantidade_usada or quantidade_usada <= 0:
        return None, None, f"{nome} sem quantidade usada."
    if not unidade_usada:
        return None, None, f"{nome} sem unidade usada."

    insumo_id = _uuid_ou_none(ingrediente.get("insumo_id"))
    try:
        if insumo_id:
            insumo = servico_de_custos.buscar_insumo(insumo_id)
            custo_unitario = Decimal(str(insumo["custo_por_unidade"]))
            custo_total = servico_de_custos._calcular_custo_ingrediente(
                custo_unitario,
                quantidade_usada,
                unidade_usada,
                insumo["unidade_compra"],
            )
            return custo_total, custo_unitario, None

        quantidade_comprada = _decimal_ou_none(ingrediente.get("quantidade_comprada"))
        unidade_compra = ingrediente.get("unidade_compra")
        preco_total = _decimal_ou_none(ingrediente.get("preco_total"))
        insumo_existente = _buscar_insumo_existente_para_ingrediente(ingrediente)
        if insumo_existente and not _tem_dados_de_compra_completos(ingrediente):
            custo_unitario = Decimal(str(insumo_existente["custo_por_unidade"]))
            custo_total = servico_de_custos._calcular_custo_ingrediente(
                custo_unitario,
                quantidade_usada,
                unidade_usada,
                insumo_existente["unidade_compra"],
            )
            return custo_total, custo_unitario, None

        if not quantidade_comprada or not unidade_compra or preco_total is None:
            return None, None, f"{nome} sem preco/quantidade de compra para calcular custo."

        custo_unitario = servico_de_custos._calcular_custo_por_unidade(
            preco_total,
            quantidade_comprada,
            unidade_compra,
        )
        custo_total = servico_de_custos._calcular_custo_ingrediente(
            custo_unitario,
            quantidade_usada,
            unidade_usada,
            unidade_compra,
        )
        return custo_total, custo_unitario, None
    except BadRequestError as exc:
        return None, None, f"{nome}: {exc.message}"


def _montar_perguntas(rascunho: dict, pendencias: list[str]) -> list[dict]:
    perguntas = []
    if not rascunho.get("produto_id"):
        perguntas.append(
            {
                "id": "produto_id",
                "campo": "produto_id",
                "pergunta": "Qual produto cadastrado deve receber este custo?",
                "tipo_resposta": "produto",
                "prioridade": 1,
            }
        )
    if not _decimal_ou_none(rascunho["receita"].get("rendimento")):
        perguntas.append(
            {
                "id": "receita.rendimento",
                "campo": "receita.rendimento",
                "pergunta": "Quantas unidades essa receita rende?",
                "tipo_resposta": "numero",
                "prioridade": 1,
            }
        )
    for indice, ingrediente in enumerate(rascunho["ingredientes"], start=1):
        nome = ingrediente.get("nome") or f"ingrediente {indice}"
        if not ingrediente.get("quantidade_usada"):
            perguntas.append(
                {
                    "id": f"ingredientes.{indice}.quantidade_usada",
                    "campo": f"ingredientes[{indice - 1}].quantidade_usada",
                    "pergunta": f"Quanto de {nome} entra na receita?",
                    "tipo_resposta": "numero",
                    "prioridade": 1,
                }
            )
        if not ingrediente.get("insumo_id") and not ingrediente.get("preco_total"):
            perguntas.append(
                {
                    "id": f"ingredientes.{indice}.preco_total",
                    "campo": f"ingredientes[{indice - 1}].preco_total",
                    "pergunta": f"Quanto custou a compra de {nome}?",
                    "tipo_resposta": "dinheiro",
                    "prioridade": 2,
                }
            )
    for pergunta in rascunho.get("perguntas_sugeridas", []):
        perguntas.append(
            {
                "id": _normalizar_chave(pergunta)[:60],
                "campo": None,
                "pergunta": pergunta,
                "tipo_resposta": "texto",
                "prioridade": 3,
            }
        )
    if not perguntas and pendencias:
        perguntas.append(
            {
                "id": "revisar_pendencias",
                "campo": None,
                "pergunta": "Revise as pendencias antes de confirmar o custo.",
                "tipo_resposta": "acao",
                "prioridade": 1,
            }
        )
    return perguntas


def _calcular_confianca_geral(rascunho: dict, pendencias: list[str]) -> Decimal:
    confiancas = []
    for ingrediente in rascunho["ingredientes"]:
        if ingrediente.get("confianca") is not None:
            confiancas.append(Decimal(str(ingrediente["confianca"])))
    for custo in rascunho["custos_adicionais"]:
        if custo.get("confianca") is not None:
            confiancas.append(Decimal(str(custo["confianca"])))
    if not confiancas:
        base = Decimal("0.60") if rascunho["ingredientes"] else Decimal("0.25")
    else:
        base = sum(confiancas, Decimal("0")) / Decimal(len(confiancas))
    desconto = Decimal("0.08") * Decimal(len(pendencias))
    return max(Decimal("0"), min(Decimal("1"), base - desconto)).quantize(Decimal("0.0001"))


def _extrair_rascunho_de_texto(
    texto: str,
    *,
    sessao: dict,
    contexto: str | None,
    finalidade: str,
    permitir_fallback: bool,
) -> dict:
    settings = get_settings()
    if settings.openai_text_configured:
        try:
            return _extrair_com_openai_texto(
                texto,
                sessao=sessao,
                contexto=contexto,
                finalidade=finalidade,
            )
        except Exception:
            if not permitir_fallback:
                raise
    return _extrair_com_fallback_texto(
        texto,
        sessao=sessao,
        contexto=contexto,
        finalidade=finalidade,
    )


def _extrair_com_openai_texto(
    texto: str,
    *,
    sessao: dict,
    contexto: str | None,
    finalidade: str,
) -> dict:
    settings = get_settings()
    resposta = get_openai_client().responses.create(
        model=settings.openai_text_model_resolved,
        instructions=_instrucoes_extracao_custeio(),
        input=json.dumps(
            {
                "tipo_entrada": "texto",
                "texto": texto,
                "contexto": contexto,
                "finalidade": finalidade,
                "produto_id_da_sessao": sessao.get("produto_id"),
                "rascunho_atual": sessao.get("rascunho") or {},
                "catalogo_produtos": _catalogo_de_produtos_para_ia(),
            },
            ensure_ascii=False,
        ),
        text={"format": _formato_json_extracao_custeio()},
    )
    dados = json.loads(resposta.output_text)
    dados["modelo_usado"] = settings.openai_text_model_resolved
    dados["finalidade"] = finalidade
    dados["rascunho"] = _normalizar_rascunho(
        dados.get("rascunho") or dados,
        produto_id=sessao.get("produto_id"),
        contexto=contexto,
    )
    dados["rascunho"] = _aplicar_finalidade_ao_rascunho_extraido(
        dados["rascunho"],
        finalidade=finalidade,
    )
    return dados


def _extrair_rascunho_de_imagem(
    *,
    conteudo: bytes,
    tipo_conteudo: str | None,
    sessao: dict,
    contexto: str | None,
    finalidade: str,
) -> dict:
    settings = get_settings()
    if not settings.openai_text_configured:
        faltando = []
        if not settings.openai_api_key:
            faltando.append("OPENAI_API_KEY")
        if not settings.openai_text_model_resolved:
            faltando.append("OPENAI_TEXT_MODEL")
        raise MissingConfigurationError("OpenAI Vision", faltando)

    tipo = tipo_conteudo or "image/jpeg"
    imagem_base64 = base64.b64encode(conteudo).decode("ascii")
    resposta = get_openai_client().responses.create(
        model=settings.openai_text_model_resolved,
        instructions=_instrucoes_extracao_custeio(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "tipo_entrada": "imagem",
                                "contexto": contexto,
                                "finalidade": finalidade,
                                "produto_id_da_sessao": sessao.get("produto_id"),
                                "rascunho_atual": sessao.get("rascunho") or {},
                                "catalogo_produtos": _catalogo_de_produtos_para_ia(),
                                "orientacao": (
                                    "Extraia somente itens, precos, quantidades e unidades "
                                    "legiveis. Se a imagem estiver ruim, gere perguntas."
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{tipo};base64,{imagem_base64}",
                    },
                ],
            }
        ],
        text={"format": _formato_json_extracao_custeio()},
    )
    dados = json.loads(resposta.output_text)
    dados["modelo_usado"] = settings.openai_text_model_resolved
    dados["finalidade"] = finalidade
    dados["rascunho"] = _normalizar_rascunho(
        dados.get("rascunho") or dados,
        produto_id=sessao.get("produto_id"),
        contexto=contexto,
    )
    dados["rascunho"] = _aplicar_finalidade_ao_rascunho_extraido(
        dados["rascunho"],
        finalidade=finalidade,
    )
    return dados


def _transcrever_audio_de_custeio(*, conteudo: bytes, nome_arquivo: str | None) -> tuple[str, str]:
    settings = get_settings()
    faltando = []
    if not settings.openai_api_key:
        faltando.append("OPENAI_API_KEY")
    if not settings.openai_transcription_model:
        faltando.append("OPENAI_TRANSCRIPTION_MODEL")
    if faltando:
        raise MissingConfigurationError("OpenAI Audio", faltando)
    buffer_audio = io.BytesIO(conteudo)
    buffer_audio.name = nome_arquivo or "audio.webm"
    resposta = get_openai_client().audio.transcriptions.create(
        model=settings.openai_transcription_model,
        file=buffer_audio,
    )
    transcricao = getattr(resposta, "text", None)
    if not transcricao and isinstance(resposta, dict):
        transcricao = resposta.get("text")
    return transcricao or "", settings.openai_transcription_model


def _extrair_com_fallback_texto(
    texto: str,
    *,
    sessao: dict,
    contexto: str | None,
    finalidade: str,
) -> dict:
    rascunho = _normalizar_rascunho({}, produto_id=sessao.get("produto_id"), contexto=contexto)
    produto_id = _identificar_produto_no_texto(texto)
    if produto_id and not rascunho.get("produto_id"):
        rascunho["produto_id"] = str(produto_id)

    rendimento = _extrair_rendimento(texto)
    if rendimento:
        rascunho["receita"]["rendimento"] = str(rendimento)

    ingredientes = _extrair_ingredientes_simples(texto)
    if ingredientes:
        rascunho["ingredientes"] = ingredientes
    else:
        rascunho["avisos"].append(
            "Fallback local nao conseguiu estruturar ingredientes com seguranca."
        )
        rascunho["perguntas_sugeridas"].append(
            "Envie os ingredientes em linhas ou configure OpenAI para extracao completa."
        )

    rascunho = _aplicar_finalidade_ao_rascunho_extraido(rascunho, finalidade=finalidade)
    return {
        "rascunho": rascunho,
        "perguntas_sugeridas": rascunho["perguntas_sugeridas"],
        "avisos": rascunho["avisos"],
        "confianca": 0.35 if ingredientes else 0.15,
        "modelo_usado": "fallback-custeio",
        "finalidade": finalidade,
    }


def _instrucoes_extracao_custeio() -> str:
    return (
        "Voce e um assistente de custeio para uma pequena padaria familiar. "
        "Transforme texto, audio transcrito, formulario ou imagem de nota/print em um rascunho "
        "estruturado de custo. Nunca invente preco, quantidade, unidade, rendimento, produto ou "
        "ingrediente. Quando algo nao estiver claro, deixe null, marque status PRECISA_REVISAR "
        "ou PENDENTE e gere perguntas_sugeridas. Use somente produto_id presente na sessao ou "
        "um produto existente no catalogo enviado. Diferencie quantidade comprada da quantidade "
        "usada na receita. O backend converte medidas como ml, l, g, kg, copo, xicara, "
        "colher de sopa, colher de cha, prato cheio com equivalencia em gramas, ovo e "
        "cartela de ovos. Se a entrada trouxer medida caseira, mantenha a unidade falada "
        "pelo usuario para que a tela mostre revisao; se houver equivalencia explicita, "
        "preserve a equivalencia na unidade, como 'prato cheio (350 g)' ou "
        "'cartela de 30 ovos'. Respeite a finalidade recebida no input: com finalidade "
        "'receita', preencha apenas receita, preparo, quantidade_usada e unidade_usada; "
        "em imagem de receita, medidas como '250 ml de leite' ou '1/2 copo de oleo' "
        "sao sempre quantidade_usada/unidade_usada, nao quantidade_comprada/unidade_compra; "
        "deixe quantidade_comprada, unidade_compra e preco_total como null, mesmo que a "
        "receita tenha medidas. Com finalidade 'compras', preencha quantidade_comprada, "
        "unidade_compra e preco_total; deixe quantidade_usada, unidade_usada, preparo e "
        "rendimento como null, salvo se o usuario trouxer isso explicitamente junto. "
        "Com finalidade 'completo', aceite receita e compras na mesma entrada, mas nunca "
        "copie quantidade usada para quantidade comprada por deducao. Para embalagem normalmente "
        "use aplicacao por_unidade; para gas, "
        "energia e transporte use por_receita quando o usuario informar valor do lote/receita. "
        "Status deve ser CONFIRMADO quando o usuario informou explicitamente, ESTIMADO quando "
        "for uma aproximacao declarada, PENDENTE quando faltar dado e PRECISA_REVISAR quando "
        "a leitura estiver incerta. Retorne somente JSON valido no schema solicitado."
    )


def _formato_json_extracao_custeio() -> dict:
    item_nullable_string = {"type": ["string", "null"]}
    item_nullable_number = {"type": ["number", "null"]}
    return {
        "type": "json_schema",
        "name": "extracao_custeio_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "rascunho",
                "perguntas_sugeridas",
                "avisos",
                "confianca",
            ],
            "properties": {
                "rascunho": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "produto_id",
                        "receita",
                        "ingredientes",
                        "custos_adicionais",
                        "preparo",
                    ],
                    "properties": {
                        "produto_id": item_nullable_string,
                        "receita": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "nome",
                                "rendimento",
                                "unidade_rendimento",
                                "status",
                                "observacoes",
                            ],
                            "properties": {
                                "nome": item_nullable_string,
                                "rendimento": item_nullable_number,
                                "unidade_rendimento": item_nullable_string,
                                "status": {"type": "string"},
                                "observacoes": item_nullable_string,
                            },
                        },
                        "ingredientes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "insumo_id",
                                    "nome",
                                    "categoria",
                                    "quantidade_comprada",
                                    "unidade_compra",
                                    "preco_total",
                                    "quantidade_usada",
                                    "unidade_usada",
                                    "status",
                                    "observacoes",
                                    "confianca",
                                ],
                                "properties": {
                                    "insumo_id": item_nullable_string,
                                    "nome": item_nullable_string,
                                    "categoria": item_nullable_string,
                                    "quantidade_comprada": item_nullable_number,
                                    "unidade_compra": item_nullable_string,
                                    "preco_total": item_nullable_number,
                                    "quantidade_usada": item_nullable_number,
                                    "unidade_usada": item_nullable_string,
                                    "status": {"type": "string"},
                                    "observacoes": item_nullable_string,
                                    "confianca": item_nullable_number,
                                },
                            },
                        },
                        "custos_adicionais": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "tipo",
                                    "nome",
                                    "valor",
                                    "aplicacao",
                                    "status",
                                    "observacoes",
                                    "confianca",
                                ],
                                "properties": {
                                    "tipo": {"type": "string"},
                                    "nome": item_nullable_string,
                                    "valor": item_nullable_number,
                                    "aplicacao": {"type": "string"},
                                    "status": {"type": "string"},
                                    "observacoes": item_nullable_string,
                                    "confianca": item_nullable_number,
                                },
                            },
                        },
                        "preparo": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "modo_preparo",
                                "tempo_preparo_minutos",
                                "tempo_forno_minutos",
                                "temperatura_forno",
                                "observacoes",
                            ],
                            "properties": {
                                "modo_preparo": item_nullable_string,
                                "tempo_preparo_minutos": item_nullable_number,
                                "tempo_forno_minutos": item_nullable_number,
                                "temperatura_forno": item_nullable_string,
                                "observacoes": item_nullable_string,
                            },
                        },
                    },
                },
                "perguntas_sugeridas": {"type": "array", "items": {"type": "string"}},
                "avisos": {"type": "array", "items": {"type": "string"}},
                "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "strict": True,
    }


def _catalogo_de_produtos_para_ia() -> list[dict]:
    return [
        {
            "id": produto["id"],
            "nome": produto["nome"],
            "descricao": produto.get("descricao"),
        }
        for produto in servico_de_produtos.listar_produtos(somente_ativos=True)
    ]


def _montar_ingredientes_para_confirmacao(
    ingredientes_draft: list[dict],
) -> list[RequisicaoIngredienteReceita]:
    ingredientes = []
    for item in ingredientes_draft:
        nome = item.get("nome")
        quantidade_usada = _decimal_obrigatorio(item.get("quantidade_usada"), "quantidade_usada")
        unidade_usada = item.get("unidade_usada")
        if not nome or not unidade_usada:
            raise BadRequestError(
                "Ingrediente incompleto para confirmacao.",
                {"ingrediente": item},
            )
        _validar_unidades_do_ingrediente_para_confirmacao(item)
        insumo_id = _resolver_ou_criar_insumo(item)
        ingredientes.append(
            RequisicaoIngredienteReceita(
                insumo_id=insumo_id,
                nome=nome,
                quantidade_usada=quantidade_usada,
                unidade=unidade_usada,
                status=_status_de_custo(item.get("status"), padrao="PENDENTE"),
                observacoes=item.get("observacoes"),
            )
        )
    return ingredientes


def _resolver_ou_criar_insumo(item: dict) -> UUID | None:
    insumo_id = _uuid_ou_none(item.get("insumo_id"))
    if insumo_id:
        servico_de_custos.buscar_insumo(insumo_id)
        return insumo_id
    if item.get("salvar_como_insumo") is False:
        return None
    insumo_existente = _buscar_insumo_existente_para_ingrediente(item)
    if insumo_existente:
        if _tem_dados_de_compra_completos(item):
            insumo_atualizado = servico_de_custos.atualizar_insumo(
                UUID(insumo_existente["id"]),
                RequisicaoAtualizarInsumo(
                    nome=item.get("nome") or insumo_existente["nome"],
                    categoria=item.get("categoria") or insumo_existente.get("categoria"),
                    quantidade_comprada=_decimal_ou_none(item.get("quantidade_comprada")),
                    unidade_compra=item.get("unidade_compra"),
                    preco_total=_decimal_ou_none(item.get("preco_total")),
                    status=_status_de_custo(item.get("status"), padrao=insumo_existente["status"]),
                    observacoes=item.get("observacoes") or insumo_existente.get("observacoes"),
                ),
            )
            return UUID(insumo_atualizado["id"])
        return UUID(insumo_existente["id"])

    quantidade = _decimal_ou_none(item.get("quantidade_comprada"))
    unidade = item.get("unidade_compra")
    preco_total = _decimal_ou_none(item.get("preco_total"))
    if not quantidade or not unidade or preco_total is None:
        return None
    insumo = servico_de_custos.criar_insumo(
        RequisicaoCriarInsumo(
            nome=item.get("nome") or "Insumo sem nome",
            categoria=item.get("categoria"),
            quantidade_comprada=quantidade,
            unidade_compra=unidade,
            preco_total=preco_total,
            status=_status_de_custo(item.get("status"), padrao="ESTIMADO"),
            observacoes=item.get("observacoes"),
        )
    )
    return UUID(insumo["id"])


def _atualizar_preco_custo_do_produto(
    *,
    produto_id: UUID,
    custo_por_unidade: Decimal,
    vigente_desde: date,
    motivo: str | None,
) -> dict | None:
    produto = servico_de_produtos.buscar_produto(produto_id)
    preco_atual = produto.get("preco_atual")
    if not preco_atual:
        return None

    if preco_atual["vigente_desde"] == vigente_desde.isoformat():
        preco = (
            get_supabase_client()
            .table("versoes_preco_produto")
            .update(
                to_db_payload(
                    {
                        "preco_custo": _arredondar_moeda(custo_por_unidade),
                        "motivo": motivo or preco_atual.get("motivo"),
                    }
                )
            )
            .eq("id", preco_atual["id"])
            .execute()
            .data[0]
        )
        registrar_evento_na_linha_do_tempo(
            get_supabase_client(),
            tipo_evento="preco_custo_produto_atualizado",
            titulo=f"Custo atualizado: {produto['nome']}",
            tipo_entidade="produto",
            entidade_id=produto_id,
            detalhes={"preco": preco, "motivo": motivo},
        )
        return preco

    return servico_de_produtos.criar_versao_de_preco(
        produto_id,
        RequisicaoCriarVersaoDePreco(
            preco_venda=Decimal(str(preco_atual["preco_venda"])),
            preco_custo=_arredondar_moeda(custo_por_unidade),
            vigente_desde=vigente_desde,
            motivo=motivo,
        ),
    )


def _resolver_proxima_acao(sessao: dict, *, produto_id: UUID | None) -> str:
    if sessao["situacao"] == "confirmado":
        return "mostrar_custo_confirmado"
    if sessao["situacao"] == "descartado":
        return "sessao_descartada"
    if not produto_id:
        return "vincular_produto"
    if sessao.get("pendencias"):
        return "resolver_pendencias"
    if sessao["situacao"] == "pronto_para_confirmar":
        return "revisar_e_confirmar"
    return "enviar_dados_de_custo"


def _resolver_finalidade_entrada(
    sessao: dict,
    *,
    finalidade: str,
    contexto: str | None,
) -> str:
    finalidade_normalizada = str(finalidade or "auto").strip().lower()
    if finalidade_normalizada in FINALIDADES_ENTRADA and finalidade_normalizada != "auto":
        return finalidade_normalizada

    contexto_normalizado = _normalizar_chave(contexto or "")
    if _contexto_indica_compras(contexto_normalizado):
        return "compras"
    if _contexto_indica_receita(contexto_normalizado):
        return "receita"

    produto_id = _uuid_ou_none(sessao.get("produto_id"))
    fase = _resolver_fase(sessao, produto_id=produto_id)
    if fase in {"vinculando_produto", "coletando_ingredientes"}:
        return "receita"
    if fase == "coletando_precos":
        return "compras"
    return "completo"


def _contexto_indica_compras(contexto_normalizado: str) -> bool:
    palavras = {
        "nota",
        "cupom",
        "mercado",
        "compra",
        "compras",
        "preco",
        "precos",
        "valor",
        "valores",
        "nf",
        "fiscal",
        "recibo",
    }
    return (
        any(palavra in contexto_normalizado.split() for palavra in palavras)
        or "r " in contexto_normalizado
    )


def _contexto_indica_receita(contexto_normalizado: str) -> bool:
    palavras = {
        "receita",
        "ingrediente",
        "ingredientes",
        "preparo",
        "modo",
        "rendimento",
        "massa",
    }
    return any(palavra in contexto_normalizado.split() for palavra in palavras)


def _aplicar_finalidade_ao_rascunho_extraido(rascunho: dict, *, finalidade: str) -> dict:
    rascunho = _normalizar_rascunho(rascunho, produto_id=rascunho.get("produto_id"))
    finalidade = finalidade if finalidade in FINALIDADES_ENTRADA else "auto"
    if finalidade == "receita":
        rascunho["ingredientes"] = [
            _manter_apenas_dados_de_receita(item) for item in rascunho["ingredientes"]
        ]
        return rascunho

    if finalidade == "compras":
        rascunho["receita"] = _limpar_receita_para_entrada_de_compras(rascunho["receita"])
        rascunho["preparo"] = _normalizar_rascunho({}).get("preparo", {})
        rascunho["custos_adicionais"] = []
        rascunho["ingredientes"] = [
            _manter_apenas_dados_de_compra(item) for item in rascunho["ingredientes"]
        ]
        return rascunho

    if finalidade == "auto":
        rascunho["ingredientes"] = [
            _limpar_compra_copiada_da_receita(item) for item in rascunho["ingredientes"]
        ]
    return rascunho


def _manter_apenas_dados_de_receita(ingrediente: dict) -> dict:
    item = dict(ingrediente)
    if item.get("preco_total") is None:
        if item.get("quantidade_usada") is None:
            item["quantidade_usada"] = item.get("quantidade_comprada")
        if item.get("unidade_usada") is None:
            item["unidade_usada"] = item.get("unidade_compra")
    item["quantidade_comprada"] = None
    item["unidade_compra"] = None
    item["preco_total"] = None
    item["insumo_id"] = None
    return item


def _manter_apenas_dados_de_compra(ingrediente: dict) -> dict:
    item = dict(ingrediente)
    if not item.get("quantidade_comprada") and item.get("quantidade_usada"):
        item["quantidade_comprada"] = item.get("quantidade_usada")
    if not item.get("unidade_compra") and item.get("unidade_usada"):
        item["unidade_compra"] = item.get("unidade_usada")
    item["quantidade_usada"] = None
    item["unidade_usada"] = None
    return item


def _limpar_receita_para_entrada_de_compras(receita: dict) -> dict:
    return {
        "nome": None,
        "rendimento": None,
        "unidade_rendimento": None,
        "status": receita.get("status") or "PENDENTE",
        "observacoes": None,
    }


def _limpar_compra_copiada_da_receita(ingrediente: dict) -> dict:
    item = dict(ingrediente)
    if item.get("preco_total") is not None:
        return item
    quantidade_compra = _decimal_ou_none(item.get("quantidade_comprada"))
    quantidade_uso = _decimal_ou_none(item.get("quantidade_usada"))
    unidade_compra = _normalizar_unidade_texto(item.get("unidade_compra"))
    unidade_uso = _normalizar_unidade_texto(item.get("unidade_usada"))
    if (
        quantidade_compra is not None
        and quantidade_uso is not None
        and quantidade_compra == quantidade_uso
        and unidade_compra
        and unidade_compra == unidade_uso
    ):
        item["quantidade_comprada"] = None
        item["unidade_compra"] = None
    return item


def _resolver_fase(sessao: dict, *, produto_id: UUID | None) -> str:
    situacao = sessao["situacao"]
    if situacao == "confirmado":
        return "confirmada"
    if situacao == "descartado":
        return "descartada"
    if not produto_id:
        return "vinculando_produto"

    rascunho = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id)
    if not rascunho["ingredientes"] or not _decimal_ou_none(rascunho["receita"].get("rendimento")):
        return "coletando_ingredientes"
    if any(_ingrediente_precisa_de_preco_ou_unidade(item) for item in rascunho["ingredientes"]):
        return "coletando_precos"
    return "revisando"


def _ingrediente_precisa_de_preco_ou_unidade(ingrediente: dict) -> bool:
    if not ingrediente.get("unidade_usada"):
        return True
    if not servico_de_custos.unidade_suportada(ingrediente.get("unidade_usada")):
        return True
    if ingrediente.get("insumo_id"):
        return False
    if _tem_dados_de_compra_completos(ingrediente):
        return not servico_de_custos.unidade_suportada(ingrediente.get("unidade_compra"))
    return _buscar_insumo_existente_para_ingrediente(ingrediente) is None


def _identificar_produto_no_texto(texto: str) -> UUID | None:
    texto_normalizado = _normalizar_chave(texto)
    for produto in servico_de_produtos.listar_produtos(somente_ativos=True):
        if _normalizar_chave(produto["nome"]) in texto_normalizado:
            return UUID(produto["id"])
    return None


def _extrair_rendimento(texto: str) -> Decimal | None:
    padrao = r"(?:rendeu|rende|rendimento(?: de)?|faz)\s+(\d+(?:[,.]\d+)?)"
    match = re.search(padrao, texto, flags=re.IGNORECASE)
    if not match:
        return None
    return _decimal_ou_none(match.group(1))


def _extrair_ingredientes_simples(texto: str) -> list[dict]:
    ingredientes = []
    padrao = re.compile(
        r"(?P<qtd>\d+(?:[,.]\d+)?)\s*"
        r"(?P<un>kg|g|ml|l|copo|copos|xicara|xicaras|xícara|xícaras|un|unidade|unidades)"
        r"\s+(?:de\s+)?(?P<nome>[a-zA-Z0-9 çÇãÃõÕáÁéÉíÍóÓúÚâÂêÊôÔ_-]+?)"
        r"(?:\s+(?:por|custou|custa|saiu|preco|preço)\s*(?:r\$)?\s*"
        r"(?P<preco>\d+(?:[,.]\d+)?))?(?:,|;|\.|\n|$)",
        flags=re.IGNORECASE,
    )
    for match in padrao.finditer(texto):
        nome = match.group("nome").strip()
        if not nome:
            continue
        ingredientes.append(
            _normalizar_ingrediente(
                {
                    "nome": nome,
                    "quantidade_comprada": match.group("qtd"),
                    "unidade_compra": match.group("un"),
                    "preco_total": match.group("preco"),
                    "quantidade_usada": match.group("qtd"),
                    "unidade_usada": match.group("un"),
                    "status": "PRECISA_REVISAR",
                    "confianca": 0.35,
                }
            )
        )
    return ingredientes


def _valor_custo_adicional_para_receita(
    custo: dict,
    rendimento: Decimal | None,
) -> Decimal | None:
    valor = _decimal_ou_none(custo.get("valor"))
    if valor is None:
        return None
    if custo.get("aplicacao") == "por_unidade":
        if rendimento and rendimento > 0:
            return _arredondar_moeda(valor * rendimento)
        return _arredondar_moeda(valor)
    return _arredondar_moeda(valor)


def _observacao_do_custo_adicional(custo: dict) -> str | None:
    partes = []
    if custo.get("observacoes"):
        partes.append(custo["observacoes"])
    if custo.get("aplicacao"):
        partes.append(f"Aplicacao informada no assistente: {custo['aplicacao']}.")
    return " ".join(partes) or None


def _tipo_custo_adicional(valor) -> str:
    valor_normalizado = str(valor or "outro").strip().lower()
    return valor_normalizado if valor_normalizado in TIPOS_CUSTO_ADICIONAL else "outro"


def _validar_unidades_do_ingrediente_para_confirmacao(item: dict) -> None:
    unidade_usada = item.get("unidade_usada")
    if not servico_de_custos.unidade_suportada(unidade_usada):
        raise BadRequestError(
            "Unidade usada no ingrediente ainda nao pode ser gravada.",
            {"ingrediente": item.get("nome"), "unidade_usada": unidade_usada},
        )

    unidade_compra = item.get("unidade_compra")
    if (
        unidade_compra
        and _tem_dados_de_compra_completos(item)
        and not servico_de_custos.unidade_suportada(unidade_compra)
    ):
        raise BadRequestError(
            "Unidade de compra do ingrediente ainda nao pode ser gravada.",
            {"ingrediente": item.get("nome"), "unidade_compra": unidade_compra},
        )


def _buscar_insumo_existente_para_ingrediente(item: dict) -> dict | None:
    nome = item.get("nome")
    if not nome:
        return None
    insumos = servico_de_custos.listar_insumos()
    nome_normalizado = _normalizar_nome_ingrediente(nome)
    for insumo in insumos:
        if _normalizar_nome_ingrediente(insumo["nome"]) == nome_normalizado:
            return insumo

    candidatos = [
        insumo
        for insumo in insumos
        if _nomes_ingredientes_compativeis(nome, insumo["nome"])
    ]
    return candidatos[0] if len(candidatos) == 1 else None


def _tem_dados_de_compra_completos(item: dict) -> bool:
    return (
        _decimal_ou_none(item.get("quantidade_comprada")) is not None
        and bool(item.get("unidade_compra"))
        and _decimal_ou_none(item.get("preco_total")) is not None
    )


def _tem_algum_dado_de_compra(item: dict) -> bool:
    return any(
        item.get(chave) is not None
        for chave in ("quantidade_comprada", "unidade_compra", "preco_total")
    )


def _descrever_conversao_aproximada(unidade: str | None) -> str | None:
    if not unidade:
        return None
    return servico_de_custos.descrever_unidade_aproximada(unidade)


def _status_de_custo(valor, *, padrao: str = "PENDENTE") -> str:
    status = str(valor or padrao).strip().upper()
    return status if status in STATUS_CUSTO_VALIDOS else padrao


def _consolidar_status(statuses: list[str]) -> str:
    if not statuses:
        return "PENDENTE"
    return max(statuses, key=lambda status: STATUS_ORDEM.get(status, 0))


def _chave_ingrediente(item: dict) -> str:
    if item.get("insumo_id"):
        return f"id:{item['insumo_id']}"
    return f"nome:{_normalizar_chave(item.get('nome') or '')}"


def _nomes_ingredientes_compativeis(nome_a: str | None, nome_b: str | None) -> bool:
    if not nome_a or not nome_b:
        return False
    normalizado_a = _normalizar_nome_ingrediente(nome_a)
    normalizado_b = _normalizar_nome_ingrediente(nome_b)
    if not normalizado_a or not normalizado_b:
        return False
    if normalizado_a == normalizado_b:
        return True

    tokens_a = set(normalizado_a.split())
    tokens_b = set(normalizado_b.split())
    if len(tokens_a) < 2 and len(tokens_b) < 2:
        return False
    comuns = tokens_a & tokens_b
    if not comuns:
        return False
    cobertura_menor = len(comuns) / min(len(tokens_a), len(tokens_b))
    cobertura_maior = len(comuns) / max(len(tokens_a), len(tokens_b))
    return cobertura_menor >= 0.75 and cobertura_maior >= 0.45


def _normalizar_nome_ingrediente(nome: str) -> str:
    texto = _normalizar_chave(nome)
    substituicoes = {
        "mucarela": "mussarela",
        "mozarela": "mussarela",
        "mozzarella": "mussarela",
    }
    tokens = []
    for token in texto.split():
        token = substituicoes.get(token, token)
        if token in STOPWORDS_INGREDIENTE or token in DESCRITORES_INGREDIENTE:
            continue
        tokens.append(token)
    return " ".join(tokens)


def _escolher_nome_ingrediente(nome_atual: str | None, nome_novo: str | None) -> str | None:
    if not nome_atual:
        return nome_novo
    if not nome_novo:
        return nome_atual
    tokens_atual = set(_normalizar_nome_ingrediente(nome_atual).split())
    tokens_novo = set(_normalizar_nome_ingrediente(nome_novo).split())
    if len(tokens_novo) > len(tokens_atual):
        return nome_novo
    return nome_atual


def _chave_custo_adicional(item: dict) -> str:
    return f"{item.get('tipo') or 'outro'}:{_normalizar_chave(item.get('nome') or '')}"


def _uuid_ou_none(valor) -> UUID | None:
    if not valor:
        return None
    try:
        return valor if isinstance(valor, UUID) else UUID(str(valor))
    except (TypeError, ValueError):
        return None


def _uuid_str_ou_none(valor) -> str | None:
    uuid_valor = _uuid_ou_none(valor)
    return str(uuid_valor) if uuid_valor else None


def _texto_ou_none(valor) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _lista_ou_vazia(valor) -> list:
    return valor if isinstance(valor, list) else []


def _lista_de_textos(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [str(item).strip() for item in valor if str(item).strip()]


def _deduplicar_textos(valores: list[str]) -> list[str]:
    vistos = set()
    resultado = []
    for valor in valores:
        texto = str(valor).strip()
        chave = _normalizar_chave(texto)
        if texto and chave not in vistos:
            vistos.add(chave)
            resultado.append(texto)
    return resultado


def _decimal_ou_none(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _decimal_obrigatorio(valor, campo: str) -> Decimal:
    numero = _decimal_ou_none(valor)
    if numero is None or numero <= 0:
        raise BadRequestError(f"Campo numerico obrigatorio invalido: {campo}.")
    return numero


def _decimal_str_ou_none(valor) -> str | None:
    numero = _decimal_ou_none(valor)
    return str(numero) if numero is not None else None


def _float_ou_none(valor) -> float | None:
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return max(0, min(1, numero))


def _arredondar_moeda(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _arredondar_percentual(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalizar_chave(valor: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", valor)
    ascii_texto = sem_acento.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_texto.lower()).strip()


def _normalizar_unidade_texto(valor: str | None) -> str | None:
    if not valor:
        return None
    return _normalizar_chave(valor)
