import io
import json
from datetime import date
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError, BadRequestError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import executar_lista_opcional, tabela_ausente
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
)
from app.modules.ia.domain import acoes as _acoes
from app.modules.ia.domain import analise as _analise
from app.modules.ia.domain import fallback as _fallback
from app.modules.ia.domain import texto as _texto
from app.modules.ia.esquemas import (
    RequisicaoInterpretarComandoDeIA,
    RequisicaoInterpretarComandoDeVenda,
)
from app.modules.ia.prompts.command_interpreter import COMMAND_INTERPRETER_INSTRUCTIONS
from app.modules.midia.servico import enviar_midia_em_bytes
from app.modules.produtos import public as produtos_public
from app.modules.relatorios import servico as servico_de_relatorios
from app.modules.vendas import servico as servico_de_vendas
from app.modules.vendas.esquemas import RequisicaoCancelarVenda, RequisicaoRegistrarVenda
from app.shared.datas import data_operacional_hoje, validar_periodo
from app.shared.db import encode_value, first_or_none, to_db_payload

# Compatibilidade: a logica pura de interpretacao vive em app.modules.ia.domain.
# Mantemos aliases sob os nomes internos ja usados no restante deste servico.
ACAO_REGISTRAR_VENDA = _acoes.ACAO_REGISTRAR_VENDA
ACAO_REGISTRAR_PRODUCAO = _acoes.ACAO_REGISTRAR_PRODUCAO
ACAO_ABRIR_DIA_DE_VENDA = _acoes.ACAO_ABRIR_DIA_DE_VENDA
ACAO_FECHAR_DIA_DE_VENDA = _acoes.ACAO_FECHAR_DIA_DE_VENDA
ACAO_CANCELAR_VENDA = _acoes.ACAO_CANCELAR_VENDA
ACAO_CANCELAR_ITEM_VENDA = _acoes.ACAO_CANCELAR_ITEM_VENDA
ACAO_DESCONHECIDO = _acoes.ACAO_DESCONHECIDO
ACOES_SUPORTADAS = _acoes.ACOES_SUPORTADAS
_normalizar = _texto.normalizar
_normalizar_quantidade = _texto.normalizar_quantidade
_normalizar_confianca = _texto.normalizar_confianca
_normalizar_texto_opcional = _texto.normalizar_texto_opcional
_normalizar_data = _texto.normalizar_data
_normalizar_uuid_str = _texto.normalizar_uuid_str
_data_ou_none = _texto.data_ou_none
_data_ou_hoje = _texto.data_ou_hoje
_extrair_data_do_texto = _texto.extrair_data_do_texto
_extrair_uuid_do_texto = _texto.extrair_uuid_do_texto
_buscar_quantidade_antes = _texto.buscar_quantidade_antes
_formatar_data = _texto.formatar_data
_formatar_moeda = _texto.formatar_moeda
_formatar_itens = _texto.formatar_itens
_formatar_itens_da_venda = _texto.formatar_itens_da_venda
_formatar_resumo_da_venda = _texto.formatar_resumo_da_venda
_total_da_venda = _texto.total_da_venda
_interpretar_com_fallback = _fallback.interpretar_com_fallback
_normalizar_interpretacao = _fallback.normalizar_interpretacao
_mensagem_inicial_da_acao = _fallback.mensagem_inicial_da_acao
_comando_pede_ultima_venda = _fallback.comando_pede_ultima_venda
_mensagem_cancelamento_sem_alvo_claro = _fallback.mensagem_cancelamento_sem_alvo_claro
_comando_menciona_cancelamento_por_valor = _fallback.comando_menciona_cancelamento_por_valor
_comando_parece_em_lote = _fallback.comando_parece_em_lote
_extrair_json_da_analise = _analise.extrair_json_da_analise
_normalizar_campos_da_analise = _analise.normalizar_campos_da_analise
_rotulo_periodo_da_analise = _analise.rotulo_periodo_da_analise
_gerar_analise_estruturada_local = _analise.gerar_analise_estruturada_local
_montar_texto_da_analise_estruturada = _analise.montar_texto_da_analise_estruturada
_gerar_analise_local = _analise.gerar_analise_local


def _normalizar_analise_estruturada(
    dados: dict,
    analise_texto: str,
    *,
    pergunta: str | None,
) -> dict:
    estrutura = _analise.normalizar_analise_estruturada(dados, analise_texto, pergunta=pergunta)
    return encode_value(estrutura)


def interpretar_comando(
    requisicao: RequisicaoInterpretarComandoDeIA,
    *,
    tipo_entrada: str = "texto",
    url_audio: str | None = None,
) -> dict:
    settings = get_settings()
    produtos = produtos_public.listar_produtos_ativos()

    modelo_usado = "fallback-parser"
    if settings.openai_text_configured:
        try:
            interpretacao = _interpretar_com_openai(requisicao.texto, produtos)
            modelo_usado = settings.openai_text_model_resolved
        except Exception:
            if not requisicao.permitir_fallback:
                raise
            interpretacao = _interpretar_com_fallback(requisicao.texto, produtos)
    else:
        interpretacao = _interpretar_com_fallback(requisicao.texto, produtos)

    interpretacao = _normalizar_interpretacao(
        interpretacao,
        produtos,
        texto_original=requisicao.texto,
    )
    dados_confirmacao = _montar_dados_confirmacao(
        interpretacao=interpretacao,
        dia_de_venda_id=requisicao.dia_de_venda_id,
        texto_original=requisicao.texto,
        tipo_entrada_venda="audio" if tipo_entrada == "audio" else "ia",
        url_audio=url_audio,
    )
    interacao = _criar_interacao_ia(
        dia_de_venda_id=_extrair_dia_de_venda_id_para_interacao(
            dados_confirmacao,
            requisicao.dia_de_venda_id,
        ),
        tipo_entrada=tipo_entrada,
        texto_original=requisicao.texto,
        url_audio=url_audio,
        acao_interpretada=interpretacao,
        dados_confirmacao=dados_confirmacao,
    )

    dados_confirmacao["interacao_ia_id"] = interacao["id"]
    if dados_confirmacao.get("venda"):
        dados_confirmacao["venda"]["interacao_ia_id"] = interacao["id"]
    get_supabase_client().table("interacoes_ia").update(
        to_db_payload({"dados_confirmacao": dados_confirmacao})
    ).eq("id", interacao["id"]).execute()

    mensagem_confirmacao = dados_confirmacao.get("mensagem_confirmacao")
    return {
        "interacao_ia_id": interacao["id"],
        "acao": dados_confirmacao["acao"],
        "precisa_confirmacao": dados_confirmacao["precisa_confirmacao"],
        "mensagem_assistente": mensagem_confirmacao or interpretacao["mensagem_assistente"],
        "mensagem_confirmacao": mensagem_confirmacao,
        "itens": interpretacao["itens"],
        "itens_nao_identificados": interpretacao["itens_nao_identificados"],
        "dados_confirmacao": dados_confirmacao,
        "modelo_usado": modelo_usado,
    }


def montar_dados_estruturados_periodo(
    *,
    data_inicio: str,
    data_fim: str,
    produto_id: UUID | None = None,
) -> dict:
    data_inicio_valor = date.fromisoformat(data_inicio)
    data_fim_valor = date.fromisoformat(data_fim)
    validar_periodo(data_inicio_valor, data_fim_valor)
    resumo = _montar_resumo_do_periodo_para_ia(
        data_inicio_valor,
        data_fim_valor,
        produto_id=produto_id,
    )
    produtos_por_id: dict[str, dict] = {}
    correcoes = []
    dias = []
    for dia in resumo["dias"]:
        dias.append(
            {
                "data": dia["data"],
                "status": dia["status"],
                "faturamentoTotal": dia["faturamento_total"],
                "quantidadeTotalProduzida": dia["total_produzido"],
                "quantidadeTotalVendida": dia["total_vendido"],
                "quantidadeTotalSobrando": dia["total_sobra"],
                "produtosEsgotados": [
                    produto["nome_produto"] for produto in dia["produtos_esgotados"]
                ],
            }
        )
        correcoes.extend(dia.get("correcoes", []))
        for produto in dia["produtos"]:
            produto_id_chave = produto["produto_id"]
            acumulado = produtos_por_id.setdefault(
                produto_id_chave,
                {
                    "produtoId": produto_id_chave,
                    "produto": produto["nome_produto"],
                    "totalProduzido": 0,
                    "totalVendido": 0,
                    "totalSobrando": 0,
                    "faturamento": 0,
                    "diasEsgotado": 0,
                },
            )
            acumulado["totalProduzido"] += produto["quantidade_produzida"]
            acumulado["totalVendido"] += produto["quantidade_vendida"]
            acumulado["totalSobrando"] += produto["quantidade_sobra"]
            acumulado["faturamento"] += produto["faturamento_bruto"]
            if produto["esgotado"]:
                acumulado["diasEsgotado"] += 1

    dados = {
        "periodo": _montar_periodo_estruturado(data_inicio_valor, data_fim_valor),
        "faturamentoTotal": resumo["faturamento_bruto"],
        "quantidadeTotalProduzida": resumo["total_produzido"],
        "quantidadeTotalVendida": resumo["total_vendido"],
        "quantidadeTotalSobrando": resumo["total_sobra"],
        "produtos": sorted(
            produtos_por_id.values(),
            key=lambda produto: produto["totalVendido"],
            reverse=True,
        ),
        "dias": dias,
        "correcoesRetroativas": correcoes,
    }
    return encode_value(dados)


def _montar_resumo_do_periodo_para_ia(
    data_inicio: date,
    data_fim: date,
    *,
    produto_id: UUID | None,
) -> dict:
    client = get_supabase_client()
    dias = (
        client.table("dias_de_venda")
        .select("id, data_venda, situacao, aberto_em")
        .gte("data_venda", data_inicio.isoformat())
        .lte("data_venda", data_fim.isoformat())
        .order("data_venda")
        .order("aberto_em")
        .execute()
        .data
    )
    resumos_por_abertura = _montar_resumos_de_aberturas_para_ia(
        client,
        dias,
        produto_id=produto_id,
    )
    resumos_dias = _consolidar_resumos_por_data_para_ia(resumos_por_abertura)
    totais = servico_de_relatorios._somar_dias(resumos_dias)
    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        **totais,
        "dias": resumos_dias,
    }


def _montar_resumos_de_aberturas_para_ia(
    client,
    dias: list[dict],
    *,
    produto_id: UUID | None,
) -> list[dict]:
    dia_ids = [dia["id"] for dia in dias]
    if not dia_ids:
        return []

    itens_producao = client.table("itens_producao").select("*").in_("dia_de_venda_id", dia_ids)
    decisoes_sobra = (
        client.table("decisoes_sobra").select("*").in_("dia_destino_id", dia_ids)
    )
    if produto_id:
        itens_producao = itens_producao.eq("produto_id", str(produto_id))
        decisoes_sobra = decisoes_sobra.eq("produto_id", str(produto_id))
    itens_producao = itens_producao.execute().data
    decisoes_sobra = _executar_lista_opcional_ia(decisoes_sobra)

    vendas_ativas = (
        client.table("vendas")
        .select("id, dia_de_venda_id")
        .in_("dia_de_venda_id", dia_ids)
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        consulta_itens_venda = client.table("itens_venda").select("*").in_("venda_id", venda_ids)
        if produto_id:
            consulta_itens_venda = consulta_itens_venda.eq("produto_id", str(produto_id))
        itens_venda = consulta_itens_venda.execute().data

    correcoes = _executar_lista_opcional_ia(
        client.table("correcoes_dia_fechado")
        .select("*")
        .in_("dia_de_venda_id", dia_ids)
        .order("criado_em", desc=True)
    )

    producoes_por_dia = _agrupar_linhas_por_chave(itens_producao, "dia_de_venda_id")
    vendas_por_dia = _agrupar_linhas_por_chave(itens_venda, "dia_de_venda_id")
    decisoes_por_dia = _agrupar_linhas_por_chave(decisoes_sobra, "dia_destino_id")
    correcoes_por_dia = _agrupar_linhas_por_chave(correcoes, "dia_de_venda_id")

    resumos = []
    for dia in dias:
        dia_id = dia["id"]
        produtos = servico_de_relatorios._montar_resumos_dos_produtos(
            producoes_por_dia.get(dia_id, []),
            vendas_por_dia.get(dia_id, []),
            decisoes_por_dia.get(dia_id, []),
        )
        totais = servico_de_relatorios._somar_produtos(produtos)
        produtos_esgotados = [produto for produto in produtos if produto["esgotado"]]
        resumos.append(
            {
                "dia_de_venda_id": dia_id,
                "data_venda": dia["data_venda"],
                "data": dia["data_venda"],
                "situacao": dia["situacao"],
                "status": dia["situacao"].upper(),
                **totais,
                "itens_vendidos": totais["total_vendido"],
                "faturamento_total": totais["faturamento_bruto"],
                "produtos": produtos,
                "produtos_esgotados": produtos_esgotados,
                "correcoes": correcoes_por_dia.get(dia_id, []),
            }
        )
    return resumos


def _consolidar_resumos_por_data_para_ia(resumos: list[dict]) -> list[dict]:
    resumos_por_data = _agrupar_linhas_por_chave(resumos, "data_venda")
    return [
        _consolidar_resumos_da_mesma_data_para_ia(resumos_por_data[data_venda])
        for data_venda in sorted(resumos_por_data)
    ]


def _consolidar_resumos_da_mesma_data_para_ia(resumos: list[dict]) -> dict:
    if len(resumos) == 1:
        return resumos[0]

    produtos = servico_de_relatorios._consolidar_produtos_por_data(resumos)
    totais = servico_de_relatorios._somar_produtos(produtos)
    correcoes = [
        correcao
        for resumo in resumos
        for correcao in (resumo.get("correcoes") or [])
    ]
    situacao = "aberto" if any(resumo["situacao"] == "aberto" for resumo in resumos) else "fechado"
    return {
        "dia_de_venda_id": resumos[-1]["dia_de_venda_id"],
        "data_venda": resumos[0]["data_venda"],
        "data": resumos[0]["data_venda"],
        "situacao": situacao,
        "status": situacao.upper(),
        **totais,
        "itens_vendidos": totais["total_vendido"],
        "faturamento_total": totais["faturamento_bruto"],
        "produtos": produtos,
        "produtos_esgotados": [produto for produto in produtos if produto["esgotado"]],
        "correcoes": correcoes,
    }


def _agrupar_linhas_por_chave(linhas: list[dict], chave: str) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(str(linha[chave]), []).append(linha)
    return grupos


# Helpers centralizados em infra; aliases preservam os nomes locais.
_executar_lista_opcional_ia = executar_lista_opcional
_erro_tabela_ausente_ia = tabela_ausente


def _montar_periodo_estruturado(data_inicio: date, data_fim: date) -> dict:
    inicio_formatado = data_inicio.strftime("%d/%m/%Y")
    fim_formatado = data_fim.strftime("%d/%m/%Y")
    return {
        "inicio": data_inicio.isoformat(),
        "fim": data_fim.isoformat(),
        "inicioFormatado": inicio_formatado,
        "fimFormatado": fim_formatado,
        "rotulo": f"{inicio_formatado} a {fim_formatado}",
    }


def analisar_periodo_padrao(requisicao) -> dict:
    dados = montar_dados_estruturados_periodo(
        data_inicio=requisicao.data_inicio,
        data_fim=requisicao.data_fim,
        produto_id=requisicao.produto_id,
    )
    analise_texto, modelo_usado = _gerar_analise_com_ia(
        dados=dados,
        pergunta=None,
        contexto_usuario=requisicao.contexto_usuario,
        filtros=requisicao.filtros,
    )
    analise = _normalizar_analise_estruturada(dados, analise_texto, pergunta=None)
    return {
        "periodo": dados["periodo"],
        "tipo": "padrao",
        "modelo_usado": modelo_usado,
        "dados_estruturados": dados,
        **analise,
    }


def analisar_periodo_especifico(requisicao) -> dict:
    dados = montar_dados_estruturados_periodo(
        data_inicio=requisicao.data_inicio,
        data_fim=requisicao.data_fim,
        produto_id=requisicao.produto_id,
    )
    analise_texto, modelo_usado = _gerar_analise_com_ia(
        dados=dados,
        pergunta=requisicao.pergunta,
        contexto_usuario=requisicao.contexto_usuario,
        filtros=requisicao.filtros,
    )
    analise = _normalizar_analise_estruturada(dados, analise_texto, pergunta=requisicao.pergunta)
    return {
        "periodo": dados["periodo"],
        "tipo": "especifica",
        "modelo_usado": modelo_usado,
        "dados_estruturados": dados,
        **analise,
    }


def interpretar_comando_de_venda(
    requisicao: RequisicaoInterpretarComandoDeVenda,
    *,
    tipo_entrada: str = "texto",
    url_audio: str | None = None,
) -> dict:
    return interpretar_comando(
        requisicao,
        tipo_entrada=tipo_entrada,
        url_audio=url_audio,
    )


async def transcrever_audio(
    *,
    file: UploadFile,
    dia_de_venda_id: UUID | None = None,
    interpretar: bool = True,
) -> dict:
    settings = get_settings()
    faltando = []
    if not settings.openai_api_key:
        faltando.append("OPENAI_API_KEY")
    if not settings.openai_transcription_model:
        faltando.append("OPENAI_TRANSCRIPTION_MODEL")
    if faltando:
        raise MissingConfigurationError("OpenAI Audio", faltando)

    conteudo = await file.read()
    if not conteudo:
        raise BadRequestError("Arquivo de audio vazio.")

    buffer_audio = io.BytesIO(conteudo)
    buffer_audio.name = file.filename or "audio.webm"
    resposta_transcricao = get_openai_client().audio.transcriptions.create(
        model=settings.openai_transcription_model,
        file=buffer_audio,
    )
    transcricao = getattr(resposta_transcricao, "text", None)
    if not transcricao and isinstance(resposta_transcricao, dict):
        transcricao = resposta_transcricao.get("text", "")
    transcricao = transcricao or ""
    interpretacao = None
    url_audio = None

    if interpretar:
        interpretacao = interpretar_comando(
            RequisicaoInterpretarComandoDeIA(
                texto=transcricao,
                dia_de_venda_id=dia_de_venda_id,
            ),
            tipo_entrada="audio",
        )
        midia = enviar_midia_em_bytes(
            tipo_entidade="interacao_ia",
            entidade_id=UUID(interpretacao["interacao_ia_id"]),
            conteudo=conteudo,
            nome_arquivo=file.filename,
            tipo_conteudo=file.content_type,
            descricao="Audio usado em comando de IA",
        )
        url_audio = midia.get("url_publica")
        dados_confirmacao = _anexar_url_audio_em_dados_confirmacao(
            interpretacao["dados_confirmacao"],
            url_audio,
        )
        interpretacao["dados_confirmacao"] = dados_confirmacao
        interpretacao["mensagem_confirmacao"] = dados_confirmacao.get("mensagem_confirmacao")
        get_supabase_client().table("interacoes_ia").update(
            to_db_payload({"url_audio": url_audio, "dados_confirmacao": dados_confirmacao})
        ).eq("id", interpretacao["interacao_ia_id"]).execute()

    return {
        "transcricao": transcricao,
        "url_audio": url_audio,
        "interpretacao": interpretacao,
    }


async def transcrever_audio_de_venda(
    *,
    file: UploadFile,
    dia_de_venda_id: UUID | None = None,
    interpretar: bool = True,
) -> dict:
    return await transcrever_audio(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
    )


def confirmar_comando(interacao_ia_id: UUID) -> dict:
    client = get_supabase_client()
    interacao = _buscar_interacao_ia(client, interacao_ia_id)
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    acao = dados_confirmacao.get("acao")
    if interacao["situacao"] == "confirmada":
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa confirmacao ja foi aplicada.",
        )
    if interacao["situacao"] != "interpretada":
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao de IA nao esta pronta para confirmacao.",
        )

    if not dados_confirmacao.get("precisa_confirmacao"):
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao nao tem nenhuma acao pronta para confirmar.",
        )
    operacao = dados_confirmacao.get("operacao")
    if not operacao:
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao nao tem uma operacao pronta para confirmar.",
        )

    try:
        resultado = _executar_operacao_confirmada(
            dados_confirmacao,
            operacao,
            interacao_ia_id=interacao_ia_id,
        )
    except AppError as exc:
        mensagem = _mensagem_falha_confirmacao(exc)
        client.table("interacoes_ia").update(
            {
                "situacao": "falhou",
                "mensagem_erro": mensagem,
            }
        ).eq("id", str(interacao_ia_id)).execute()
        return {
            "interacao_ia_id": interacao_ia_id,
            "acao": dados_confirmacao.get("acao", operacao.get("tipo")),
            "sucesso": False,
            "mensagem_assistente": mensagem,
            "resultado": {
                "aplicado": False,
                "mensagem": mensagem,
                "codigo": exc.code,
                "detalhes": exc.details,
            },
        }

    client.table("interacoes_ia").update({"situacao": "confirmada"}).eq(
        "id",
        str(interacao_ia_id),
    ).execute()
    mensagem = _mensagem_sucesso_confirmacao(
        dados_confirmacao.get("acao", operacao.get("tipo"))
    )
    return {
        "interacao_ia_id": interacao_ia_id,
        "acao": dados_confirmacao.get("acao", operacao.get("tipo")),
        "sucesso": True,
        "mensagem_assistente": mensagem,
        "resultado": {
            "aplicado": True,
            "mensagem": mensagem,
            **resultado,
        },
    }


def confirmar_venda(interacao_ia_id: UUID) -> dict:
    client = get_supabase_client()
    interacao = _buscar_interacao_ia(client, interacao_ia_id)
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    if not dados_confirmacao.get("venda"):
        mensagem = (
            "Essa interacao nao e uma venda pronta para confirmar. "
            "Use a confirmacao geral do comando."
        )
        return {
            "interacao_ia_id": interacao_ia_id,
            "sucesso": False,
            "mensagem_assistente": mensagem,
            "venda": None,
            "resultado": {
                "aplicado": False,
                "mensagem": mensagem,
            },
        }

    confirmacao = confirmar_comando(interacao_ia_id)
    venda = confirmacao["resultado"].get("venda")
    if not venda:
        return {
            "interacao_ia_id": interacao_ia_id,
            "sucesso": False,
            "mensagem_assistente": confirmacao.get("mensagem_assistente"),
            "venda": None,
            "resultado": confirmacao["resultado"],
        }
    return {
        "interacao_ia_id": interacao_ia_id,
        "sucesso": True,
        "mensagem_assistente": confirmacao.get("mensagem_assistente"),
        "venda": venda,
        "resultado": confirmacao["resultado"],
    }


def _interpretar_com_openai(texto: str, produtos: list[dict]) -> dict:
    settings = get_settings()
    catalogo = [
        {
            "id": produto["id"],
            "nome": produto["nome"],
            "descricao": produto.get("descricao"),
            "descricao_visual": produto.get("descricao_visual"),
        }
        for produto in produtos
    ]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "acao",
            "data_venda",
            "nome_local",
            "venda_id",
            "usar_ultima_venda",
            "motivo_cancelamento",
            "observacoes",
            "itens",
            "itens_nao_identificados",
            "mensagem_assistente",
        ],
        "properties": {
            "acao": {
                "type": "string",
                "enum": sorted(ACOES_SUPORTADAS),
            },
            "data_venda": {
                "type": ["string", "null"],
                "description": "Data no formato YYYY-MM-DD quando o comando indicar uma data.",
            },
            "nome_local": {"type": ["string", "null"]},
            "venda_id": {"type": ["string", "null"]},
            "usar_ultima_venda": {"type": "boolean"},
            "motivo_cancelamento": {"type": ["string", "null"]},
            "observacoes": {"type": ["string", "null"]},
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["produto_id", "nome_produto", "quantidade", "confianca"],
                    "properties": {
                        "produto_id": {"type": "string"},
                        "nome_produto": {"type": "string"},
                        "quantidade": {"type": "integer", "minimum": 1},
                        "confianca": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "itens_nao_identificados": {"type": "array", "items": {"type": "string"}},
            "mensagem_assistente": {"type": "string"},
        },
    }
    resposta = get_openai_client().responses.create(
        model=settings.openai_text_model_resolved,
        instructions=COMMAND_INTERPRETER_INSTRUCTIONS,
        input=(
            f"Data de hoje: {data_operacional_hoje().isoformat()}\n\n"
            "Catalogo de produtos:\n"
            f"{json.dumps(catalogo, ensure_ascii=False)}\n\n"
            f"Comando falado ou digitado: {texto}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "interpretacao_comando_padoka",
                "schema": schema,
                "strict": True,
            }
        },
    )
    return json.loads(resposta.output_text)


def _gerar_analise_com_ia(
    *,
    dados: dict,
    pergunta: str | None,
    contexto_usuario: str | None,
    filtros: dict,
) -> tuple[str, str]:
    settings = get_settings()
    if not settings.openai_text_configured:
        return _gerar_analise_local(dados, pergunta), "analise-local"

    resposta = get_openai_client().responses.create(
        model=settings.openai_text_model_resolved,
        instructions=(
            "Voce analisa dados estruturados de vendas de uma pequena padaria familiar. "
            "Use apenas os dados fornecidos. Nao invente vendas, custos, datas ou produtos. "
            "Se algo nao estiver nos dados, diga que a informacao nao esta disponivel. "
            "Considere faturamento, producao, vendas, sobras, produtos esgotados, "
            "comparacao entre dias e correcoes retroativas. "
            "Quando houver dados estimados ou incompletos, sinalize a limitacao. "
            "Ao mencionar datas para o usuario, use formato brasileiro dd/mm/aaaa; "
            "para o periodo analisado, prefira dados.periodo.rotulo. "
            "Responda em portugues brasileiro, de forma direta e acionavel. "
            "Retorne somente JSON valido, sem markdown, com estes campos: "
            "resumo (string), principais_achados (lista de strings), "
            "mais_venderam (lista de objetos), mais_sobraram (lista de objetos), "
            "sugestoes (lista de strings), pontos_atencao (lista de strings)."
        ),
        input=json.dumps(
            {
                "pergunta_especifica": pergunta,
                "contexto_usuario": contexto_usuario,
                "filtros": filtros,
                "dados": dados,
            },
            ensure_ascii=False,
        ),
    )
    return resposta.output_text, settings.openai_text_model_resolved


def _montar_dados_confirmacao(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada_venda: str,
    url_audio: str | None,
) -> dict:
    acao = interpretacao["acao"]
    if acao == ACAO_REGISTRAR_VENDA:
        return _montar_confirmacao_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
            tipo_entrada_venda=tipo_entrada_venda,
            url_audio=url_audio,
        )
    if acao == ACAO_REGISTRAR_PRODUCAO:
        return _montar_confirmacao_de_producao(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
        )
    if acao == ACAO_ABRIR_DIA_DE_VENDA:
        return _montar_confirmacao_de_abertura_de_dia(interpretacao)
    if acao == ACAO_FECHAR_DIA_DE_VENDA:
        return _montar_confirmacao_de_fechamento_de_dia(interpretacao, dia_de_venda_id)
    if acao == ACAO_CANCELAR_VENDA:
        return _montar_confirmacao_de_cancelamento_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
        )
    if acao == ACAO_CANCELAR_ITEM_VENDA:
        return _montar_confirmacao_de_cancelamento_de_item_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
            tipo_entrada_venda=tipo_entrada_venda,
            url_audio=url_audio,
        )
    return _dados_sem_confirmacao(
        acao,
        "Nao consegui transformar esse comando em uma acao segura. Tente falar de outro jeito.",
    )


def _montar_confirmacao_de_venda(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada_venda: str,
    url_audio: str | None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_VENDA,
            "Entendi que era uma venda, mas nao identifiquei nenhum produto cadastrado.",
        )

    dia_de_venda = _resolver_dia_de_venda(dia_de_venda_id, interpretacao["data_venda"])
    if not dia_de_venda:
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_VENDA,
            "Entendi a venda, mas nao encontrei um dia de venda aberto para registrar.",
        )
    if dia_de_venda["situacao"] != "aberto":
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_VENDA,
            "Entendi a venda, mas esse dia de venda ja esta fechado.",
        )

    venda = {
        "dia_de_venda_id": dia_de_venda["id"],
        "tipo_entrada": tipo_entrada_venda,
        "texto_original": texto_original,
        "url_audio": url_audio,
        "itens": [
            {"produto_id": item["produto_id"], "quantidade": item["quantidade"]}
            for item in itens
        ],
    }
    mensagem = (
        f"Entendi que voce vendeu {_formatar_itens(itens)} "
        f"no dia {_formatar_data(dia_de_venda['data_venda'])}. Confirma para registrar?"
    )
    return {
        "acao": ACAO_REGISTRAR_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "venda": venda,
        "operacao": {
            "tipo": ACAO_REGISTRAR_VENDA,
            "dia_de_venda_id": dia_de_venda["id"],
            "itens": itens,
        },
    }


def _montar_confirmacao_de_producao(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_PRODUCAO,
            "Entendi que era producao, mas nao identifiquei nenhum produto cadastrado.",
        )

    data_venda = _data_ou_hoje(interpretacao["data_venda"])
    dia_de_venda = _resolver_dia_de_venda(dia_de_venda_id, data_venda.isoformat())
    if dia_de_venda:
        if dia_de_venda["situacao"] != "aberto":
            return _dados_sem_confirmacao(
                ACAO_REGISTRAR_PRODUCAO,
                "Entendi a producao, mas esse dia de venda ja esta fechado.",
            )
        mensagem = (
            f"Entendi que a producao do dia {_formatar_data(dia_de_venda['data_venda'])} "
            f"foi {_formatar_itens(itens)}. Confirma para salvar?"
        )
        return {
            "acao": ACAO_REGISTRAR_PRODUCAO,
            "precisa_confirmacao": True,
            "mensagem_confirmacao": mensagem,
            "producao": {
                "dia_de_venda_id": dia_de_venda["id"],
                "itens": itens,
                "observacoes": interpretacao["observacoes"],
            },
            "operacao": {
                "tipo": ACAO_REGISTRAR_PRODUCAO,
                "dia_de_venda_id": dia_de_venda["id"],
                "itens": itens,
                "observacoes": interpretacao["observacoes"],
            },
        }

    mensagem = (
        f"Nao encontrei dia aberto em {_formatar_data(data_venda.isoformat())}. "
        f"Entendi que devo abrir esse dia e registrar a producao: {_formatar_itens(itens)}. "
        "Confirma?"
    )
    return {
        "acao": ACAO_ABRIR_DIA_DE_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "dia_de_venda": {
            "data_venda": data_venda.isoformat(),
            "nome_local": interpretacao["nome_local"],
            "observacoes": interpretacao["observacoes"],
            "itens_producao": itens,
        },
        "operacao": {
            "tipo": ACAO_ABRIR_DIA_DE_VENDA,
            "data_venda": data_venda.isoformat(),
            "nome_local": interpretacao["nome_local"],
            "observacoes": interpretacao["observacoes"],
            "itens": itens,
        },
    }


def _montar_confirmacao_de_abertura_de_dia(interpretacao: dict) -> dict:
    data_venda = _data_ou_hoje(interpretacao["data_venda"])
    dia_existente = _buscar_dia_aberto(data_venda)
    itens = interpretacao["itens"]
    trecho_producao = f" com producao de {_formatar_itens(itens)}" if itens else ""
    if dia_existente:
        mensagem = (
            f"Ja existe uma abertura aberta em {_formatar_data(data_venda.isoformat())}. "
            f"Vou criar uma nova abertura para o mesmo dia{trecho_producao}. Confirma?"
        )
    else:
        mensagem = (
            f"Entendi que devo abrir o dia de venda em {_formatar_data(data_venda.isoformat())}"
            f"{trecho_producao}. Confirma?"
        )
    return {
        "acao": ACAO_ABRIR_DIA_DE_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "dia_de_venda": {
            "data_venda": data_venda.isoformat(),
            "nome_local": interpretacao["nome_local"],
            "observacoes": interpretacao["observacoes"],
            "itens_producao": itens,
        },
        "operacao": {
            "tipo": ACAO_ABRIR_DIA_DE_VENDA,
            "data_venda": data_venda.isoformat(),
            "nome_local": interpretacao["nome_local"],
            "observacoes": interpretacao["observacoes"],
            "itens": itens,
        },
    }


def _montar_confirmacao_de_fechamento_de_dia(
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
) -> dict:
    dia_de_venda = _resolver_dia_de_venda(dia_de_venda_id, interpretacao["data_venda"])
    if not dia_de_venda:
        return _dados_sem_confirmacao(
            ACAO_FECHAR_DIA_DE_VENDA,
            "Entendi que devo fechar o dia, mas nao encontrei um dia aberto.",
        )
    if dia_de_venda["situacao"] == "fechado":
        return _dados_sem_confirmacao(
            ACAO_FECHAR_DIA_DE_VENDA,
            "Entendi que devo fechar o dia, mas esse dia ja esta fechado.",
        )

    mensagem = (
        f"Entendi que devo fechar o dia de venda {_formatar_data(dia_de_venda['data_venda'])}. "
        "Confirma?"
    )
    return {
        "acao": ACAO_FECHAR_DIA_DE_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "operacao": {
            "tipo": ACAO_FECHAR_DIA_DE_VENDA,
            "dia_de_venda_id": dia_de_venda["id"],
            "observacoes": interpretacao["observacoes"],
        },
    }


def _montar_confirmacao_de_cancelamento_de_venda(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
) -> dict:
    venda = None
    if interpretacao["venda_id"]:
        venda = _buscar_venda_ou_none(interpretacao["venda_id"])
    if not venda and _comando_pede_ultima_venda(texto_original, interpretacao):
        venda = _buscar_ultima_venda_ativa(
            dia_de_venda_id=dia_de_venda_id,
            data_venda=interpretacao["data_venda"],
        )
    if not venda and not interpretacao["venda_id"]:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_VENDA,
            _mensagem_cancelamento_sem_alvo_claro(texto_original),
        )
    if not venda:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_VENDA,
            "Entendi que devo cancelar uma venda, mas nao encontrei venda ativa para cancelar.",
        )
    if venda["situacao"] != "ativa":
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_VENDA,
            "Entendi que devo cancelar essa venda, mas ela ja esta cancelada.",
        )

    motivo = interpretacao["motivo_cancelamento"] or "Cancelado via IA"
    mensagem = (
        f"Entendi que devo cancelar a venda {venda['id']}: "
        f"{_formatar_resumo_da_venda(venda)}. Confirma?"
    )
    return {
        "acao": ACAO_CANCELAR_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "cancelamento": {
            "venda_id": venda["id"],
            "motivo": motivo,
        },
        "operacao": {
            "tipo": ACAO_CANCELAR_VENDA,
            "venda_id": venda["id"],
            "motivo": motivo,
        },
    }


def _montar_confirmacao_de_cancelamento_de_item_de_venda(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada_venda: str,
    url_audio: str | None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_ITEM_VENDA,
            "Entendi que devo cancelar itens de uma venda, mas nao identifiquei os itens.",
        )

    venda = None
    if interpretacao["venda_id"]:
        venda = _buscar_venda_ou_none(interpretacao["venda_id"])
    if not venda and _comando_pede_ultima_venda(texto_original, interpretacao):
        venda = _buscar_ultima_venda_ativa(
            dia_de_venda_id=dia_de_venda_id,
            data_venda=interpretacao["data_venda"],
        )
    if not venda and not interpretacao["venda_id"]:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_ITEM_VENDA,
            _mensagem_cancelamento_sem_alvo_claro(texto_original),
        )
    if not venda:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_ITEM_VENDA,
            "Entendi que devo cancelar itens, mas nao encontrei venda ativa para ajustar.",
        )
    if venda["situacao"] != "ativa":
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_ITEM_VENDA,
            "Entendi que devo ajustar essa venda, mas ela ja esta cancelada.",
        )

    ajuste = _calcular_ajuste_de_itens_da_venda(venda, itens)
    if ajuste["erro"]:
        return _dados_sem_confirmacao(ACAO_CANCELAR_ITEM_VENDA, ajuste["erro"])

    itens_restantes = ajuste["itens_restantes"]
    itens_cancelados = ajuste["itens_cancelados"]
    if itens_restantes:
        dia_de_venda = _buscar_dia_ou_none(venda["dia_de_venda_id"])
        if not dia_de_venda or dia_de_venda["situacao"] != "aberto":
            return _dados_sem_confirmacao(
                ACAO_CANCELAR_ITEM_VENDA,
                (
                    "Entendi o ajuste, mas nao consigo recriar a venda corrigida "
                    "porque o dia de venda esta fechado."
                ),
            )
    motivo = interpretacao["motivo_cancelamento"] or "Item cancelado via IA"
    if itens_restantes:
        complemento = (
            "Para preservar o historico, vou cancelar a venda original e registrar "
            f"uma venda corrigida com {_formatar_itens(itens_restantes)}."
        )
    else:
        complemento = "Isso deixa a venda sem itens, entao vou cancelar a venda inteira."

    mensagem = (
        f"Entendi que devo tirar {_formatar_itens(itens_cancelados)} da venda {venda['id']}. "
        f"{complemento} Confirma?"
    )
    return {
        "acao": ACAO_CANCELAR_ITEM_VENDA,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "ajuste_venda": {
            "venda_id": venda["id"],
            "itens_cancelados": itens_cancelados,
            "itens_restantes": itens_restantes,
            "motivo": motivo,
        },
        "operacao": {
            "tipo": ACAO_CANCELAR_ITEM_VENDA,
            "venda_id": venda["id"],
            "motivo": motivo,
            "tipo_entrada": tipo_entrada_venda,
            "texto_original": texto_original,
            "url_audio": url_audio,
            "itens_cancelados": itens_cancelados,
            "itens_restantes": itens_restantes,
        },
    }


def _calcular_ajuste_de_itens_da_venda(venda: dict, itens_cancelar: list[dict]) -> dict:
    quantidades_cancelar = {}
    nomes_cancelar = {}
    for item in itens_cancelar:
        produto_id = str(item["produto_id"])
        quantidades_cancelar[produto_id] = (
            quantidades_cancelar.get(produto_id, 0) + item["quantidade"]
        )
        nomes_cancelar[produto_id] = item["nome_produto"]

    itens_restantes = []
    itens_cancelados = []
    produtos_na_venda = {str(item["produto_id"]) for item in venda.get("itens", [])}
    produtos_fora_da_venda = set(quantidades_cancelar) - produtos_na_venda
    if produtos_fora_da_venda:
        nomes = ", ".join(nomes_cancelar[produto_id] for produto_id in produtos_fora_da_venda)
        return {
            "erro": f"Entendi o ajuste, mas a venda escolhida nao tem estes produtos: {nomes}.",
            "itens_restantes": [],
            "itens_cancelados": [],
        }

    for item_venda in venda.get("itens", []):
        produto_id = str(item_venda["produto_id"])
        quantidade_atual = int(item_venda["quantidade"])
        quantidade_cancelar = quantidades_cancelar.get(produto_id, 0)
        if quantidade_cancelar > quantidade_atual:
            return {
                "erro": (
                    f"A venda tem {quantidade_atual}x {item_venda['nome_produto_no_momento']}, "
                    f"mas o comando pediu cancelar {quantidade_cancelar}."
                ),
                "itens_restantes": [],
                "itens_cancelados": [],
            }
        if quantidade_cancelar:
            itens_cancelados.append(
                {
                    "produto_id": produto_id,
                    "nome_produto": item_venda["nome_produto_no_momento"],
                    "quantidade": quantidade_cancelar,
                    "confianca": 1,
                }
            )
        quantidade_restante = quantidade_atual - quantidade_cancelar
        if quantidade_restante:
            itens_restantes.append(
                {
                    "produto_id": produto_id,
                    "nome_produto": item_venda["nome_produto_no_momento"],
                    "quantidade": quantidade_restante,
                    "confianca": 1,
                }
            )

    if not itens_cancelados:
        return {
            "erro": "Entendi o ajuste, mas nenhum item da venda seria alterado.",
            "itens_restantes": [],
            "itens_cancelados": [],
        }
    return {
        "erro": None,
        "itens_restantes": itens_restantes,
        "itens_cancelados": itens_cancelados,
    }


def _executar_operacao_confirmada(
    dados_confirmacao: dict,
    operacao: dict,
    *,
    interacao_ia_id: UUID,
) -> dict:
    tipo = operacao.get("tipo")
    if tipo == ACAO_REGISTRAR_VENDA:
        dados_venda = dados_confirmacao.get("venda")
        if not dados_venda:
            raise BadRequestError("Essa interacao nao tem dados de venda para executar.")
        _validar_itens_com_preco_no_dia(
            UUID(str(dados_venda["dia_de_venda_id"])),
            dados_venda.get("itens") or [],
        )
        venda = servico_de_vendas.registrar_venda(RequisicaoRegistrarVenda(**dados_venda))
        return {"venda": venda}

    if tipo == ACAO_REGISTRAR_PRODUCAO:
        dia_de_venda_id = UUID(str(operacao["dia_de_venda_id"]))
        _validar_itens_com_preco_no_dia(dia_de_venda_id, operacao.get("itens") or [])
        itens_producao = []
        for item in operacao.get("itens") or []:
            itens_producao.append(
                servico_de_dias_de_venda.salvar_item_producao(
                    dia_de_venda_id,
                    RequisicaoCriarItemProducao(
                        produto_id=UUID(str(item["produto_id"])),
                        quantidade_produzida=item["quantidade"],
                        observacoes=operacao.get("observacoes"),
                    ),
                )
            )
        return {
            "dia_de_venda_id": str(dia_de_venda_id),
            "itens_producao": itens_producao,
        }

    if tipo == ACAO_ABRIR_DIA_DE_VENDA:
        data_venda = date.fromisoformat(operacao["data_venda"])
        _validar_itens_com_preco_na_data(data_venda, operacao.get("itens") or [])
        dia_de_venda = servico_de_dias_de_venda.criar_dia_de_venda(
            RequisicaoCriarDiaDeVenda(
                data_venda=data_venda,
                nome_local=operacao.get("nome_local"),
                observacoes=operacao.get("observacoes"),
                itens_producao=[
                    RequisicaoCriarItemProducao(
                        produto_id=UUID(str(item["produto_id"])),
                        quantidade_produzida=item["quantidade"],
                        observacoes=operacao.get("observacoes"),
                    )
                    for item in operacao.get("itens") or []
                ],
            )
        )
        return {"dia_de_venda": dia_de_venda}

    if tipo == ACAO_FECHAR_DIA_DE_VENDA:
        dia_de_venda = servico_de_dias_de_venda.fechar_dia_de_venda(
            UUID(str(operacao["dia_de_venda_id"])),
            RequisicaoFecharDiaDeVenda(observacoes=operacao.get("observacoes")),
        )
        return {"dia_de_venda": dia_de_venda}

    if tipo == ACAO_CANCELAR_VENDA:
        venda = servico_de_vendas.cancelar_venda(
            UUID(str(operacao["venda_id"])),
            RequisicaoCancelarVenda(motivo=operacao.get("motivo")),
        )
        return {"venda": venda}

    if tipo == ACAO_CANCELAR_ITEM_VENDA:
        venda_original = servico_de_vendas.buscar_venda(UUID(str(operacao["venda_id"])))
        if venda_original["situacao"] != "ativa":
            raise BadRequestError("Essa venda nao esta ativa para ajuste.")
        itens_restantes = operacao.get("itens_restantes") or []
        if itens_restantes:
            dia_de_venda = _buscar_dia_ou_none(venda_original["dia_de_venda_id"])
            if not dia_de_venda or dia_de_venda["situacao"] != "aberto":
                raise BadRequestError(
                    "Nao e possivel recriar a venda corrigida porque o dia esta fechado."
                )
            _validar_itens_com_preco_na_data(
                date.fromisoformat(dia_de_venda["data_venda"]),
                itens_restantes,
            )
        venda_cancelada = servico_de_vendas.cancelar_venda(
            UUID(str(operacao["venda_id"])),
            RequisicaoCancelarVenda(motivo=operacao.get("motivo")),
        )
        if not itens_restantes:
            return {"venda_cancelada": venda_cancelada, "venda_corrigida": None}

        venda_corrigida = servico_de_vendas.registrar_venda(
            RequisicaoRegistrarVenda(
                dia_de_venda_id=UUID(str(venda_cancelada["dia_de_venda_id"])),
                tipo_entrada=operacao.get("tipo_entrada") or "ia",
                interacao_ia_id=interacao_ia_id,
                texto_original=operacao.get("texto_original"),
                url_audio=operacao.get("url_audio"),
                observacoes=f"Venda corrigida a partir da venda {venda_cancelada['id']}.",
                itens=[
                    {
                        "produto_id": UUID(str(item["produto_id"])),
                        "quantidade": item["quantidade"],
                    }
                    for item in itens_restantes
                ],
            )
        )
        return {
            "venda_cancelada": venda_cancelada,
            "venda_corrigida": venda_corrigida,
        }

    raise BadRequestError("Tipo de operacao de IA nao suportado.")


def _validar_itens_com_preco_no_dia(dia_de_venda_id: UUID, itens: list[dict]) -> None:
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        get_supabase_client(),
        dia_de_venda_id,
    )
    _validar_itens_com_preco_na_data(date.fromisoformat(dia_de_venda["data_venda"]), itens)


def _validar_itens_com_preco_na_data(data_venda: date, itens: list[dict]) -> None:
    for item in itens:
        try:
            produto_id = UUID(str(item["produto_id"]))
        except (KeyError, ValueError) as exc:
            raise BadRequestError(
                "Produto invalido na confirmacao.",
                {"produto_id": item.get("produto_id")},
            ) from exc
        produtos_public.buscar_snapshot_do_produto(produto_id, data_venda)


def _criar_interacao_ia(
    *,
    dia_de_venda_id: UUID | str | None,
    tipo_entrada: str,
    texto_original: str,
    url_audio: str | None,
    acao_interpretada: dict,
    dados_confirmacao: dict,
) -> dict:
    return (
        get_supabase_client()
        .table("interacoes_ia")
        .insert(
            to_db_payload(
                {
                    "dia_de_venda_id": dia_de_venda_id,
                    "tipo_entrada": tipo_entrada,
                    "texto_original": texto_original,
                    "url_audio": url_audio,
                    "acao_interpretada": acao_interpretada,
                    "dados_confirmacao": dados_confirmacao,
                    "situacao": "interpretada",
                }
            )
        )
        .execute()
        .data[0]
    )


def _buscar_interacao_ia(client, interacao_ia_id: UUID) -> dict:
    interacao = first_or_none(
        client.table("interacoes_ia")
        .select("*")
        .eq("id", str(interacao_ia_id))
        .limit(1)
        .execute()
        .data
    )
    if not interacao:
        raise NotFoundError("Interacao de IA", str(interacao_ia_id))
    return interacao


def _resolver_dia_de_venda(dia_de_venda_id: UUID | None, data_venda: str | None) -> dict | None:
    if dia_de_venda_id:
        return _buscar_dia_ou_none(dia_de_venda_id)
    data = _data_ou_none(data_venda)
    dia = _buscar_dia_aberto(data)
    if dia:
        return dia
    if data:
        return None
    return _buscar_dia_aberto(None)


def _buscar_dia_ou_none(dia_de_venda_id: UUID | str) -> dict | None:
    try:
        return servico_de_dias_de_venda.buscar_linha_dia_de_venda(
            get_supabase_client(),
            dia_de_venda_id,
        )
    except NotFoundError:
        return None


def _buscar_dia_aberto(data_venda: date | None) -> dict | None:
    consulta = (
        get_supabase_client()
        .table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .order("aberto_em", desc=True)
    )
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    return first_or_none(consulta.limit(1).execute().data)


def _buscar_venda_ou_none(venda_id: str) -> dict | None:
    try:
        return servico_de_vendas.buscar_venda(UUID(venda_id))
    except (BadRequestError, NotFoundError, ValueError):
        return None


def _buscar_ultima_venda_ativa(
    *,
    dia_de_venda_id: UUID | None,
    data_venda: str | None,
) -> dict | None:
    client = get_supabase_client()
    consulta = client.table("vendas").select("*").eq("situacao", "ativa")
    if dia_de_venda_id:
        consulta = consulta.eq("dia_de_venda_id", str(dia_de_venda_id))
    else:
        data = _data_ou_none(data_venda)
        if data:
            dias = client.table("dias_de_venda").select("id").eq(
                "data_venda",
                data.isoformat(),
            ).execute().data
            dia_ids = [dia["id"] for dia in dias]
            if not dia_ids:
                return None
            consulta = consulta.in_("dia_de_venda_id", dia_ids)

    venda = first_or_none(consulta.order("ocorrido_em", desc=True).limit(1).execute().data)
    if not venda:
        return None
    return servico_de_vendas.buscar_venda(UUID(venda["id"]))


def _extrair_dia_de_venda_id_para_interacao(
    dados_confirmacao: dict,
    dia_de_venda_id: UUID | None,
) -> UUID | str | None:
    if dia_de_venda_id:
        return dia_de_venda_id
    operacao = dados_confirmacao.get("operacao") or {}
    return operacao.get("dia_de_venda_id")


def _anexar_url_audio_em_dados_confirmacao(dados_confirmacao: dict, url_audio: str | None) -> dict:
    if not url_audio:
        return dados_confirmacao
    if dados_confirmacao.get("venda"):
        dados_confirmacao["venda"]["url_audio"] = url_audio
    operacao = dados_confirmacao.get("operacao") or {}
    if operacao.get("tipo") == ACAO_CANCELAR_ITEM_VENDA:
        operacao["url_audio"] = url_audio
    return dados_confirmacao


def _dados_sem_confirmacao(acao: str, mensagem: str) -> dict:
    return {
        "acao": acao,
        "precisa_confirmacao": False,
        "mensagem_confirmacao": mensagem,
        "operacao": None,
    }


def _resposta_confirmacao_nao_aplicada(
    interacao_ia_id: UUID,
    acao: str | None,
    mensagem: str,
) -> dict:
    return {
        "interacao_ia_id": interacao_ia_id,
        "acao": acao or ACAO_DESCONHECIDO,
        "sucesso": False,
        "mensagem_assistente": mensagem,
        "resultado": {
            "aplicado": False,
            "mensagem": mensagem,
        },
    }


def _mensagem_falha_confirmacao(exc: AppError) -> str:
    if exc.status_code == 404:
        return (
            f"Nao consegui aplicar essa confirmacao: {exc.message} "
            "Confira os dados e envie o comando de novo."
        )
    return f"Nao consegui aplicar essa confirmacao: {exc.message}"


def _mensagem_sucesso_confirmacao(acao: str | None) -> str:
    if acao == ACAO_REGISTRAR_VENDA:
        return "Pronto, registrei a venda."
    if acao == ACAO_REGISTRAR_PRODUCAO:
        return "Pronto, salvei a producao."
    if acao == ACAO_ABRIR_DIA_DE_VENDA:
        return "Pronto, abri o dia de venda."
    if acao == ACAO_FECHAR_DIA_DE_VENDA:
        return "Pronto, fechei o dia de venda."
    if acao == ACAO_CANCELAR_VENDA:
        return "Pronto, cancelei a venda."
    if acao == ACAO_CANCELAR_ITEM_VENDA:
        return "Pronto, ajustei a venda."
    return "Pronto, apliquei a confirmacao."
