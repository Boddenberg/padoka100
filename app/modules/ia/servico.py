import io
import json
import re
import unicodedata
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.modules.ia.esquemas import RequisicaoInterpretarComandoDeVenda
from app.modules.midia.servico import enviar_midia_em_bytes
from app.modules.produtos import servico as servico_de_produtos
from app.modules.vendas import servico as servico_de_vendas
from app.modules.vendas.esquemas import RequisicaoRegistrarVenda
from app.shared.db import first_or_none, to_db_payload

NUMEROS_POR_EXTENSO = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
}
PALAVRAS_IGNORADAS_DE_PRODUTO = {"pao", "paes", "de", "do", "da", "recheado", "recheada"}


def interpretar_comando_de_venda(
    requisicao: RequisicaoInterpretarComandoDeVenda,
    *,
    tipo_entrada: str = "texto",
    url_audio: str | None = None,
) -> dict:
    settings = get_settings()
    produtos = servico_de_produtos.listar_produtos(somente_ativos=True)
    if not produtos:
        raise BadRequestError("Cadastre produtos antes de usar a interpretacao de vendas.")

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

    dados_confirmacao = _montar_dados_confirmacao(
        interpretacao=interpretacao,
        dia_de_venda_id=requisicao.dia_de_venda_id,
        texto_original=requisicao.texto,
        tipo_entrada="audio" if tipo_entrada == "audio" else "ia",
    )
    interacao = _criar_interacao_ia(
        dia_de_venda_id=requisicao.dia_de_venda_id,
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

    return {
        "interacao_ia_id": interacao["id"],
        "acao": interpretacao["acao"],
        "precisa_confirmacao": True,
        "mensagem_assistente": interpretacao["mensagem_assistente"],
        "itens": interpretacao["itens"],
        "itens_nao_identificados": interpretacao["itens_nao_identificados"],
        "dados_confirmacao": dados_confirmacao,
        "modelo_usado": modelo_usado,
    }


async def transcrever_audio_de_venda(
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
        interpretacao = interpretar_comando_de_venda(
            RequisicaoInterpretarComandoDeVenda(
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
            descricao="Audio usado para registrar venda",
        )
        url_audio = midia.get("url_publica")
        dados_confirmacao = interpretacao["dados_confirmacao"]
        if dados_confirmacao.get("venda"):
            dados_confirmacao["venda"]["url_audio"] = url_audio
        interpretacao["dados_confirmacao"] = dados_confirmacao
        get_supabase_client().table("interacoes_ia").update(
            to_db_payload({"url_audio": url_audio, "dados_confirmacao": dados_confirmacao})
        ).eq("id", interpretacao["interacao_ia_id"]).execute()

    return {
        "transcricao": transcricao,
        "url_audio": url_audio,
        "interpretacao": interpretacao,
    }


def confirmar_venda(interacao_ia_id: UUID) -> dict:
    client = get_supabase_client()
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
    if interacao["situacao"] == "confirmada":
        raise BadRequestError("Essa interacao de IA ja foi confirmada.")

    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    dados_venda = dados_confirmacao.get("venda")
    if not dados_venda:
        raise BadRequestError("Essa interacao nao tem uma venda pronta para confirmar.")

    venda = servico_de_vendas.registrar_venda(RequisicaoRegistrarVenda(**dados_venda))
    client.table("interacoes_ia").update({"situacao": "confirmada"}).eq(
        "id",
        str(interacao_ia_id),
    ).execute()
    return {"interacao_ia_id": interacao_ia_id, "venda": venda}


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
        "required": ["acao", "itens", "itens_nao_identificados", "mensagem_assistente"],
        "properties": {
            "acao": {"type": "string", "enum": ["registrar_venda", "desconhecido"]},
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
        instructions=(
            "Voce interpreta comandos curtos de venda para um padeiro. "
            "Use apenas produtos do catalogo. Nao invente produto. "
            "Se faltar certeza, coloque em itens_nao_identificados."
        ),
        input=(
            "Catalogo de produtos:\n"
            f"{json.dumps(catalogo, ensure_ascii=False)}\n\n"
            f"Comando falado ou digitado: {texto}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "interpretacao_comando_venda",
                "schema": schema,
                "strict": True,
            }
        },
    )
    return json.loads(resposta.output_text)


def _interpretar_com_fallback(texto: str, produtos: list[dict]) -> dict:
    texto_normalizado = _normalizar(texto)
    tokens = texto_normalizado.split()
    itens = []
    itens_nao_identificados = []

    for produto in produtos:
        tokens_produto = [
            token
            for token in _normalizar(produto["nome"]).split()
            if token not in PALAVRAS_IGNORADAS_DE_PRODUTO
        ]
        if not tokens_produto or not all(token in tokens for token in tokens_produto):
            continue
        primeira_posicao = min(tokens.index(token) for token in tokens_produto)
        quantidade = _buscar_quantidade_antes(tokens, primeira_posicao)
        itens.append(
            {
                "produto_id": produto["id"],
                "nome_produto": produto["nome"],
                "quantidade": quantidade,
                "confianca": 0.65,
            }
        )

    acao = "registrar_venda" if itens else "desconhecido"
    if not itens:
        itens_nao_identificados.append(texto)
    return {
        "acao": acao,
        "itens": itens,
        "itens_nao_identificados": itens_nao_identificados,
        "mensagem_assistente": (
            "Confira antes de salvar a venda."
            if itens
            else "Nao consegui identificar nenhum produto cadastrado nesse comando."
        ),
    }


def _montar_dados_confirmacao(
    *,
    interpretacao: dict,
    dia_de_venda_id: UUID | None,
    texto_original: str,
    tipo_entrada: str,
) -> dict:
    dados_venda = None
    if interpretacao["acao"] == "registrar_venda" and dia_de_venda_id and interpretacao["itens"]:
        dados_venda = {
            "dia_de_venda_id": str(dia_de_venda_id),
            "tipo_entrada": tipo_entrada,
            "texto_original": texto_original,
            "itens": [
                {"produto_id": item["produto_id"], "quantidade": item["quantidade"]}
                for item in interpretacao["itens"]
            ],
        }
    return {
        "acao": interpretacao["acao"],
        "precisa_confirmacao": True,
        "venda": dados_venda,
    }


def _criar_interacao_ia(
    *,
    dia_de_venda_id: UUID | None,
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


def _buscar_quantidade_antes(tokens: list[str], posicao: int) -> int:
    janela = tokens[max(0, posicao - 6) : posicao]
    for token in reversed(janela):
        if token.isdigit():
            return max(int(token), 1)
        if token in NUMEROS_POR_EXTENSO:
            return NUMEROS_POR_EXTENSO[token]
        resultado = re.match(r"(\d+)x?", token)
        if resultado:
            return max(int(resultado.group(1)), 1)
    return 1


def _normalizar(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor.lower())
    valor_ascii = normalizado.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", valor_ascii).strip()
