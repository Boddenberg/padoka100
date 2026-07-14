import base64
import io
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    BadRequestError,
    ExternalServiceError,
    MissingConfigurationError,
    NotFoundError,
)
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import coluna_ausente, executar_lista_opcional, tabela_ausente
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
)
from app.modules.ia import midias_recebidas, threads
from app.modules.ia.domain import acoes as _acoes
from app.modules.ia.domain import analise as _analise
from app.modules.ia.domain import fallback as _fallback
from app.modules.ia.domain import texto as _texto
from app.modules.ia.esquemas import (
    RequisicaoInterpretarComandoDeIA,
    RequisicaoInterpretarComandoDeVenda,
)
from app.modules.ia.prompts.command_interpreter import COMMAND_INTERPRETER_INSTRUCTIONS
from app.modules.ia.prompts.especialista import (
    ESPECIALISTA_INSTRUCTIONS,
    FRASES_JORNADAS,
    JORNADAS_ESPECIALISTA,
)
from app.modules.midia.servico import enviar_midia_em_bytes
from app.modules.produtos import public as produtos_public
from app.modules.produtos.esquemas import RequisicaoCriarProduto
from app.modules.relatorios.domain import agregacao
from app.modules.vendas import servico as servico_de_vendas
from app.modules.vendas.esquemas import RequisicaoCancelarVenda, RequisicaoRegistrarVenda
from app.shared.datas import data_operacional_hoje, validar_periodo
from app.shared.db import encode_value, first_or_none, to_db_payload

logger = logging.getLogger(__name__)

# Compatibilidade: a logica pura de interpretacao vive em app.modules.ia.domain.
# Mantemos aliases sob os nomes internos ja usados no restante deste servico.
ACAO_REGISTRAR_VENDA = _acoes.ACAO_REGISTRAR_VENDA
ACAO_REGISTRAR_PRODUCAO = _acoes.ACAO_REGISTRAR_PRODUCAO
ACAO_CRIAR_PRODUTO = _acoes.ACAO_CRIAR_PRODUTO
ACAO_CRIAR_PRODUTOS = _acoes.ACAO_CRIAR_PRODUTOS
ACAO_ABRIR_DIA_DE_VENDA = _acoes.ACAO_ABRIR_DIA_DE_VENDA
ACAO_FECHAR_DIA_DE_VENDA = _acoes.ACAO_FECHAR_DIA_DE_VENDA
ACAO_CANCELAR_VENDA = _acoes.ACAO_CANCELAR_VENDA
ACAO_CANCELAR_ITEM_VENDA = _acoes.ACAO_CANCELAR_ITEM_VENDA
ACAO_CONVERSAR = _acoes.ACAO_CONVERSAR
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
_normalizar_produto_interpretado = _fallback.normalizar_produto_interpretado
_normalizar_produtos_interpretados = _fallback.normalizar_produtos_interpretados
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
    usuario_id: UUID | str | None = None,
) -> dict:
    settings = get_settings()
    thread_id = requisicao.thread_id or uuid4()
    produtos = produtos_public.listar_produtos_ativos(usuario_id=usuario_id)

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
    if interpretacao["acao"] == ACAO_CONVERSAR:
        dados_confirmacao = _montar_conversa_especialista(
            interpretacao=interpretacao,
            texto=requisicao.texto,
            produtos=produtos,
            usuario_id=usuario_id,
        )
    else:
        dados_confirmacao = _montar_dados_confirmacao(
            interpretacao=interpretacao,
            dia_de_venda_id=requisicao.dia_de_venda_id,
            texto_original=requisicao.texto,
            tipo_entrada_venda="audio" if tipo_entrada == "audio" else "ia",
            url_audio=url_audio,
            usuario_id=usuario_id,
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
        usuario_id=usuario_id,
        thread_id=thread_id,
    )
    thread_id = interacao.get("thread_id") or thread_id

    dados_confirmacao["interacao_ia_id"] = interacao["id"]
    if dados_confirmacao.get("venda"):
        dados_confirmacao["venda"]["interacao_ia_id"] = interacao["id"]
    _atualizar_interacao_ia(
        get_supabase_client(),
        interacao["id"],
        {"dados_confirmacao": dados_confirmacao},
    )

    mensagem_confirmacao = dados_confirmacao.get("mensagem_confirmacao")
    return {
        "interacao_ia_id": interacao["id"],
        "thread_id": thread_id,
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
    usuario_id: UUID | str | None = None,
) -> dict:
    data_inicio_valor = date.fromisoformat(data_inicio)
    data_fim_valor = date.fromisoformat(data_fim)
    validar_periodo(data_inicio_valor, data_fim_valor)
    resumo = _montar_resumo_do_periodo_para_ia(
        data_inicio_valor,
        data_fim_valor,
        produto_id=produto_id,
        usuario_id=usuario_id,
    )
    produtos_por_id: dict[str, dict] = {}
    correcoes = []
    dias = []
    for dia in resumo["dias"]:
        dias.append(
            {
                "data": dia["data"],
                "status": dia["status"],
                "nomeLocal": dia.get("nome_local"),
                "faturamentoTotal": dia["faturamento_total"],
                "custoEstimado": dia["custo_estimado"],
                "lucroEstimado": dia["lucro_estimado"],
                "quantidadeTotalProduzida": dia["total_produzido"],
                "quantidadeTotalVendida": dia["total_vendido"],
                "quantidadeTotalSobrando": dia["total_sobra"],
                "quantidadeSobraAproveitada": dia["total_sobra_aproveitada"],
                "quantidadeSobraDescartada": dia["total_sobra_descartada"],
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
                    "totalSobraAproveitada": 0,
                    "totalSobraDescartada": 0,
                    "faturamento": 0,
                    "custoEstimado": 0,
                    "lucroEstimado": 0,
                    "diasEsgotado": 0,
                },
            )
            acumulado["totalProduzido"] += produto["quantidade_produzida"]
            acumulado["totalVendido"] += produto["quantidade_vendida"]
            acumulado["totalSobrando"] += produto["quantidade_sobra"]
            acumulado["totalSobraAproveitada"] += produto[
                "quantidade_sobra_aproveitada"
            ]
            acumulado["totalSobraDescartada"] += produto[
                "quantidade_sobra_descartada"
            ]
            acumulado["faturamento"] += produto["faturamento_bruto"]
            acumulado["custoEstimado"] += produto["custo_estimado"]
            acumulado["lucroEstimado"] += produto["lucro_estimado"]
            if produto["esgotado"]:
                acumulado["diasEsgotado"] += 1

    dados = {
        "periodo": _montar_periodo_estruturado(data_inicio_valor, data_fim_valor),
        "faturamentoTotal": resumo["faturamento_bruto"],
        "custoEstimado": resumo["custo_estimado"],
        "lucroEstimado": resumo["lucro_estimado"],
        "quantidadeTotalProduzida": resumo["total_produzido"],
        "quantidadeTotalVendida": resumo["total_vendido"],
        "quantidadeTotalSobrando": resumo["total_sobra"],
        "quantidadeSobraAproveitada": resumo["total_sobra_aproveitada"],
        "quantidadeSobraDescartada": resumo["total_sobra_descartada"],
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
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("id, data_venda, nome_local_no_momento, situacao, aberto_em")
        .gte("data_venda", data_inicio.isoformat())
        .lte("data_venda", data_fim.isoformat())
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    dias = consulta.order("data_venda").order("aberto_em").execute().data
    resumos_por_abertura = _montar_resumos_de_aberturas_para_ia(
        client,
        dias,
        produto_id=produto_id,
    )
    resumos_dias = _consolidar_resumos_por_data_para_ia(resumos_por_abertura)
    totais = agregacao.somar_dias(resumos_dias)
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
        produtos = agregacao.montar_resumos_dos_produtos(
            producoes_por_dia.get(dia_id, []),
            vendas_por_dia.get(dia_id, []),
            decisoes_por_dia.get(dia_id, []),
        )
        totais = agregacao.somar_produtos(produtos)
        produtos_esgotados = [produto for produto in produtos if produto["esgotado"]]
        resumos.append(
            {
                "dia_de_venda_id": dia_id,
                "data_venda": dia["data_venda"],
                "data": dia["data_venda"],
                "nome_local": dia.get("nome_local_no_momento"),
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

    produtos = agregacao.consolidar_produtos_por_data(resumos)
    totais = agregacao.somar_produtos(produtos)
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
        "nome_local": ", ".join(
            dict.fromkeys(
                resumo["nome_local"] for resumo in resumos if resumo.get("nome_local")
            )
        )
        or None,
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


def analisar_periodo_padrao(requisicao, *, usuario_id: UUID | str | None = None) -> dict:
    dados = montar_dados_estruturados_periodo(
        data_inicio=requisicao.data_inicio,
        data_fim=requisicao.data_fim,
        produto_id=requisicao.produto_id,
        usuario_id=usuario_id,
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


def analisar_periodo_especifico(requisicao, *, usuario_id: UUID | str | None = None) -> dict:
    dados = montar_dados_estruturados_periodo(
        data_inicio=requisicao.data_inicio,
        data_fim=requisicao.data_fim,
        produto_id=requisicao.produto_id,
        usuario_id=usuario_id,
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
    usuario_id: UUID | str | None = None,
) -> dict:
    return interpretar_comando(
        requisicao,
        tipo_entrada=tipo_entrada,
        url_audio=url_audio,
        usuario_id=usuario_id,
    )


def listar_midias_recebidas_por_ia(
    *,
    item: str | None = None,
    thread_id: UUID | str | None = None,
    usuario_id: UUID | str | None = None,
    limite: int = 100,
) -> list[dict]:
    return midias_recebidas.listar(
        item=item,
        thread_id=thread_id,
        usuario_id=usuario_id,
        limite=limite,
    )


def listar_threads_de_ia(
    *,
    thread_id: UUID | str | None = None,
    usuario_id: UUID | str | None = None,
    situacao: str | None = None,
    limite_threads: int = 50,
    limite_interacoes: int = 200,
) -> list[dict]:
    return threads.listar(
        thread_id=thread_id,
        usuario_id=usuario_id,
        situacao=situacao,
        limite_threads=limite_threads,
        limite_interacoes=limite_interacoes,
    )


async def transcrever_audio(
    *,
    file: UploadFile,
    dia_de_venda_id: UUID | None = None,
    interpretar: bool = True,
    thread_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
    usuario_nome: str | None = None,
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
    interacao_ia_id = None
    midia_audio = None
    thread_id_resposta = thread_id or uuid4()

    if interpretar:
        interpretacao = interpretar_comando(
            RequisicaoInterpretarComandoDeIA(
                texto=transcricao,
                dia_de_venda_id=dia_de_venda_id,
                thread_id=thread_id_resposta,
            ),
            tipo_entrada="audio",
            usuario_id=usuario_id,
        )
        interacao_ia_id = interpretacao["interacao_ia_id"]
        thread_id_resposta = interpretacao["thread_id"]
        midia_audio = enviar_midia_em_bytes(
            tipo_entidade="interacao_ia",
            entidade_id=UUID(str(interacao_ia_id)),
            conteudo=conteudo,
            nome_arquivo=file.filename,
            tipo_conteudo=file.content_type,
            descricao="Audio usado em comando de IA",
            usuario_id=usuario_id,
        )
        url_audio = midia_audio.get("url_publica")
        dados_confirmacao = _anexar_url_audio_em_dados_confirmacao(
            interpretacao["dados_confirmacao"],
            url_audio,
        )
        interpretacao["dados_confirmacao"] = dados_confirmacao
        interpretacao["mensagem_confirmacao"] = dados_confirmacao.get("mensagem_confirmacao")
        _atualizar_interacao_ia(
            get_supabase_client(),
            interpretacao["interacao_ia_id"],
            {"url_audio": url_audio, "dados_confirmacao": dados_confirmacao},
        )

    midias_recebidas.registrar(
        item="audio",
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        thread_id=thread_id_resposta,
        interacao_ia_id=interacao_ia_id,
        midia_id=(midia_audio or {}).get("id"),
        nome_arquivo=file.filename,
        url_publica=url_audio,
        tipo_conteudo=file.content_type,
        resposta_ia=_resposta_ia_do_payload(interpretacao),
    )

    return {
        "transcricao": transcricao,
        "thread_id": thread_id_resposta,
        "url_audio": url_audio,
        "interpretacao": interpretacao,
    }


async def transcrever_audio_de_venda(
    *,
    file: UploadFile,
    dia_de_venda_id: UUID | None = None,
    interpretar: bool = True,
    thread_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
    usuario_nome: str | None = None,
) -> dict:
    return await transcrever_audio(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
        thread_id=thread_id,
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
    )


async def importar_cardapio_por_imagem(
    *,
    file: UploadFile,
    contexto: str | None = None,
    thread_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
    usuario_nome: str | None = None,
) -> dict:
    conteudo = await file.read()
    if not conteudo:
        raise BadRequestError("Arquivo de imagem vazio.")
    tipo_conteudo = _validar_tipo_imagem(file.content_type)

    extraidos = _extrair_produtos_de_cardapio(
        conteudo=conteudo,
        tipo_conteudo=tipo_conteudo,
        contexto=contexto,
    )
    interpretacao = _montar_interpretacao_de_cardapio(extraidos, contexto=contexto)
    dados_confirmacao = _montar_confirmacao_de_produtos(interpretacao)
    thread_id = thread_id or uuid4()
    interacao = _criar_interacao_ia(
        dia_de_venda_id=None,
        tipo_entrada="imagem",
        texto_original=contexto or file.filename or "Cardapio importado por imagem",
        url_audio=None,
        acao_interpretada=interpretacao,
        dados_confirmacao=dados_confirmacao,
        usuario_id=usuario_id,
        thread_id=thread_id,
    )
    thread_id = interacao.get("thread_id") or thread_id
    interacao["thread_id"] = thread_id
    dados_confirmacao = _salvar_imagem_na_interacao(
        interacao_id=interacao["id"],
        thread_id=thread_id,
        dados_confirmacao=dados_confirmacao,
        conteudo=conteudo,
        nome_arquivo=file.filename,
        tipo_conteudo=tipo_conteudo,
        descricao="Foto de cardapio usada para cadastro de produtos por IA",
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
    )
    return _resposta_importacao_cardapio(interacao, interpretacao, dados_confirmacao, extraidos)


async def importar_producao_por_imagem(
    *,
    file: UploadFile,
    dia_de_venda_id: UUID | None = None,
    contexto: str | None = None,
    thread_id: UUID | None = None,
    usuario_id: UUID | str | None = None,
    usuario_nome: str | None = None,
) -> dict:
    conteudo = await file.read()
    if not conteudo:
        raise BadRequestError("Arquivo de imagem vazio.")
    tipo_conteudo = _validar_tipo_imagem(file.content_type)

    produtos = produtos_public.listar_produtos_ativos(usuario_id=usuario_id)
    interpretacao = _extrair_producao_de_imagem(
        conteudo=conteudo,
        tipo_conteudo=tipo_conteudo,
        contexto=contexto,
        produtos=produtos,
    )
    texto_original = contexto or file.filename or "Producao importada por imagem"
    dados_confirmacao = _montar_dados_confirmacao(
        interpretacao=interpretacao,
        dia_de_venda_id=dia_de_venda_id,
        texto_original=texto_original,
        tipo_entrada_venda="ia",
        url_audio=None,
        usuario_id=usuario_id,
    )
    thread_id = thread_id or uuid4()
    interacao = _criar_interacao_ia(
        dia_de_venda_id=_extrair_dia_de_venda_id_para_interacao(
            dados_confirmacao,
            dia_de_venda_id,
        ),
        tipo_entrada="imagem",
        texto_original=texto_original,
        url_audio=None,
        acao_interpretada=interpretacao,
        dados_confirmacao=dados_confirmacao,
        usuario_id=usuario_id,
        thread_id=thread_id,
    )
    thread_id = interacao.get("thread_id") or thread_id
    interacao["thread_id"] = thread_id
    dados_confirmacao = _salvar_imagem_na_interacao(
        interacao_id=interacao["id"],
        thread_id=thread_id,
        dados_confirmacao=dados_confirmacao,
        conteudo=conteudo,
        nome_arquivo=file.filename,
        tipo_conteudo=tipo_conteudo,
        descricao="Foto usada em comando de producao por IA",
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
    )
    return _resposta_interpretacao_por_imagem(
        interacao=interacao,
        interpretacao=interpretacao,
        dados_confirmacao=dados_confirmacao,
        modelo_usado=interpretacao["modelo_usado"],
    )


def _montar_interpretacao_de_cardapio(extraidos: dict, *, contexto: str | None) -> dict:
    return {
        "acao": ACAO_CRIAR_PRODUTOS,
        "data_venda": None,
        "nome_local": None,
        "venda_id": None,
        "usar_ultima_venda": False,
        "motivo_cancelamento": None,
        "observacoes": contexto,
        "itens": [],
        "produto": None,
        "produtos": extraidos["produtos"],
        "itens_nao_identificados": extraidos["itens_nao_identificados"],
        "avisos": extraidos["avisos"],
        "mensagem_assistente": "Li a foto do cardapio e montei uma lista para conferir.",
    }


def _salvar_imagem_na_interacao(
    *,
    interacao_id: UUID | str,
    thread_id: UUID | str | None,
    dados_confirmacao: dict,
    conteudo: bytes,
    nome_arquivo: str | None,
    tipo_conteudo: str,
    descricao: str,
    usuario_id: UUID | str | None,
    usuario_nome: str | None,
) -> dict:
    try:
        midia = enviar_midia_em_bytes(
            tipo_entidade="interacao_ia",
            entidade_id=UUID(str(interacao_id)),
            conteudo=conteudo,
            nome_arquivo=nome_arquivo,
            tipo_conteudo=tipo_conteudo,
            descricao=descricao,
            usuario_id=usuario_id,
        )
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - queremos a causa real no erro
        logger.exception("Falha ao salvar a imagem no storage")
        raise ExternalServiceError(
            "Storage",
            "Nao consegui guardar a foto agora. Tente novamente em instantes.",
            exc,
        ) from exc
    midias_recebidas.registrar(
        item="foto",
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        thread_id=thread_id,
        interacao_ia_id=interacao_id,
        midia_id=midia.get("id"),
        nome_arquivo=nome_arquivo,
        url_publica=midia.get("url_publica"),
        tipo_conteudo=tipo_conteudo,
        resposta_ia=_resposta_ia_do_payload(dados_confirmacao),
    )
    dados_confirmacao["interacao_ia_id"] = interacao_id
    dados_confirmacao["url_imagem"] = midia.get("url_publica")
    dados_confirmacao["midia_id"] = midia.get("id")
    _atualizar_interacao_ia(
        get_supabase_client(),
        interacao_id,
        {"dados_confirmacao": dados_confirmacao},
    )
    return dados_confirmacao


def _resposta_importacao_cardapio(
    interacao: dict,
    interpretacao: dict,
    dados_confirmacao: dict,
    extraidos: dict,
) -> dict:
    return _resposta_interpretacao_por_imagem(
        interacao=interacao,
        interpretacao=interpretacao,
        dados_confirmacao=dados_confirmacao,
        modelo_usado=extraidos["modelo_usado"],
    )


def _resposta_interpretacao_por_imagem(
    *,
    interacao: dict,
    interpretacao: dict,
    dados_confirmacao: dict,
    modelo_usado: str,
) -> dict:
    mensagem_confirmacao = dados_confirmacao.get("mensagem_confirmacao")
    return {
        "interacao_ia_id": interacao["id"],
        "thread_id": interacao.get("thread_id"),
        "acao": dados_confirmacao["acao"],
        "precisa_confirmacao": dados_confirmacao["precisa_confirmacao"],
        "mensagem_assistente": mensagem_confirmacao or dados_confirmacao["mensagem_confirmacao"],
        "mensagem_confirmacao": mensagem_confirmacao,
        "itens": interpretacao["itens"],
        "itens_nao_identificados": interpretacao["itens_nao_identificados"],
        "dados_confirmacao": dados_confirmacao,
        "modelo_usado": modelo_usado,
    }


def _validar_tipo_imagem(tipo_conteudo: str | None) -> str:
    tipo = (tipo_conteudo or "image/jpeg").split(";", 1)[0].strip().lower()
    if not tipo.startswith("image/"):
        raise BadRequestError(
            "Envie uma imagem do cardapio.",
            {"tipo_conteudo": tipo_conteudo},
        )
    return tipo


def _responder_visao(**kwargs) -> dict:
    """Chama a visão da OpenAI e devolve o JSON já parseado.

    Qualquer falha (modelo sem visão, schema recusado, resposta inválida,
    rede) vira ExternalServiceError com a causa real — nunca um 500 seco.
    """
    try:
        resposta = get_openai_client().responses.create(**kwargs)
        return json.loads(resposta.output_text)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - queremos a causa real no erro
        logger.exception("Falha ao ler imagem com OpenAI Vision")
        raise ExternalServiceError(
            "OpenAI Vision",
            "Nao consegui ler a imagem agora. Confira a foto e tente de novo.",
            exc,
        ) from exc


def _extrair_produtos_de_cardapio(
    *,
    conteudo: bytes,
    tipo_conteudo: str,
    contexto: str | None,
) -> dict:
    settings = get_settings()
    if not settings.openai_text_configured:
        faltando = []
        if not settings.openai_api_key:
            faltando.append("OPENAI_API_KEY")
        if not settings.openai_text_model_resolved:
            faltando.append("OPENAI_TEXT_MODEL")
        raise MissingConfigurationError("OpenAI Vision", faltando)

    imagem_base64 = base64.b64encode(conteudo).decode("ascii")
    dados = _responder_visao(
        model=settings.openai_text_model_resolved,
        instructions=_instrucoes_importacao_cardapio(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "contexto": contexto,
                                "orientacao": (
                                    "Extraia todos os produtos vendaveis e seus precos. "
                                    "Ignore titulos, categorias, observacoes, telefones, "
                                    "horarios e texto decorativo."
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{tipo_conteudo};base64,{imagem_base64}",
                    },
                ],
            }
        ],
        text={"format": _formato_json_importacao_cardapio()},
    )
    produtos = _normalizar_produtos_da_imagem(dados.get("produtos") or [])
    return {
        "produtos": produtos,
        "itens_nao_identificados": _lista_textos(dados.get("itens_sem_preco")),
        "avisos": _lista_textos(dados.get("avisos")),
        "modelo_usado": settings.openai_text_model_resolved,
    }


def _extrair_producao_de_imagem(
    *,
    conteudo: bytes,
    tipo_conteudo: str,
    contexto: str | None,
    produtos: list[dict],
) -> dict:
    settings = get_settings()
    if not settings.openai_text_configured:
        faltando = []
        if not settings.openai_api_key:
            faltando.append("OPENAI_API_KEY")
        if not settings.openai_text_model_resolved:
            faltando.append("OPENAI_TEXT_MODEL")
        raise MissingConfigurationError("OpenAI Vision", faltando)

    catalogo = [
        {
            "id": produto["id"],
            "nome": produto["nome"],
            "descricao": produto.get("descricao"),
        }
        for produto in produtos
    ]
    imagem_base64 = base64.b64encode(conteudo).decode("ascii")
    dados = _responder_visao(
        model=settings.openai_text_model_resolved,
        instructions=_instrucoes_importacao_producao(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "contexto": contexto,
                                "catalogo_produtos": catalogo,
                                "orientacao": (
                                    "Extraia quantidades produzidas/feitas/assadas. "
                                    "Use somente IDs presentes no catalogo."
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{tipo_conteudo};base64,{imagem_base64}",
                    },
                ],
            }
        ],
        text={"format": _formato_json_importacao_producao()},
    )
    interpretacao = {
        "acao": ACAO_REGISTRAR_PRODUCAO,
        "data_venda": dados.get("data_venda"),
        "nome_local": dados.get("nome_local"),
        "venda_id": None,
        "usar_ultima_venda": False,
        "motivo_cancelamento": None,
        "observacoes": contexto,
        "itens": dados.get("itens") or [],
        "produto": None,
        "produtos": [],
        "itens_nao_identificados": _lista_textos(dados.get("itens_nao_identificados")),
        "mensagem_assistente": "Li a foto e montei a producao para conferir.",
    }
    interpretacao = _normalizar_interpretacao(
        interpretacao,
        produtos,
        texto_original=contexto or "producao por imagem",
    )
    interpretacao["avisos"] = _lista_textos(dados.get("avisos"))
    interpretacao["modelo_usado"] = settings.openai_text_model_resolved
    return interpretacao


def _instrucoes_importacao_producao() -> str:
    return (
        "Voce le fotos de lista/quadro/anotacao de producao de uma padaria. "
        "Extraia somente itens produzidos, feitos, assados ou de fornada, com quantidade. "
        "Use apenas produtos do catalogo informado e devolva produto_id exatamente como recebido. "
        "Nao invente produtos nem quantidades. Se o item nao estiver no catalogo ou a "
        "quantidade estiver ilegivel, coloque em itens_nao_identificados. "
        "Nao trate preco de cardapio como quantidade de producao. "
        "Retorne apenas JSON valido no schema solicitado."
    )


def _formato_json_importacao_producao() -> dict:
    return {
        "type": "json_schema",
        "name": "importacao_producao_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "data_venda",
                "nome_local",
                "itens",
                "itens_nao_identificados",
                "avisos",
            ],
            "properties": {
                "data_venda": {"type": ["string", "null"]},
                "nome_local": {"type": ["string", "null"]},
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
                "avisos": {"type": "array", "items": {"type": "string"}},
            },
        },
        "strict": True,
    }


def _instrucoes_importacao_cardapio() -> str:
    return (
        "Voce le fotos de cardapio/menu de uma pequena padaria. "
        "Extraia somente produtos vendaveis e preco de venda. "
        "Nao invente nomes nem precos. Se o preco nao estiver legivel, coloque o nome "
        "em itens_sem_preco e nao inclua como produto pronto. "
        "Use valores numericos em reais no campo preco_venda, sem simbolo de moeda. "
        "Se houver tamanho/variacao com precos diferentes, crie produtos separados "
        "com o tamanho no nome. Retorne apenas JSON valido no schema solicitado."
    )


def _formato_json_importacao_cardapio() -> dict:
    produto_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "nome",
            "descricao",
            "descricao_visual",
            "url_imagem_principal",
            "cor_botao",
            "ordem_exibicao",
            "preco_venda",
            "preco_custo",
            "vigente_desde",
        ],
        "properties": {
            "nome": {"type": ["string", "null"]},
            "descricao": {"type": ["string", "null"]},
            "descricao_visual": {"type": ["string", "null"]},
            "url_imagem_principal": {"type": ["string", "null"]},
            "cor_botao": {"type": ["string", "null"]},
            "ordem_exibicao": {"type": ["integer", "null"]},
            # Sem "minimum": o structured outputs estrito da OpenAI recusa
            # restrições numéricas em campo anulável; o preço é validado no
            # código (_normalizar_produtos_da_imagem), não no schema.
            "preco_venda": {"type": ["number", "null"]},
            "preco_custo": {"type": ["number", "null"]},
            "vigente_desde": {"type": ["string", "null"]},
        },
    }
    return {
        "type": "json_schema",
        "name": "importacao_cardapio_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["produtos", "itens_sem_preco", "avisos"],
            "properties": {
                "produtos": {"type": "array", "items": produto_schema},
                "itens_sem_preco": {"type": "array", "items": {"type": "string"}},
                "avisos": {"type": "array", "items": {"type": "string"}},
            },
        },
        "strict": True,
    }


def _normalizar_produtos_da_imagem(produtos: list[dict]) -> list[dict]:
    normalizados = _normalizar_produtos_interpretados(produtos)
    vistos = set()
    unicos = []
    for indice, produto in enumerate(normalizados):
        nome = produto.get("nome")
        if not nome:
            continue
        chave = _normalizar(nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        produto["ordem_exibicao"] = produto.get("ordem_exibicao")
        if produto["ordem_exibicao"] is None:
            produto["ordem_exibicao"] = indice
        unicos.append(produto)
    return unicos


def _lista_textos(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [str(item).strip() for item in valor if str(item).strip()]


def confirmar_comando(interacao_ia_id: UUID, *, usuario_id: UUID | str | None = None) -> dict:
    client = get_supabase_client()
    interacao = _buscar_interacao_ia(client, interacao_ia_id, usuario_id=usuario_id)
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    acao = dados_confirmacao.get("acao")
    if interacao["situacao"] == "confirmada":
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa confirmacao ja foi aplicada.",
            thread_id=interacao.get("thread_id"),
        )
    if interacao["situacao"] != "interpretada":
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao de IA nao esta pronta para confirmacao.",
            thread_id=interacao.get("thread_id"),
        )

    if not dados_confirmacao.get("precisa_confirmacao"):
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao nao tem nenhuma acao pronta para confirmar.",
            thread_id=interacao.get("thread_id"),
        )
    operacao = dados_confirmacao.get("operacao")
    if not operacao:
        return _resposta_confirmacao_nao_aplicada(
            interacao_ia_id,
            acao,
            "Essa interacao nao tem uma operacao pronta para confirmar.",
            thread_id=interacao.get("thread_id"),
        )

    try:
        resultado = _executar_operacao_confirmada(
            dados_confirmacao,
            operacao,
            interacao_ia_id=interacao_ia_id,
            usuario_id=usuario_id,
        )
    except AppError as exc:
        mensagem = _mensagem_falha_confirmacao(exc)
        _atualizar_interacao_ia(
            client,
            interacao_ia_id,
            {
                "situacao": "falhou",
                "mensagem_erro": mensagem,
                "resolvido_em": datetime.now(UTC),
            },
        )
        return {
            "interacao_ia_id": interacao_ia_id,
            "thread_id": interacao.get("thread_id"),
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

    _atualizar_interacao_ia(
        client,
        interacao_ia_id,
        {"situacao": "confirmada", "resolvido_em": datetime.now(UTC)},
    )
    mensagem = _mensagem_sucesso_confirmacao(
        dados_confirmacao.get("acao", operacao.get("tipo"))
    )
    return {
        "interacao_ia_id": interacao_ia_id,
        "thread_id": interacao.get("thread_id"),
        "acao": dados_confirmacao.get("acao", operacao.get("tipo")),
        "sucesso": True,
        "mensagem_assistente": mensagem,
        "resultado": {
            "aplicado": True,
            "mensagem": mensagem,
            **resultado,
        },
    }


def confirmar_venda(interacao_ia_id: UUID, *, usuario_id: UUID | str | None = None) -> dict:
    client = get_supabase_client()
    interacao = _buscar_interacao_ia(client, interacao_ia_id, usuario_id=usuario_id)
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    if not dados_confirmacao.get("venda"):
        mensagem = (
            "Essa interacao nao e uma venda pronta para confirmar. "
            "Use a confirmacao geral do comando."
        )
        return {
            "interacao_ia_id": interacao_ia_id,
            "thread_id": interacao.get("thread_id"),
            "sucesso": False,
            "mensagem_assistente": mensagem,
            "venda": None,
            "resultado": {
                "aplicado": False,
                "mensagem": mensagem,
            },
        }

    confirmacao = confirmar_comando(interacao_ia_id, usuario_id=usuario_id)
    venda = confirmacao["resultado"].get("venda")
    if not venda:
        return {
            "interacao_ia_id": interacao_ia_id,
            "thread_id": confirmacao.get("thread_id") or interacao.get("thread_id"),
            "sucesso": False,
            "mensagem_assistente": confirmacao.get("mensagem_assistente"),
            "venda": None,
            "resultado": confirmacao["resultado"],
        }
    return {
        "interacao_ia_id": interacao_ia_id,
        "thread_id": confirmacao.get("thread_id") or interacao.get("thread_id"),
        "sucesso": True,
        "mensagem_assistente": confirmacao.get("mensagem_assistente"),
        "venda": venda,
        "resultado": confirmacao["resultado"],
    }


def rejeitar_comando(
    interacao_ia_id: UUID,
    *,
    motivo: str | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    interacao = _buscar_interacao_ia(client, interacao_ia_id, usuario_id=usuario_id)
    if interacao["situacao"] == "confirmada":
        mensagem = "Essa interacao ja foi confirmada e nao pode mais ser rejeitada."
        return {
            "interacao_ia_id": interacao_ia_id,
            "thread_id": interacao.get("thread_id"),
            "sucesso": False,
            "mensagem_assistente": mensagem,
            "resultado": {
                "rejeitada": False,
                "mensagem": mensagem,
                "situacao": interacao["situacao"],
            },
        }
    if interacao["situacao"] == "rejeitada":
        mensagem = "Essa interacao ja estava rejeitada."
        return {
            "interacao_ia_id": interacao_ia_id,
            "thread_id": interacao.get("thread_id"),
            "sucesso": True,
            "mensagem_assistente": mensagem,
            "resultado": {
                "rejeitada": True,
                "mensagem": mensagem,
                "situacao": "rejeitada",
            },
        }

    _atualizar_interacao_ia(
        client,
        interacao_ia_id,
        {
            "situacao": "rejeitada",
            "motivo_rejeicao": motivo,
            "resolvido_em": datetime.now(UTC),
        },
    )
    mensagem = "Tudo bem, descartei essa interpretacao."
    return {
        "interacao_ia_id": interacao_ia_id,
        "thread_id": interacao.get("thread_id"),
        "sucesso": True,
        "mensagem_assistente": mensagem,
        "resultado": {
            "rejeitada": True,
            "mensagem": mensagem,
            "situacao": "rejeitada",
            "motivo": motivo,
        },
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
            "produto",
            "produtos",
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
            "produto": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": [
                    "nome",
                    "descricao",
                    "descricao_visual",
                    "url_imagem_principal",
                    "cor_botao",
                    "ordem_exibicao",
                    "preco_venda",
                    "preco_custo",
                    "vigente_desde",
                ],
                "properties": {
                    "nome": {"type": ["string", "null"]},
                    "descricao": {"type": ["string", "null"]},
                    "descricao_visual": {"type": ["string", "null"]},
                    "url_imagem_principal": {"type": ["string", "null"]},
                    "cor_botao": {"type": ["string", "null"]},
                    "ordem_exibicao": {"type": ["integer", "null"]},
                    "preco_venda": {"type": ["number", "null"], "minimum": 0},
                    "preco_custo": {"type": ["number", "null"], "minimum": 0},
                    "vigente_desde": {
                        "type": ["string", "null"],
                        "description": "Data YYYY-MM-DD para inicio do preco, se informada.",
                    },
                },
            },
            "produtos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "nome",
                        "descricao",
                        "descricao_visual",
                        "url_imagem_principal",
                        "cor_botao",
                        "ordem_exibicao",
                        "preco_venda",
                        "preco_custo",
                        "vigente_desde",
                    ],
                    "properties": {
                        "nome": {"type": ["string", "null"]},
                        "descricao": {"type": ["string", "null"]},
                        "descricao_visual": {"type": ["string", "null"]},
                        "url_imagem_principal": {"type": ["string", "null"]},
                        "cor_botao": {"type": ["string", "null"]},
                        "ordem_exibicao": {"type": ["integer", "null"]},
                        "preco_venda": {"type": ["number", "null"], "minimum": 0},
                        "preco_custo": {"type": ["number", "null"], "minimum": 0},
                        "vigente_desde": {"type": ["string", "null"]},
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


def _montar_contexto_do_especialista(
    produtos: list[dict],
    *,
    usuario_id: UUID | str | None,
) -> dict:
    """Contexto do cliente para o especialista: produtos + resumo recente.

    O historico e melhor-esforco: se algo falhar (backend antigo, sem dados),
    seguimos so com os produtos — o agente ainda responde bem.
    """
    catalogo = []
    for produto in produtos:
        preco = produto.get("preco_atual") if isinstance(produto.get("preco_atual"), dict) else {}
        catalogo.append(
            {
                "nome": produto.get("nome"),
                "preco_venda": preco.get("preco_venda"),
                "preco_custo": preco.get("preco_custo"),
            }
        )

    resumo_recente = None
    try:
        hoje = data_operacional_hoje()
        inicio = hoje - timedelta(days=14)
        dados = montar_dados_estruturados_periodo(
            data_inicio=inicio.isoformat(),
            data_fim=hoje.isoformat(),
            usuario_id=usuario_id,
        )
        resumo_recente = {
            "periodo": dados["periodo"]["rotulo"],
            "faturamentoTotal": dados["faturamentoTotal"],
            "quantidadeTotalVendida": dados["quantidadeTotalVendida"],
            "quantidadeTotalSobrando": dados["quantidadeTotalSobrando"],
            "produtos": dados["produtos"][:8],
        }
    except Exception:  # noqa: BLE001 - contexto opcional; sem ele ainda respondemos
        logger.exception("Falha ao montar o resumo recente para o especialista")
        resumo_recente = None

    return {"produtos_cadastrados": catalogo, "resumo_recente": resumo_recente}


def _formato_json_resposta_especialista() -> dict:
    return {
        "type": "json_schema",
        "name": "resposta_especialista_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["resposta", "jornadas"],
            "properties": {
                "resposta": {"type": "string"},
                "jornadas": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(JORNADAS_ESPECIALISTA)},
                },
            },
        },
        "strict": True,
    }


def _normalizar_jornadas(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        chave = str(item).strip()
        if chave in JORNADAS_ESPECIALISTA and chave not in vistas:
            vistas.append(chave)
    return vistas[:2]


def _humanizar_jornadas_no_texto(texto: str) -> str:
    """Nunca deixa a chave interna da jornada vazar no texto do cliente.

    Se o modelo escapar e escrever "cadastrar_produtos" (com ou sem aspas), a
    gente troca pela frase amigavel antes de responder. Cinto e suspensario do
    guardrail que ja pede isso no prompt.
    """
    for chave, frase in FRASES_JORNADAS.items():
        # Casa a chave crua, com aspas opcionais em volta, sem diferenciar caixa.
        texto = re.sub(rf'["\']?\b{re.escape(chave)}\b["\']?', frase, texto, flags=re.IGNORECASE)
    return texto


def responder_como_especialista(
    texto: str,
    produtos: list[dict],
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    """Resposta do Pãozinho como especialista de padaria + guia do app.

    Faz uma chamada propria a OpenAI, com contexto do cliente e guardrails de
    escopo, e devolve {"resposta", "jornadas"}. As jornadas sao chaves que o app
    vira botao (respeitando o plano). Devolve None se a IA nao estiver
    configurada ou falhar — quem chama cai numa mensagem padrao amigavel.
    """
    settings = get_settings()
    if not settings.openai_text_configured:
        return None
    contexto = _montar_contexto_do_especialista(produtos, usuario_id=usuario_id)
    try:
        resposta = get_openai_client().responses.create(
            model=settings.openai_text_model_resolved,
            instructions=ESPECIALISTA_INSTRUCTIONS,
            input=json.dumps({"pergunta": texto, "contexto": contexto}, ensure_ascii=False),
            text={"format": _formato_json_resposta_especialista()},
        )
        dados = json.loads(getattr(resposta, "output_text", "") or "{}")
    except Exception:  # noqa: BLE001 - a conversa nunca derruba o fluxo de comando
        logger.exception("Falha ao gerar a resposta do especialista")
        return None
    texto_resposta = _humanizar_jornadas_no_texto((dados.get("resposta") or "").strip())
    if not texto_resposta:
        return None
    return {"resposta": texto_resposta, "jornadas": _normalizar_jornadas(dados.get("jornadas"))}


def _montar_conversa_especialista(
    *,
    interpretacao: dict,
    texto: str,
    produtos: list[dict],
    usuario_id: UUID | str | None = None,
) -> dict:
    resultado = responder_como_especialista(texto, produtos, usuario_id=usuario_id)
    if resultado:
        mensagem = resultado["resposta"]
        jornadas = resultado["jornadas"]
    else:
        mensagem = interpretacao.get("mensagem_assistente") or (
            "Posso ajudar com a sua padaria: receitas, custos, precos, producao e como "
            "usar o app. E so me perguntar!"
        )
        jornadas = []
    return {
        "acao": ACAO_CONVERSAR,
        "precisa_confirmacao": False,
        "mensagem_confirmacao": mensagem,
        "jornadas": jornadas,
        "operacao": None,
    }


def _montar_dados_confirmacao(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada_venda: str,
    url_audio: str | None,
    usuario_id: UUID | str | None = None,
) -> dict:
    acao = interpretacao["acao"]
    if acao == ACAO_CRIAR_PRODUTO:
        return _montar_confirmacao_de_produto(interpretacao)
    if acao == ACAO_CRIAR_PRODUTOS:
        return _montar_confirmacao_de_produtos(interpretacao)
    if acao == ACAO_REGISTRAR_VENDA:
        return _montar_confirmacao_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
            tipo_entrada_venda=tipo_entrada_venda,
            url_audio=url_audio,
            usuario_id=usuario_id,
        )
    if acao == ACAO_REGISTRAR_PRODUCAO:
        return _montar_confirmacao_de_producao(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            usuario_id=usuario_id,
        )
    if acao == ACAO_ABRIR_DIA_DE_VENDA:
        return _montar_confirmacao_de_abertura_de_dia(interpretacao, usuario_id=usuario_id)
    if acao == ACAO_FECHAR_DIA_DE_VENDA:
        return _montar_confirmacao_de_fechamento_de_dia(
            interpretacao,
            dia_de_venda_id,
            usuario_id=usuario_id,
        )
    if acao == ACAO_CANCELAR_VENDA:
        return _montar_confirmacao_de_cancelamento_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
            usuario_id=usuario_id,
        )
    if acao == ACAO_CANCELAR_ITEM_VENDA:
        return _montar_confirmacao_de_cancelamento_de_item_de_venda(
            interpretacao=interpretacao,
            dia_de_venda_id=dia_de_venda_id,
            texto_original=texto_original,
            tipo_entrada_venda=tipo_entrada_venda,
            url_audio=url_audio,
            usuario_id=usuario_id,
        )
    return _dados_sem_confirmacao(
        acao,
        "Nao consegui transformar esse comando em uma acao segura. Tente falar de outro jeito.",
    )


def _montar_confirmacao_de_produtos(interpretacao: dict) -> dict:
    produtos = interpretacao.get("produtos") or []
    produtos_prontos = []
    produtos_pendentes = []
    for produto in produtos:
        nome = produto.get("nome")
        preco_venda = produto.get("preco_venda")
        if not nome:
            produtos_pendentes.append({"motivo": "nome_nao_identificado", "produto": produto})
            continue
        if preco_venda is None:
            produtos_pendentes.append({"motivo": "preco_nao_identificado", "nome": nome})
            continue
        produtos_prontos.append(_dados_produto_para_cadastro(produto))

    for item in interpretacao.get("itens_nao_identificados") or []:
        produtos_pendentes.append({"motivo": "preco_nao_identificado", "nome": item})

    if not produtos_prontos:
        return _dados_sem_confirmacao(
            ACAO_CRIAR_PRODUTOS,
            (
                "Li a foto, mas nao encontrei produtos com nome e preco de venda "
                "legiveis para cadastrar."
            ),
        )

    quantidade = len(produtos_prontos)
    lista = _formatar_produtos_para_confirmacao(produtos_prontos)
    pendencias = ""
    if produtos_pendentes:
        pendencias = f" Deixei {len(produtos_pendentes)} item(ns) para revisao por faltar dado."
    mensagem = f"Encontrei {quantidade} produto(s) no cardapio: {lista}.{pendencias} Confirma?"
    return {
        "acao": ACAO_CRIAR_PRODUTOS,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "produtos": produtos_prontos,
        "produtos_pendentes": produtos_pendentes,
        "avisos": interpretacao.get("avisos") or [],
        "operacao": {
            "tipo": ACAO_CRIAR_PRODUTOS,
            "produtos": produtos_prontos,
        },
    }


def _montar_confirmacao_de_produto(interpretacao: dict) -> dict:
    produto = interpretacao.get("produto") or {}
    nome = produto.get("nome")
    preco_venda = produto.get("preco_venda")
    if not nome:
        return _dados_sem_confirmacao(
            ACAO_CRIAR_PRODUTO,
            "Entendi que voce quer cadastrar um produto, mas nao identifiquei o nome.",
        )
    if preco_venda is None:
        return _dados_sem_confirmacao(
            ACAO_CRIAR_PRODUTO,
            f"Entendi que voce quer cadastrar {nome}, mas preciso do preco de venda.",
        )

    dados_produto = _dados_produto_para_cadastro(produto)
    mensagem = (
        f"Entendi que devo cadastrar {nome} com preco de venda "
        f"{_formatar_moeda(preco_venda)}. Confirma?"
    )
    return {
        "acao": ACAO_CRIAR_PRODUTO,
        "precisa_confirmacao": True,
        "mensagem_confirmacao": mensagem,
        "produto": dados_produto,
        "operacao": {
            "tipo": ACAO_CRIAR_PRODUTO,
            "produto": dados_produto,
        },
    }


def _dados_produto_para_cadastro(produto: dict) -> dict:
    return {
        "nome": produto["nome"],
        "descricao": produto.get("descricao"),
        "descricao_visual": produto.get("descricao_visual"),
        "url_imagem_principal": produto.get("url_imagem_principal"),
        "cor_botao": produto.get("cor_botao"),
        "ordem_exibicao": produto.get("ordem_exibicao") or 0,
        "preco_venda": produto["preco_venda"],
        "preco_custo": produto.get("preco_custo") or 0,
        "vigente_desde": produto.get("vigente_desde") or data_operacional_hoje().isoformat(),
        "motivo_preco": "Produto cadastrado via IA",
        "origem_preco": "ia",
        "gerado_por_ia": True,
    }


def _formatar_produtos_para_confirmacao(produtos: list[dict]) -> str:
    partes = [
        f"{produto['nome']} ({_formatar_moeda(Decimal(str(produto['preco_venda'])))})"
        for produto in produtos[:5]
    ]
    if len(produtos) > 5:
        partes.append(f"mais {len(produtos) - 5}")
    return ", ".join(partes)


def _montar_confirmacao_de_venda(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada_venda: str,
    url_audio: str | None,
    usuario_id: UUID | str | None = None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_VENDA,
            "Entendi que era uma venda, mas nao identifiquei nenhum produto cadastrado.",
        )

    dia_de_venda = _resolver_dia_de_venda(
        dia_de_venda_id,
        interpretacao["data_venda"],
        usuario_id=usuario_id,
    )
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
    usuario_id: UUID | str | None = None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_REGISTRAR_PRODUCAO,
            "Entendi que era producao, mas nao identifiquei nenhum produto cadastrado.",
        )

    data_venda = _data_ou_hoje(interpretacao["data_venda"])
    dia_de_venda = _resolver_dia_de_venda(
        dia_de_venda_id,
        data_venda.isoformat(),
        usuario_id=usuario_id,
    )
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


def _montar_confirmacao_de_abertura_de_dia(
    interpretacao: dict,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    data_venda = _data_ou_hoje(interpretacao["data_venda"])
    dia_existente = _buscar_dia_aberto(data_venda, usuario_id=usuario_id)
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
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    dia_de_venda = _resolver_dia_de_venda(
        dia_de_venda_id,
        interpretacao["data_venda"],
        usuario_id=usuario_id,
    )
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
    usuario_id: UUID | str | None = None,
) -> dict:
    venda = None
    if interpretacao["venda_id"]:
        venda = _buscar_venda_ou_none(interpretacao["venda_id"], usuario_id=usuario_id)
    if not venda and _comando_pede_ultima_venda(texto_original, interpretacao):
        venda = _buscar_ultima_venda_ativa(
            dia_de_venda_id=dia_de_venda_id,
            data_venda=interpretacao["data_venda"],
            usuario_id=usuario_id,
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
    usuario_id: UUID | str | None = None,
) -> dict:
    itens = interpretacao["itens"]
    if not itens:
        return _dados_sem_confirmacao(
            ACAO_CANCELAR_ITEM_VENDA,
            "Entendi que devo cancelar itens de uma venda, mas nao identifiquei os itens.",
        )

    venda = None
    if interpretacao["venda_id"]:
        venda = _buscar_venda_ou_none(interpretacao["venda_id"], usuario_id=usuario_id)
    if not venda and _comando_pede_ultima_venda(texto_original, interpretacao):
        venda = _buscar_ultima_venda_ativa(
            dia_de_venda_id=dia_de_venda_id,
            data_venda=interpretacao["data_venda"],
            usuario_id=usuario_id,
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
    usuario_id: UUID | str | None = None,
) -> dict:
    tipo = operacao.get("tipo")
    if tipo == ACAO_CRIAR_PRODUTO:
        dados_produto = operacao.get("produto")
        if not dados_produto:
            raise BadRequestError("Essa interacao nao tem dados de produto para executar.")
        produto = produtos_public.criar_produto(
            RequisicaoCriarProduto(**dados_produto),
            usuario_id=usuario_id,
        )
        return {"produto": produto}

    if tipo == ACAO_CRIAR_PRODUTOS:
        produtos_operacao = operacao.get("produtos") or []
        if not produtos_operacao:
            raise BadRequestError("Essa interacao nao tem produtos para executar.")
        produtos_criados = [
            produtos_public.criar_produto(
                RequisicaoCriarProduto(**dados_produto),
                usuario_id=usuario_id,
            )
            for dados_produto in produtos_operacao
        ]
        return {"produtos": produtos_criados, "quantidade": len(produtos_criados)}

    if tipo == ACAO_REGISTRAR_VENDA:
        dados_venda = dados_confirmacao.get("venda")
        if not dados_venda:
            raise BadRequestError("Essa interacao nao tem dados de venda para executar.")
        _validar_itens_com_preco_no_dia(
            UUID(str(dados_venda["dia_de_venda_id"])),
            dados_venda.get("itens") or [],
            usuario_id=usuario_id,
        )
        venda = servico_de_vendas.registrar_venda(
            RequisicaoRegistrarVenda(**dados_venda),
            usuario_id=usuario_id,
        )
        return {"venda": venda}

    if tipo == ACAO_REGISTRAR_PRODUCAO:
        dia_de_venda_id = UUID(str(operacao["dia_de_venda_id"]))
        _validar_itens_com_preco_no_dia(
            dia_de_venda_id,
            operacao.get("itens") or [],
            usuario_id=usuario_id,
        )
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
                    usuario_id=usuario_id,
                )
            )
        return {
            "dia_de_venda_id": str(dia_de_venda_id),
            "itens_producao": itens_producao,
        }

    if tipo == ACAO_ABRIR_DIA_DE_VENDA:
        data_venda = date.fromisoformat(operacao["data_venda"])
        _validar_itens_com_preco_na_data(
            data_venda,
            operacao.get("itens") or [],
            usuario_id=usuario_id,
        )
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
            ),
            usuario_id=usuario_id,
        )
        return {"dia_de_venda": dia_de_venda}

    if tipo == ACAO_FECHAR_DIA_DE_VENDA:
        dia_de_venda = servico_de_dias_de_venda.fechar_dia_de_venda(
            UUID(str(operacao["dia_de_venda_id"])),
            RequisicaoFecharDiaDeVenda(observacoes=operacao.get("observacoes")),
            usuario_id=usuario_id,
        )
        return {"dia_de_venda": dia_de_venda}

    if tipo == ACAO_CANCELAR_VENDA:
        venda = servico_de_vendas.cancelar_venda(
            UUID(str(operacao["venda_id"])),
            RequisicaoCancelarVenda(motivo=operacao.get("motivo")),
            usuario_id=usuario_id,
        )
        return {"venda": venda}

    if tipo == ACAO_CANCELAR_ITEM_VENDA:
        venda_original = servico_de_vendas.buscar_venda(
            UUID(str(operacao["venda_id"])),
            usuario_id=usuario_id,
        )
        if venda_original["situacao"] != "ativa":
            raise BadRequestError("Essa venda nao esta ativa para ajuste.")
        itens_restantes = operacao.get("itens_restantes") or []
        if itens_restantes:
            dia_de_venda = _buscar_dia_ou_none(
                venda_original["dia_de_venda_id"],
                usuario_id=usuario_id,
            )
            if not dia_de_venda or dia_de_venda["situacao"] != "aberto":
                raise BadRequestError(
                    "Nao e possivel recriar a venda corrigida porque o dia esta fechado."
                )
            _validar_itens_com_preco_na_data(
                date.fromisoformat(dia_de_venda["data_venda"]),
                itens_restantes,
                usuario_id=usuario_id,
            )
        venda_cancelada = servico_de_vendas.cancelar_venda(
            UUID(str(operacao["venda_id"])),
            RequisicaoCancelarVenda(motivo=operacao.get("motivo")),
            usuario_id=usuario_id,
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
            ),
            usuario_id=usuario_id,
        )
        return {
            "venda_cancelada": venda_cancelada,
            "venda_corrigida": venda_corrigida,
        }

    raise BadRequestError("Tipo de operacao de IA nao suportado.")


def _validar_itens_com_preco_no_dia(
    dia_de_venda_id: UUID,
    itens: list[dict],
    *,
    usuario_id: UUID | str | None = None,
) -> None:
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        get_supabase_client(),
        dia_de_venda_id,
        usuario_id=usuario_id,
    )
    _validar_itens_com_preco_na_data(
        date.fromisoformat(dia_de_venda["data_venda"]),
        itens,
        usuario_id=usuario_id,
    )


def _validar_itens_com_preco_na_data(
    data_venda: date,
    itens: list[dict],
    *,
    usuario_id: UUID | str | None = None,
) -> None:
    for item in itens:
        try:
            produto_id = UUID(str(item["produto_id"]))
        except (KeyError, ValueError) as exc:
            raise BadRequestError(
                "Produto invalido na confirmacao.",
                {"produto_id": item.get("produto_id")},
            ) from exc
        produtos_public.buscar_snapshot_do_produto(produto_id, data_venda, usuario_id=usuario_id)


def _criar_interacao_ia(
    *,
    dia_de_venda_id: UUID | str | None,
    thread_id: UUID | str | None,
    tipo_entrada: str,
    texto_original: str,
    url_audio: str | None,
    acao_interpretada: dict,
    dados_confirmacao: dict,
    usuario_id: UUID | str | None = None,
) -> dict:
    thread_id = thread_id or uuid4()
    payload = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda_id,
            "thread_id": thread_id,
            "tipo_entrada": tipo_entrada,
            "texto_original": texto_original,
            "url_audio": url_audio,
            "acao_interpretada": acao_interpretada,
            "dados_confirmacao": dados_confirmacao,
            "situacao": "interpretada",
            "usuario_id": usuario_id,
        }
    )
    try:
        interacao = _inserir_interacao_ia(payload)
    except Exception as exc:
        if not coluna_ausente(exc, "thread_id"):
            raise
        payload_sem_thread = {**payload}
        payload_sem_thread.pop("thread_id", None)
        interacao = _inserir_interacao_ia(payload_sem_thread)
        interacao["thread_id"] = str(thread_id)
    return interacao


def _inserir_interacao_ia(payload: dict) -> dict:
    return get_supabase_client().table("interacoes_ia").insert(payload).execute().data[0]


def _atualizar_interacao_ia(client, interacao_ia_id: UUID | str, payload: dict) -> None:
    payload_db = to_db_payload(payload)
    try:
        client.table("interacoes_ia").update(payload_db).eq("id", str(interacao_ia_id)).execute()
    except Exception as exc:
        payload_fallback = payload_db
        while True:
            payload_ajustado = _remover_colunas_ausentes_da_interacao(payload_fallback, exc)
            if payload_ajustado == payload_fallback:
                raise
            try:
                client.table("interacoes_ia").update(payload_ajustado).eq(
                    "id",
                    str(interacao_ia_id),
                ).execute()
                return
            except Exception as exc_retry:  # noqa: BLE001
                exc = exc_retry
                payload_fallback = payload_ajustado


def _remover_colunas_ausentes_da_interacao(payload: dict, exc: Exception) -> dict:
    ajustado = {**payload}
    for coluna in ("resolvido_em", "motivo_rejeicao"):
        if coluna_ausente(exc, coluna) and coluna in ajustado:
            logger.warning("Coluna interacoes_ia.%s ainda nao esta disponivel", coluna)
            ajustado.pop(coluna, None)
    return ajustado


def _buscar_interacao_ia(
    client,
    interacao_ia_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    consulta = client.table("interacoes_ia").select("*").eq("id", str(interacao_ia_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    interacao = first_or_none(consulta.limit(1).execute().data)
    if not interacao:
        raise NotFoundError("Interacao de IA", str(interacao_ia_id))
    return interacao


def _resolver_dia_de_venda(
    dia_de_venda_id: UUID | None,
    data_venda: str | None,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    if dia_de_venda_id:
        return _buscar_dia_ou_none(dia_de_venda_id, usuario_id=usuario_id)
    data = _data_ou_none(data_venda)
    dia = _buscar_dia_aberto(data, usuario_id=usuario_id)
    if dia:
        return dia
    if data:
        return None
    return _buscar_dia_aberto(None, usuario_id=usuario_id)


def _buscar_dia_ou_none(
    dia_de_venda_id: UUID | str,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    try:
        return servico_de_dias_de_venda.buscar_linha_dia_de_venda(
            get_supabase_client(),
            dia_de_venda_id,
            usuario_id=usuario_id,
        )
    except NotFoundError:
        return None


def _buscar_dia_aberto(
    data_venda: date | None,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    consulta = (
        get_supabase_client()
        .table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .order("aberto_em", desc=True)
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    return first_or_none(consulta.limit(1).execute().data)


def _buscar_venda_ou_none(venda_id: str, *, usuario_id: UUID | str | None = None) -> dict | None:
    try:
        return servico_de_vendas.buscar_venda(UUID(venda_id), usuario_id=usuario_id)
    except (BadRequestError, NotFoundError, ValueError):
        return None


def _buscar_ultima_venda_ativa(
    *,
    dia_de_venda_id: UUID | None,
    data_venda: str | None,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    client = get_supabase_client()
    consulta = client.table("vendas").select("*").eq("situacao", "ativa")
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    if dia_de_venda_id:
        consulta = consulta.eq("dia_de_venda_id", str(dia_de_venda_id))
    else:
        data = _data_ou_none(data_venda)
        if data:
            consulta_dias = client.table("dias_de_venda").select("id").eq(
                "data_venda",
                data.isoformat(),
            )
            if usuario_id:
                consulta_dias = consulta_dias.eq("usuario_id", str(usuario_id))
            dias = consulta_dias.execute().data
            dia_ids = [dia["id"] for dia in dias]
            if not dia_ids:
                return None
            consulta = consulta.in_("dia_de_venda_id", dia_ids)

    venda = first_or_none(consulta.order("ocorrido_em", desc=True).limit(1).execute().data)
    if not venda:
        return None
    return servico_de_vendas.buscar_venda(UUID(venda["id"]), usuario_id=usuario_id)


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


def _resposta_ia_do_payload(payload: dict | None) -> str | None:
    if not payload:
        return None
    return payload.get("mensagem_assistente") or payload.get("mensagem_confirmacao")


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
    *,
    thread_id: UUID | str | None = None,
) -> dict:
    return {
        "interacao_ia_id": interacao_ia_id,
        "thread_id": thread_id,
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
    if acao == ACAO_CRIAR_PRODUTO:
        return "Pronto, cadastrei o produto."
    if acao == ACAO_CRIAR_PRODUTOS:
        return "Pronto, cadastrei os produtos."
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
