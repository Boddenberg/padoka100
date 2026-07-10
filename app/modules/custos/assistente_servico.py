import base64
import io
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.modules.custos import servico as servico_de_custos
from app.modules.custos.assistant import ingredientes as assistant_ingredientes
from app.modules.custos.assistant import rascunho as assistant_rascunho
from app.modules.custos.assistant import valores as assistant_valores
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
from app.modules.custos.prompts.extracao_custeio import (
    formato_json_extracao_custeio,
    instrucoes_extracao_custeio,
)
from app.modules.midia.servico import enviar_midia_em_bytes
from app.modules.produtos import servico as servico_de_produtos
from app.modules.produtos.esquemas import RequisicaoCriarVersaoDePreco
from app.shared.db import encode_value, first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo

SESSOES_IMUTAVEIS = {"confirmado", "descartado"}
FINALIDADES_ENTRADA = {"auto", "receita", "compras", "completo"}

# Compatibilidade: o nucleo puro do assistente vive em
# app.modules.custos.assistant (valores, ingredientes, rascunho) e os prompts
# em app.modules.custos.prompts. Aliases preservam os nomes locais usados
# pelas funcoes de orquestracao que permanecem neste arquivo.
STATUS_CUSTO_VALIDOS = assistant_ingredientes.STATUS_CUSTO_VALIDOS
TIPOS_CUSTO_ADICIONAL = assistant_ingredientes.TIPOS_CUSTO_ADICIONAL
APLICACOES_CUSTO = assistant_ingredientes.APLICACOES_CUSTO
DESCRITORES_INGREDIENTE = assistant_ingredientes.DESCRITORES_INGREDIENTE
STOPWORDS_INGREDIENTE = assistant_ingredientes.STOPWORDS_INGREDIENTE
INGREDIENTES_GENERICOS_PARA_MATCH = assistant_ingredientes.INGREDIENTES_GENERICOS_PARA_MATCH

_uuid_ou_none = assistant_valores.uuid_ou_none
_uuid_str_ou_none = assistant_valores.uuid_str_ou_none
_texto_ou_none = assistant_valores.texto_ou_none
_normalizar_unidade_de_entrada = assistant_valores.normalizar_unidade_de_entrada
_lista_ou_vazia = assistant_valores.lista_ou_vazia
_lista_de_textos = assistant_valores.lista_de_textos
_deduplicar_textos = assistant_valores.deduplicar_textos
_decimal_ou_none = assistant_valores.decimal_ou_none
_decimal_obrigatorio = assistant_valores.decimal_obrigatorio
_decimal_str_ou_none = assistant_valores.decimal_str_ou_none
_decimal_str_limpa = assistant_valores.decimal_str_limpa
_float_ou_none = assistant_valores.float_ou_none
_arredondar_moeda = assistant_valores.arredondar_moeda
_arredondar_percentual = assistant_valores.arredondar_percentual
_normalizar_chave = assistant_valores.normalizar_chave
_normalizar_unidade_texto = assistant_valores.normalizar_unidade_texto

_status_de_custo = assistant_ingredientes.status_de_custo
_consolidar_status = assistant_ingredientes.consolidar_status
_chave_ingrediente = assistant_ingredientes.chave_ingrediente
_nomes_ingredientes_compativeis = assistant_ingredientes.nomes_ingredientes_compativeis
_normalizar_nome_ingrediente = assistant_ingredientes.normalizar_nome_ingrediente
_escolher_nome_ingrediente = assistant_ingredientes.escolher_nome_ingrediente
_chave_custo_adicional = assistant_ingredientes.chave_custo_adicional
_tipo_custo_adicional = assistant_ingredientes.tipo_custo_adicional
_tem_dados_de_compra_completos = assistant_ingredientes.tem_dados_de_compra_completos
_tem_algum_dado_de_compra = assistant_ingredientes.tem_algum_dado_de_compra
_texto_indica_quantidade_alternativa = assistant_ingredientes.texto_indica_quantidade_alternativa
_extrair_numeros_de_texto = assistant_ingredientes.extrair_numeros_de_texto
_inferir_unidade_da_quantidade_ambigua = (
    assistant_ingredientes.inferir_unidade_da_quantidade_ambigua
)

_normalizar_rascunho = assistant_rascunho.normalizar_rascunho
_normalizar_ingrediente = assistant_rascunho.normalizar_ingrediente
_normalizar_custo_adicional = assistant_rascunho.normalizar_custo_adicional
_equivalencia_explicita_na_unidade = assistant_rascunho.equivalencia_explicita_na_unidade
_mesclar_rascunhos = assistant_rascunho.mesclar_rascunhos
_mesclar_dict_sem_nones = assistant_rascunho.mesclar_dict_sem_nones
_mesclar_listas_por_chave = assistant_rascunho.mesclar_listas_por_chave
_mesclar_ingredientes = assistant_rascunho.mesclar_ingredientes

_instrucoes_extracao_custeio = instrucoes_extracao_custeio
_formato_json_extracao_custeio = formato_json_extracao_custeio


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
            origem=requisicao.origem,
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
    sessao = _sessao_com_estado_recalculado(sessao)
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


def _sessao_com_estado_recalculado(sessao: dict) -> dict:
    if sessao["situacao"] in SESSOES_IMUTAVEIS:
        return sessao
    produto_id = _uuid_ou_none(sessao.get("produto_id"))
    rascunho = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id)
    estado = _montar_estado_da_sessao(rascunho, produto_id=produto_id)
    return {
        **sessao,
        "situacao": estado["situacao"],
        "rascunho": rascunho,
        "perguntas": estado["perguntas"],
        "pendencias": estado["pendencias"],
        "avisos": estado["avisos"],
        "confianca_geral": estado["confianca_geral"],
        "custo_simulado": estado["custo_simulado"],
    }


def _montar_estado_da_sessao(rascunho: dict, *, produto_id: UUID | None) -> dict:
    rascunho_normalizado = _normalizar_rascunho(rascunho, produto_id=produto_id)
    custo_simulado = _simular_custo(rascunho_normalizado, produto_id=produto_id)
    fase = _resolver_fase_do_rascunho(rascunho_normalizado, produto_id=produto_id)
    pendencias = _consolidar_pendencias_para_fase(
        custo_simulado["pendencias"],
        rascunho_normalizado,
        fase=fase,
    )
    custo_simulado["pendencias"] = pendencias
    avisos = _deduplicar_textos(custo_simulado["avisos"] + rascunho_normalizado.get("avisos", []))
    perguntas = _montar_perguntas(rascunho_normalizado, pendencias, fase=fase)
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
        custo_total, custo_unitario, pendencia, metadados_calculo = _simular_ingrediente(
            ingrediente,
        )
        for campo_unidade in ("unidade_usada", "unidade_compra"):
            descricao = _descrever_conversao_aproximada(ingrediente.get(campo_unidade))
            if descricao:
                avisos.append(
                    f"Ingrediente {ingrediente.get('nome') or indice}: medida caseira "
                    f"convertida como {descricao}. Confirme se esse e o tamanho usado."
                )
        avisos.extend(metadados_calculo.get("avisos", []))
        if pendencia:
            pendencias.append(f"Ingrediente {indice}: {pendencia}")
        if custo_total is not None:
            custo_ingredientes += custo_total
        simulado["custo_unitario_base"] = _decimal_str_ou_none(custo_unitario)
        simulado["custo_total_estimado"] = _decimal_str_ou_none(custo_total)
        simulado.update(metadados_calculo.get("campos_simulados", {}))
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


def _simular_ingrediente(
    ingrediente: dict,
) -> tuple[Decimal | None, Decimal | None, str | None, dict]:
    nome = ingrediente.get("nome") or "sem nome"
    quantidade_usada = _decimal_ou_none(ingrediente.get("quantidade_usada"))
    unidade_usada = ingrediente.get("unidade_usada")
    if not nome:
        return None, None, "nome nao informado.", {}
    if not quantidade_usada or quantidade_usada <= 0:
        return None, None, f"{nome} sem quantidade usada.", {}
    if not unidade_usada:
        return None, None, f"{nome} sem unidade usada.", {}

    insumo_id = _uuid_ou_none(ingrediente.get("insumo_id"))
    try:
        if insumo_id:
            insumo = servico_de_custos.buscar_insumo(insumo_id)
            custo_unitario = Decimal(str(insumo["custo_por_unidade"]))
            quantidade_calculo, unidade_usada_calculo, metadados_calculo = (
                _resolver_uso_do_ingrediente_para_calculo(
                    ingrediente,
                    unidade_referencia=insumo["unidade_compra"],
                )
            )
            campos = metadados_calculo["campos_simulados"]
            campos["quantidade_comprada_calculo"] = None
            campos["unidade_compra_calculo"] = insumo["unidade_compra"]
            campos["preco_total_calculo"] = None
            custo_total = servico_de_custos._calcular_custo_ingrediente(
                custo_unitario,
                quantidade_calculo,
                unidade_usada_calculo,
                insumo["unidade_compra"],
            )
            campos["formula_calculo"] = _formula_calculo_ingrediente(
                quantidade=quantidade_calculo,
                unidade=unidade_usada_calculo,
                custo_unitario=custo_unitario,
                custo_total=custo_total,
            )
            return custo_total, custo_unitario, None, metadados_calculo

        quantidade_comprada = _decimal_ou_none(ingrediente.get("quantidade_comprada"))
        unidade_compra = ingrediente.get("unidade_compra")
        preco_total = _decimal_ou_none(ingrediente.get("preco_total"))
        insumo_existente = _buscar_insumo_existente_para_ingrediente(ingrediente)
        if insumo_existente and not _tem_dados_de_compra_completos(ingrediente):
            custo_unitario = Decimal(str(insumo_existente["custo_por_unidade"]))
            quantidade_calculo, unidade_usada_calculo, metadados_calculo = (
                _resolver_uso_do_ingrediente_para_calculo(
                    ingrediente,
                    unidade_referencia=insumo_existente["unidade_compra"],
                )
            )
            campos = metadados_calculo["campos_simulados"]
            campos["quantidade_comprada_calculo"] = None
            campos["unidade_compra_calculo"] = insumo_existente["unidade_compra"]
            campos["preco_total_calculo"] = None
            custo_total = servico_de_custos._calcular_custo_ingrediente(
                custo_unitario,
                quantidade_calculo,
                unidade_usada_calculo,
                insumo_existente["unidade_compra"],
            )
            campos["formula_calculo"] = _formula_calculo_ingrediente(
                quantidade=quantidade_calculo,
                unidade=unidade_usada_calculo,
                custo_unitario=custo_unitario,
                custo_total=custo_total,
            )
            return custo_total, custo_unitario, None, metadados_calculo

        if not quantidade_comprada or not unidade_compra or preco_total is None:
            return None, None, f"{nome} sem preco/quantidade de compra para calcular custo.", {}

        custo_unitario = servico_de_custos._calcular_custo_por_unidade(
            preco_total,
            quantidade_comprada,
            unidade_compra,
        )
        quantidade_calculo, unidade_usada_calculo, metadados_calculo = (
            _resolver_uso_do_ingrediente_para_calculo(
                ingrediente,
                unidade_referencia=unidade_compra,
            )
        )
        campos = metadados_calculo["campos_simulados"]
        campos["quantidade_comprada_calculo"] = str(quantidade_comprada)
        campos["unidade_compra_calculo"] = unidade_compra
        campos["preco_total_calculo"] = str(preco_total)
        custo_total = servico_de_custos._calcular_custo_ingrediente(
            custo_unitario,
            quantidade_calculo,
            unidade_usada_calculo,
            unidade_compra,
        )
        campos["formula_calculo"] = _formula_calculo_ingrediente(
            quantidade=quantidade_calculo,
            unidade=unidade_usada_calculo,
            custo_unitario=custo_unitario,
            custo_total=custo_total,
        )
        return custo_total, custo_unitario, None, metadados_calculo
    except BadRequestError as exc:
        return None, None, f"{nome}: {exc.message}", {}


def _montar_perguntas(rascunho: dict, pendencias: list[str], *, fase: str) -> list[dict]:
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

    ingredientes_sem_medida = _ingredientes_sem_dados_de_receita(rascunho["ingredientes"])
    if ingredientes_sem_medida:
        perguntas.append(
            {
                "id": "ingredientes.medidas_receita",
                "campo": None,
                "pergunta": (
                    "Complete as quantidades usadas na receita para: "
                    f"{_formatar_lista_nomes(ingredientes_sem_medida)}. "
                    "Pode responder tudo junto, por exemplo: "
                    "'ovos 2 unidades, leite 250 ml, oleo 1/2 copo'."
                ),
                "tipo_resposta": "texto",
                "prioridade": 1,
            }
        )

    ingredientes_sem_compra = _ingredientes_sem_dados_de_compra(rascunho["ingredientes"])
    if _fase_permite_perguntas_de_preco(fase) and ingredientes_sem_compra:
        perguntas.append(
            {
                "id": "ingredientes.dados_de_compra",
                "campo": None,
                "pergunta": (
                    "Agora preciso dos dados de compra para calcular o custo de: "
                    f"{_formatar_lista_nomes(ingredientes_sem_compra)}. "
                    "Voce pode responder em uma mensagem so com quantidade comprada e preco, "
                    "ou enviar a foto/print da notinha do mercado."
                ),
                "tipo_resposta": "texto_ou_arquivo",
                "prioridade": 2,
            }
        )

    for pergunta in _perguntas_sugeridas_para_fase(
        rascunho,
        fase=fase,
        ignorar_perguntas_de_medida=bool(ingredientes_sem_medida),
        ignorar_perguntas_de_rendimento=not _decimal_ou_none(rascunho["receita"].get("rendimento")),
    ):
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


def _ingredientes_sem_dados_de_receita(ingredientes: list[dict]) -> list[str]:
    nomes = []
    for indice, ingrediente in enumerate(ingredientes, start=1):
        if _ingrediente_precisa_de_dados_de_receita(ingrediente):
            nomes.append(ingrediente.get("nome") or f"ingrediente {indice}")
    return nomes


def _ingrediente_precisa_de_dados_de_receita(ingrediente: dict) -> bool:
    return not ingrediente.get("quantidade_usada") or not ingrediente.get("unidade_usada")


def _ingredientes_com_quantidade_ambigua(ingredientes: list[dict]) -> list[str]:
    nomes = []
    for indice, ingrediente in enumerate(ingredientes, start=1):
        if _ingrediente_tem_quantidade_ambigua(ingrediente):
            nomes.append(ingrediente.get("nome") or f"ingrediente {indice}")
    return nomes


def _ingrediente_tem_quantidade_ambigua(ingrediente: dict) -> bool:
    return bool(
        ingrediente.get("quantidade_usada_ambigua")
        or ingrediente.get("quantidade_usada_original")
    ) or _texto_indica_quantidade_alternativa(
        ingrediente.get("quantidade_usada"),
    ) or _texto_indica_quantidade_alternativa(ingrediente.get("unidade_usada"))


def _ingredientes_sem_dados_de_compra(ingredientes: list[dict]) -> list[str]:
    nomes = []
    for indice, ingrediente in enumerate(ingredientes, start=1):
        if _ingrediente_precisa_de_dados_de_compra(ingrediente):
            nomes.append(ingrediente.get("nome") or f"ingrediente {indice}")
    return nomes


def _ingrediente_precisa_de_dados_de_compra(ingrediente: dict) -> bool:
    if ingrediente.get("insumo_id"):
        return False
    if _tem_dados_de_compra_completos(ingrediente):
        return False
    return _buscar_insumo_existente_para_ingrediente(ingrediente) is None


def _resolver_uso_do_ingrediente_para_calculo(
    ingrediente: dict,
    *,
    unidade_referencia: str | None,
) -> tuple[Decimal, str, dict]:
    quantidade_original = _decimal_obrigatorio(
        ingrediente.get("quantidade_usada"),
        "quantidade_usada",
    )
    unidade_original = ingrediente.get("unidade_usada")
    quantidade_calculo = quantidade_original
    unidade_calculo = unidade_original
    avisos = []
    calculo_estimado = False
    nome = ingrediente.get("nome") or "ingrediente"

    estimativa_ambigua = _resolver_quantidade_ambigua_para_estimativa(ingrediente)
    if estimativa_ambigua:
        quantidade_calculo = estimativa_ambigua["quantidade"]
        unidade_calculo = estimativa_ambigua["unidade"] or unidade_calculo
        calculo_estimado = True
        avisos.append(
            f"Ingrediente {nome}: a receita indicava '{estimativa_ambigua['texto_original']}'. "
            f"Para estimar o custo, considerei {quantidade_calculo} {unidade_calculo}. "
            "Confirme se esta e a quantidade correta."
        )

    unidade_ajustada = _unidade_usada_para_calculo(ingrediente, unidade_calculo, unidade_referencia)
    if unidade_ajustada != unidade_calculo:
        calculo_estimado = True
        quantidade_ajustada = quantidade_calculo
        unidade_ajustada_final = unidade_ajustada
        equivalencia = _equivalencia_explicita_na_unidade(unidade_ajustada)
        if equivalencia:
            quantidade_ajustada = quantidade_calculo * equivalencia["fator_base"]
            unidade_ajustada_final = equivalencia["unidade_base"]
        avisos.append(
            f"Ingrediente {nome}: para calcular contra a compra em {unidade_referencia}, "
            f"considerei {quantidade_calculo} {unidade_calculo} como "
            f"{quantidade_ajustada} {unidade_ajustada_final}."
        )
        quantidade_calculo = quantidade_ajustada
        unidade_calculo = unidade_ajustada_final

    return (
        quantidade_calculo,
        unidade_calculo,
        {
            "avisos": avisos,
            "campos_simulados": {
                "quantidade_usada_calculo": str(quantidade_calculo),
                "unidade_usada_calculo": unidade_calculo,
                "calculo_estimado": calculo_estimado,
                "avisos_calculo": avisos,
            },
        },
    )


def _resolver_quantidade_ambigua_para_estimativa(ingrediente: dict) -> dict | None:
    if not _ingrediente_tem_quantidade_ambigua(ingrediente):
        return None
    texto_original = ingrediente.get("quantidade_usada_original") or " ".join(
        str(valor).strip()
        for valor in (ingrediente.get("quantidade_usada"), ingrediente.get("unidade_usada"))
        if valor is not None and str(valor).strip()
    )
    numeros = _extrair_numeros_de_texto(texto_original)
    quantidade = _decimal_ou_none(
        ingrediente.get("quantidade_usada_estimativa") or ingrediente.get("quantidade_usada")
    )
    if quantidade is None and len(numeros) >= 2:
        quantidade = max(numeros)
    if quantidade is None:
        return None
    return {
        "quantidade": quantidade,
        "unidade": _inferir_unidade_da_quantidade_ambigua(texto_original, ingrediente),
        "texto_original": texto_original,
    }


def _unidade_usada_para_calculo(
    ingrediente: dict,
    unidade_usada: str | None,
    unidade_referencia: str | None,
) -> str | None:
    if not unidade_usada:
        return unidade_usada
    unidade_sal = _unidade_sal_para_calculo_em_massa(ingrediente, unidade_usada, unidade_referencia)
    if unidade_sal:
        return unidade_sal
    if servico_de_custos.unidade_suportada(unidade_usada):
        return unidade_usada
    if (
        _unidade_generica_de_embalagem(unidade_usada)
        and _unidade_tem_embalagem_com_equivalencia(unidade_referencia)
    ):
        return unidade_referencia
    return unidade_usada


def _unidade_sal_para_calculo_em_massa(
    ingrediente: dict,
    unidade_usada: str | None,
    unidade_referencia: str | None,
) -> str | None:
    if not _ingrediente_e_sal(ingrediente) or not _unidade_representa_massa(unidade_referencia):
        return None
    unidade_normalizada = _normalizar_unidade_texto(unidade_usada)
    if not unidade_normalizada or "colher" not in unidade_normalizada:
        return None
    if "cha" in unidade_normalizada:
        return "5g"
    return "15g"


def _ingrediente_e_sal(ingrediente: dict) -> bool:
    return "sal" in set(_normalizar_nome_ingrediente(ingrediente.get("nome") or "").split())


def _unidade_representa_massa(unidade: str | None) -> bool:
    if not unidade:
        return False
    equivalencia = _equivalencia_explicita_na_unidade(unidade)
    if equivalencia:
        return equivalencia["tipo"] == "massa"
    return _normalizar_unidade_texto(unidade) in {
        "g",
        "grama",
        "gramas",
        "kg",
        "quilo",
        "quilos",
    }


def _formula_calculo_ingrediente(
    *,
    quantidade: Decimal,
    unidade: str,
    custo_unitario: Decimal,
    custo_total: Decimal,
) -> str:
    return (
        f"{quantidade} {unidade} x R$ {_decimal_preciso_str(custo_unitario)} "
        f"= R$ {_decimal_moeda_str(custo_total)}"
    )


def _decimal_moeda_str(valor: Decimal) -> str:
    return str(_arredondar_moeda(valor)).replace(".", ",")


def _decimal_preciso_str(valor: Decimal) -> str:
    return format(valor.normalize(), "f").replace(".", ",")


def _unidade_generica_de_embalagem(unidade: str | None) -> bool:
    unidade_normalizada = _normalizar_unidade_texto(unidade)
    if not unidade_normalizada:
        return False
    tokens = set(unidade_normalizada.split())
    return bool(
        tokens
        & {
            "caixa",
            "caixinha",
            "embalagem",
            "frasco",
            "frasquinho",
            "garrafa",
            "garrafinha",
            "lata",
            "latinha",
            "pacote",
            "pacotinho",
            "pct",
            "pote",
            "potinho",
            "sache",
            "saco",
            "saquinho",
        }
    )


def _unidade_tem_embalagem_com_equivalencia(unidade: str | None) -> bool:
    return _unidade_generica_de_embalagem(unidade) and bool(
        _equivalencia_explicita_na_unidade(unidade)
    )


def _fase_permite_perguntas_de_preco(fase: str) -> bool:
    return fase in {"coletando_precos", "revisando"}


def _formatar_lista_nomes(nomes: list[str], *, limite: int = 6) -> str:
    nomes_limpos = [nome for nome in _deduplicar_textos(nomes) if nome]
    if not nomes_limpos:
        return "os ingredientes pendentes"
    exibidos = nomes_limpos[:limite]
    texto = ", ".join(exibidos)
    restantes = len(nomes_limpos) - len(exibidos)
    if restantes > 0:
        texto = f"{texto} e mais {restantes}"
    return texto


def _perguntas_sugeridas_para_fase(
    rascunho: dict,
    *,
    fase: str,
    ignorar_perguntas_de_medida: bool = False,
    ignorar_perguntas_de_rendimento: bool = False,
) -> list[str]:
    perguntas = []
    for pergunta in rascunho.get("perguntas_sugeridas", []):
        if not _fase_permite_perguntas_de_preco(fase) and _texto_indica_preco_ou_compra(pergunta):
            continue
        if ignorar_perguntas_de_medida and _texto_indica_medida_de_receita(pergunta):
            continue
        if ignorar_perguntas_de_rendimento and _texto_indica_rendimento(pergunta):
            continue
        perguntas.append(pergunta)
    return _deduplicar_textos(perguntas)[:3]


def _texto_indica_preco_ou_compra(texto: str | None) -> bool:
    texto_normalizado = _normalizar_chave(texto or "")
    palavras = {
        "preco",
        "precos",
        "custou",
        "custa",
        "compra",
        "compras",
        "comprado",
        "comprada",
        "comprou",
        "mercado",
        "nota",
        "notinha",
        "cupom",
        "fiscal",
        "valor",
        "valores",
    }
    tokens = set(texto_normalizado.split())
    return bool(tokens & palavras) or "r " in texto_normalizado


def _texto_indica_medida_de_receita(texto: str | None) -> bool:
    texto_normalizado = _normalizar_chave(texto or "")
    palavras = {
        "quantidade",
        "quantidades",
        "quanto",
        "quantos",
        "unidade",
        "unidades",
        "peso",
        "gramatura",
        "gramas",
        "ml",
    }
    return bool(set(texto_normalizado.split()) & palavras)


def _texto_indica_rendimento(texto: str | None) -> bool:
    texto_normalizado = _normalizar_chave(texto or "")
    return any(palavra in texto_normalizado.split() for palavra in {"rendimento", "rende"})


def _consolidar_pendencias_para_fase(
    pendencias: list[str],
    rascunho: dict,
    *,
    fase: str,
) -> list[str]:
    pendencias_de_medida = [
        pendencia for pendencia in pendencias if _pendencia_indica_medida_de_receita(pendencia)
    ]
    pendencias_sem_preco_ou_medida = [
        pendencia
        for pendencia in pendencias
        if not _pendencia_indica_preco_ou_compra(pendencia)
        and not _pendencia_indica_medida_de_receita(pendencia)
    ]
    pendencias_de_preco = [
        pendencia for pendencia in pendencias if _pendencia_indica_preco_ou_compra(pendencia)
    ]

    pendencias_consolidadas = list(pendencias_sem_preco_ou_medida)
    if pendencias_de_medida:
        ingredientes_sem_medida = _ingredientes_sem_dados_de_receita(rascunho["ingredientes"])
        pendencias_consolidadas.append(
            "Complete as quantidades/unidades usadas na receita: "
            f"{_formatar_lista_nomes(ingredientes_sem_medida)}."
        )

    if not pendencias_de_preco:
        return _deduplicar_textos(pendencias_consolidadas)

    if not _fase_permite_perguntas_de_preco(fase):
        return _deduplicar_textos(pendencias_consolidadas)

    ingredientes_sem_compra = _ingredientes_sem_dados_de_compra(rascunho["ingredientes"])
    resumo = (
        "Informe os dados de compra/preco dos ingredientes para calcular o custo: "
        f"{_formatar_lista_nomes(ingredientes_sem_compra)}."
    )
    return _deduplicar_textos(pendencias_consolidadas + [resumo])


def _pendencia_indica_preco_ou_compra(texto: str | None) -> bool:
    texto_normalizado = _normalizar_chave(texto or "")
    return (
        "sem preco quantidade de compra" in texto_normalizado
        or "dados de compra preco" in texto_normalizado
        or "unidade de compra" in texto_normalizado
    )


def _pendencia_indica_medida_de_receita(texto: str | None) -> bool:
    texto_normalizado = _normalizar_chave(texto or "")
    return (
        "sem quantidade usada" in texto_normalizado
        or "sem unidade usada" in texto_normalizado
        or "unidade usada" in texto_normalizado
    )


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
    origem: str,
) -> dict | None:
    produto = servico_de_produtos.buscar_produto(produto_id)
    preco_atual = produto.get("preco_atual")
    if not preco_atual:
        return None

    gerado_por_ia = origem == "ia"
    if preco_atual["vigente_desde"] == vigente_desde.isoformat():
        preco = (
            get_supabase_client()
            .table("versoes_preco_produto")
            .update(
                to_db_payload(
                    {
                        "preco_custo": _arredondar_moeda(custo_por_unidade),
                        "motivo": motivo or preco_atual.get("motivo"),
                        "origem": origem,
                        "gerado_por_ia": gerado_por_ia,
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
            detalhes={"preco": preco, "motivo": motivo, "origem": origem},
        )
        return preco

    return servico_de_produtos.criar_versao_de_preco(
        produto_id,
        RequisicaoCriarVersaoDePreco(
            preco_venda=Decimal(str(preco_atual["preco_venda"])),
            preco_custo=_arredondar_moeda(custo_por_unidade),
            vigente_desde=vigente_desde,
            motivo=motivo,
            origem=origem,
            gerado_por_ia=gerado_por_ia,
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
        rascunho["perguntas_sugeridas"] = [
            pergunta
            for pergunta in rascunho["perguntas_sugeridas"]
            if not _texto_indica_preco_ou_compra(pergunta)
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

    rascunho = _normalizar_rascunho(sessao.get("rascunho") or {}, produto_id=produto_id)
    return _resolver_fase_do_rascunho(rascunho, produto_id=produto_id)


def _resolver_fase_do_rascunho(rascunho: dict, *, produto_id: UUID | str | None) -> str:
    produto_id_resolvido = _uuid_ou_none(produto_id or rascunho.get("produto_id"))
    if not produto_id_resolvido:
        return "vinculando_produto"
    if (
        not rascunho["ingredientes"]
        or not _decimal_ou_none(rascunho["receita"].get("rendimento"))
        or any(_ingrediente_precisa_de_dados_de_receita(item) for item in rascunho["ingredientes"])
    ):
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
    return servico_de_custos.buscar_insumo_compativel_por_nome(nome)


def _descrever_conversao_aproximada(unidade: str | None) -> str | None:
    if not unidade:
        return None
    return servico_de_custos.descrever_unidade_aproximada(unidade)


