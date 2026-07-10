import base64
import json
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.modules.custos.domain.status import consolidar_status
from app.modules.custos.esquemas import (
    ItemAtualizacaoPrecoCompra,
    RequisicaoAtualizarInsumo,
    RequisicaoAtualizarPrecosPorCompra,
    RequisicaoCriarCustoAdicional,
    RequisicaoCriarInsumo,
    RequisicaoCriarReceita,
    RequisicaoGerarListaCompras,
    RequisicaoRegistrarPrecoInsumo,
)
from app.modules.produtos import servico as servico_de_produtos
from app.shared.db import first_or_none, to_db_payload

UNIDADES_BASE = {
    "kg": ("massa", Decimal("1000")),
    "quilo": ("massa", Decimal("1000")),
    "quilos": ("massa", Decimal("1000")),
    "kilograma": ("massa", Decimal("1000")),
    "kilogramas": ("massa", Decimal("1000")),
    "g": ("massa", Decimal("1")),
    "grama": ("massa", Decimal("1")),
    "gramas": ("massa", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "lt": ("volume", Decimal("1000")),
    "litro": ("volume", Decimal("1000")),
    "litros": ("volume", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "mililitro": ("volume", Decimal("1")),
    "mililitros": ("volume", Decimal("1")),
    "copo": ("volume", Decimal("200")),
    "copos": ("volume", Decimal("200")),
    "copo americano": ("volume", Decimal("200")),
    "copos americanos": ("volume", Decimal("200")),
    "xicara": ("volume", Decimal("240")),
    "xicaras": ("volume", Decimal("240")),
    "colher sopa": ("volume", Decimal("15")),
    "colheres sopa": ("volume", Decimal("15")),
    "colher de sopa": ("volume", Decimal("15")),
    "colheres de sopa": ("volume", Decimal("15")),
    "colher cha": ("volume", Decimal("5")),
    "colheres cha": ("volume", Decimal("5")),
    "colher de cha": ("volume", Decimal("5")),
    "colheres de cha": ("volume", Decimal("5")),
    "prato cheio": ("massa", Decimal("350")),
    "pratos cheios": ("massa", Decimal("350")),
    "un": ("unidade", Decimal("1")),
    "und": ("unidade", Decimal("1")),
    "unidade": ("unidade", Decimal("1")),
    "unidades": ("unidade", Decimal("1")),
    "ovo": ("unidade", Decimal("1")),
    "ovos": ("unidade", Decimal("1")),
    "barra": ("unidade", Decimal("1")),
    "barras": ("unidade", Decimal("1")),
    "bisnaga": ("unidade", Decimal("1")),
    "bisnagas": ("unidade", Decimal("1")),
    "caixa": ("unidade", Decimal("1")),
    "caixas": ("unidade", Decimal("1")),
    "caixinha": ("unidade", Decimal("1")),
    "caixinhas": ("unidade", Decimal("1")),
    "cx": ("unidade", Decimal("1")),
    "dente": ("unidade", Decimal("1")),
    "dentes": ("unidade", Decimal("1")),
    "emb": ("unidade", Decimal("1")),
    "embalagem": ("unidade", Decimal("1")),
    "embalagens": ("unidade", Decimal("1")),
    "fatia": ("unidade", Decimal("1")),
    "fatias": ("unidade", Decimal("1")),
    "folha": ("unidade", Decimal("1")),
    "folhas": ("unidade", Decimal("1")),
    "frasco": ("unidade", Decimal("1")),
    "frascos": ("unidade", Decimal("1")),
    "frasquinho": ("unidade", Decimal("1")),
    "frasquinhos": ("unidade", Decimal("1")),
    "garrafa": ("unidade", Decimal("1")),
    "garrafas": ("unidade", Decimal("1")),
    "garrafinha": ("unidade", Decimal("1")),
    "garrafinhas": ("unidade", Decimal("1")),
    "lata": ("unidade", Decimal("1")),
    "latas": ("unidade", Decimal("1")),
    "latinha": ("unidade", Decimal("1")),
    "latinhas": ("unidade", Decimal("1")),
    "maco": ("unidade", Decimal("1")),
    "macos": ("unidade", Decimal("1")),
    "pacote": ("unidade", Decimal("1")),
    "pacotes": ("unidade", Decimal("1")),
    "pacotinho": ("unidade", Decimal("1")),
    "pacotinhos": ("unidade", Decimal("1")),
    "pitada": ("unidade", Decimal("1")),
    "pitadas": ("unidade", Decimal("1")),
    "porcao": ("unidade", Decimal("1")),
    "porcoes": ("unidade", Decimal("1")),
    "pct": ("unidade", Decimal("1")),
    "pcts": ("unidade", Decimal("1")),
    "pcte": ("unidade", Decimal("1")),
    "pote": ("unidade", Decimal("1")),
    "potes": ("unidade", Decimal("1")),
    "potinho": ("unidade", Decimal("1")),
    "potinhos": ("unidade", Decimal("1")),
    "punhado": ("unidade", Decimal("1")),
    "punhados": ("unidade", Decimal("1")),
    "ramo": ("unidade", Decimal("1")),
    "ramos": ("unidade", Decimal("1")),
    "rolo": ("unidade", Decimal("1")),
    "rolos": ("unidade", Decimal("1")),
    "sache": ("unidade", Decimal("1")),
    "saches": ("unidade", Decimal("1")),
    "saco": ("unidade", Decimal("1")),
    "sacos": ("unidade", Decimal("1")),
    "saquinho": ("unidade", Decimal("1")),
    "saquinhos": ("unidade", Decimal("1")),
    "tablete": ("unidade", Decimal("1")),
    "tabletes": ("unidade", Decimal("1")),
    "vidro": ("unidade", Decimal("1")),
    "vidros": ("unidade", Decimal("1")),
    "duzia": ("unidade", Decimal("12")),
    "duzias": ("unidade", Decimal("12")),
    "cartela": ("unidade", Decimal("30")),
    "cartelas": ("unidade", Decimal("30")),
    "cartela de ovos": ("unidade", Decimal("30")),
    "cartelas de ovos": ("unidade", Decimal("30")),
    "bandeja de ovos": ("unidade", Decimal("30")),
    "bandejas de ovos": ("unidade", Decimal("30")),
}

DESCRICOES_UNIDADES_APROXIMADAS = {
    "copo": "copo = 200 ml",
    "copos": "copo = 200 ml",
    "copo americano": "copo americano = 200 ml",
    "copos americanos": "copo americano = 200 ml",
    "xicara": "xicara = 240 ml",
    "xicaras": "xicara = 240 ml",
    "colher sopa": "colher de sopa = 15 ml",
    "colheres sopa": "colher de sopa = 15 ml",
    "colher de sopa": "colher de sopa = 15 ml",
    "colheres de sopa": "colher de sopa = 15 ml",
    "colher cha": "colher de cha = 5 ml",
    "colheres cha": "colher de cha = 5 ml",
    "colher de cha": "colher de cha = 5 ml",
    "colheres de cha": "colher de cha = 5 ml",
    "prato cheio": "prato cheio = 350 g",
    "pratos cheios": "prato cheio = 350 g",
    "duzia": "duzia = 12 unidades",
    "duzias": "duzia = 12 unidades",
    "cartela": "cartela = 30 unidades",
    "cartelas": "cartela = 30 unidades",
    "cartela de ovos": "cartela de ovos = 30 unidades",
    "cartelas de ovos": "cartela de ovos = 30 unidades",
    "bandeja de ovos": "bandeja de ovos = 30 unidades",
    "bandejas de ovos": "bandeja de ovos = 30 unidades",
}
PADROES_UNIDADES_COM_RUIDO = (
    (r"\bcolher(?:es)?\s*(?:de\s*)?sopa\b", "colher sopa"),
    (r"\bcolher(?:es)?\s*(?:de\s*)?cha\b", "colher cha"),
    (r"\bxicaras?\b", "xicara"),
    (r"\bcopos?\b", "copo"),
    (r"\bpratos?\s+cheios?\b", "prato cheio"),
    (r"\bcartelas?(?:\s+de\s+ovos)?\b", "cartela"),
    (r"\bbandejas?(?:\s+de\s+ovos)?\b", "bandeja de ovos"),
    (r"\bduzias?\b", "duzia"),
    (r"\b(?:pacote|pacotes|pacotinho|pacotinhos|pct|pcts|pcte)\b", "pacote"),
    (r"\b(?:saco|sacos|saquinho|saquinhos)\b", "saco"),
    (r"\b(?:sache|saches)\b", "sache"),
    (r"\b(?:caixa|caixas|caixinha|caixinhas|cx)\b", "caixa"),
    (r"\b(?:emb|embalagem|embalagens)\b", "embalagem"),
    (r"\b(?:frasco|frascos|frasquinho|frasquinhos)\b", "frasco"),
    (r"\b(?:garrafa|garrafas|garrafinha|garrafinhas)\b", "garrafa"),
    (r"\b(?:lata|latas|latinha|latinhas)\b", "lata"),
    (r"\b(?:pote|potes|potinho|potinhos)\b", "pote"),
    (r"\b(?:barra|barras)\b", "barra"),
    (r"\b(?:tablete|tabletes)\b", "tablete"),
    (r"\b(?:bisnaga|bisnagas)\b", "bisnaga"),
    (r"\b(?:vidro|vidros)\b", "vidro"),
    (r"\b(?:rolo|rolos)\b", "rolo"),
    (r"\b(?:fatia|fatias)\b", "fatia"),
    (r"\b(?:maco|macos)\b", "maco"),
    (r"\b(?:ramo|ramos)\b", "ramo"),
    (r"\b(?:folha|folhas)\b", "folha"),
    (r"\b(?:dente|dentes)\b", "dente"),
    (r"\b(?:pitada|pitadas)\b", "pitada"),
    (r"\b(?:punhado|punhados)\b", "punhado"),
    (r"\b(?:porcao|porcoes)\b", "porcao"),
    (r"\b(?:un|und|unidades?|ovos?)\b", "unidade"),
    (r"\b(?:kg|quilo|quilos|kilograma|kilogramas)\b", "kg"),
    (r"\b(?:g|grama|gramas)\b", "g"),
    (r"\b(?:ml|mililitro|mililitros)\b", "ml"),
    (r"\b(?:l|lt|litro|litros)\b", "l"),
)

STATUS_ORDEM = {
    "CONFIRMADO": 0,
    "ESTIMADO": 1,
    "PENDENTE": 2,
    "PRECISA_REVISAR": 3,
}

DESCRITORES_INGREDIENTE = {
    "branca",
    "brancas",
    "branco",
    "brancos",
    "especial",
    "especiais",
    "extra",
    "fina",
    "fino",
    "grande",
    "grandes",
    "integral",
    "iodada",
    "iodado",
    "ralado",
    "ralada",
    "refinada",
    "refinado",
    "tradicional",
    "tradicionais",
}
STOPWORDS_INGREDIENTE = {
    "a",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "o",
    "os",
    "ou",
    "para",
    "sem",
    "tipo",
}
INGREDIENTES_GENERICOS_PARA_MATCH = {"queijo"}


def listar_insumos() -> list[dict]:
    client = get_supabase_client()
    insumos = _executar_lista_opcional(client.table("insumos").select("*").order("nome"))
    return [_anexar_preco_atual(insumo) for insumo in insumos]


def criar_insumo(requisicao: RequisicaoCriarInsumo) -> dict:
    client = get_supabase_client()
    existente = buscar_insumo_compativel_por_nome(requisicao.nome)
    if existente:
        if requisicao.categoria and requisicao.categoria != existente.get("categoria"):
            client.table("insumos").update({"categoria": requisicao.categoria}).eq(
                "id",
                existente["id"],
            ).execute()
        return registrar_preco_insumo(
            UUID(existente["id"]),
            RequisicaoRegistrarPrecoInsumo(
                quantidade_comprada=requisicao.quantidade_comprada,
                unidade_compra=requisicao.unidade_compra,
                preco_total=requisicao.preco_total,
                vigente_desde=requisicao.vigente_desde,
                origem="manual",
                fornecedor=requisicao.fornecedor,
                fonte=requisicao.fonte,
                observacoes=requisicao.observacoes,
                status=requisicao.status,
            ),
        )["insumo"]

    custo_por_unidade = _calcular_custo_por_unidade(
        requisicao.preco_total,
        requisicao.quantidade_comprada,
        requisicao.unidade_compra,
    )
    insumo = (
        client.table("insumos")
        .insert(
            to_db_payload(
                {
                    "nome": requisicao.nome,
                    "categoria": requisicao.categoria,
                    "quantidade_comprada": requisicao.quantidade_comprada,
                    "preco_total": requisicao.preco_total,
                    "status": requisicao.status,
                    "observacoes": requisicao.observacoes,
                    "nome_normalizado": normalizar_nome_insumo(requisicao.nome),
                    "unidade_compra": _normalizar_unidade(requisicao.unidade_compra),
                    "custo_por_unidade": custo_por_unidade,
                    "ultima_compra_em": requisicao.vigente_desde,
                }
            )
        )
        .execute()
        .data[0]
    )
    _registrar_preco_insumo_bruto(
        insumo_id=UUID(insumo["id"]),
        quantidade_comprada=requisicao.quantidade_comprada,
        unidade_compra=requisicao.unidade_compra,
        preco_total=requisicao.preco_total,
        custo_por_unidade=custo_por_unidade,
        vigente_desde=requisicao.vigente_desde,
        origem="manual",
        fornecedor=requisicao.fornecedor,
        fonte=requisicao.fonte,
        observacoes=requisicao.observacoes,
    )
    return buscar_insumo(UUID(insumo["id"]))


def atualizar_insumo(insumo_id: UUID, requisicao: RequisicaoAtualizarInsumo) -> dict:
    client = get_supabase_client()
    insumo = buscar_insumo(insumo_id)
    dados = requisicao.model_dump(exclude_unset=True)
    if not dados:
        return insumo

    quantidade = Decimal(str(dados.get("quantidade_comprada", insumo["quantidade_comprada"])))
    preco_total = Decimal(str(dados.get("preco_total", insumo["preco_total"])))
    unidade = dados.get("unidade_compra", insumo["unidade_compra"])
    dados["unidade_compra"] = _normalizar_unidade(unidade)
    dados["custo_por_unidade"] = _calcular_custo_por_unidade(preco_total, quantidade, unidade)
    if "nome" in dados:
        dados["nome_normalizado"] = normalizar_nome_insumo(dados["nome"])
    vigente_desde = dados.pop("vigente_desde", None) or date.today()
    fornecedor = dados.pop("fornecedor", None)
    fonte = dados.pop("fonte", None)
    dados["ultima_compra_em"] = vigente_desde

    insumo_atualizado = (
        client.table("insumos")
        .update(to_db_payload(dados))
        .eq("id", str(insumo_id))
        .execute()
        .data[0]
    )
    if _dados_de_preco_foram_informados(requisicao):
        _registrar_preco_insumo_bruto(
            insumo_id=insumo_id,
            quantidade_comprada=quantidade,
            unidade_compra=unidade,
            preco_total=preco_total,
            custo_por_unidade=dados["custo_por_unidade"],
            vigente_desde=vigente_desde,
            origem="manual",
            fornecedor=fornecedor,
            fonte=fonte,
            observacoes=dados.get("observacoes"),
        )
    return _anexar_preco_atual(insumo_atualizado)


def registrar_preco_insumo(
    insumo_id: UUID,
    requisicao: RequisicaoRegistrarPrecoInsumo,
) -> dict:
    client = get_supabase_client()
    insumo = buscar_insumo(insumo_id)
    custo_por_unidade = _calcular_custo_por_unidade(
        requisicao.preco_total,
        requisicao.quantidade_comprada,
        requisicao.unidade_compra,
    )
    preco = _registrar_preco_insumo_bruto(
        insumo_id=insumo_id,
        quantidade_comprada=requisicao.quantidade_comprada,
        unidade_compra=requisicao.unidade_compra,
        preco_total=requisicao.preco_total,
        custo_por_unidade=custo_por_unidade,
        vigente_desde=requisicao.vigente_desde,
        origem=requisicao.origem,
        fornecedor=requisicao.fornecedor,
        fonte=requisicao.fonte,
        observacoes=requisicao.observacoes,
    )
    insumo_atualizado = (
        client.table("insumos")
        .update(
            to_db_payload(
                {
                    "quantidade_comprada": requisicao.quantidade_comprada,
                    "unidade_compra": _normalizar_unidade(requisicao.unidade_compra),
                    "preco_total": requisicao.preco_total,
                    "custo_por_unidade": custo_por_unidade,
                    "status": requisicao.status,
                    "observacoes": requisicao.observacoes or insumo.get("observacoes"),
                    "ultima_compra_em": requisicao.vigente_desde,
                }
            )
        )
        .eq("id", str(insumo_id))
        .execute()
        .data[0]
    )
    return {"insumo": _anexar_preco_atual(insumo_atualizado), "preco": preco}


def listar_precos_insumo(insumo_id: UUID) -> list[dict]:
    buscar_insumo(insumo_id)
    client = get_supabase_client()
    return _executar_lista_opcional(
        client.table("insumos_precos")
        .select("*")
        .eq("insumo_id", str(insumo_id))
        .order("vigente_desde", desc=True)
        .order("criado_em", desc=True)
    )


def buscar_insumo(insumo_id: UUID | str) -> dict:
    client = get_supabase_client()
    insumo = first_or_none(
        _executar_lista_opcional(
            client.table("insumos").select("*").eq("id", str(insumo_id)).limit(1)
        )
    )
    if not insumo:
        raise NotFoundError("Insumo", str(insumo_id))
    return _anexar_preco_atual(insumo)


def buscar_insumo_compativel_por_nome(nome: str | None) -> dict | None:
    if not nome:
        return None
    insumos = _executar_lista_opcional(get_supabase_client().table("insumos").select("*"))
    nome_normalizado = normalizar_nome_insumo(nome)
    for insumo in insumos:
        normalizado_insumo = insumo.get("nome_normalizado") or normalizar_nome_insumo(
            insumo["nome"]
        )
        if normalizado_insumo == nome_normalizado:
            return _anexar_preco_atual(insumo)
    candidatos = [
        insumo
        for insumo in insumos
        if nomes_insumos_compativeis(nome, insumo["nome"])
    ]
    return _anexar_preco_atual(candidatos[0]) if len(candidatos) == 1 else None


def normalizar_unidade(unidade: str | None) -> str | None:
    if not unidade:
        return None
    return _normalizar_unidade(unidade)


def criar_receita(produto_id: UUID, requisicao: RequisicaoCriarReceita) -> dict:
    client = get_supabase_client()
    produto = servico_de_produtos.buscar_produto(produto_id)
    receita = (
        client.table("receitas_produto")
        .insert(
            to_db_payload(
                {
                    "produto_id": produto_id,
                    "nome": requisicao.nome or f"Receita de {produto['nome']}",
                    "rendimento": requisicao.rendimento,
                    "unidade_rendimento": requisicao.unidade_rendimento,
                    "status": requisicao.status,
                    "observacoes": requisicao.observacoes,
                }
            )
        )
        .execute()
        .data[0]
    )
    if requisicao.ingredientes:
        linhas = [
            _montar_linha_ingrediente(receita["id"], ingrediente)
            for ingrediente in requisicao.ingredientes
        ]
        client.table("ingredientes_receita").insert(linhas).execute()
    return buscar_receita(receita["id"])


def listar_receitas_do_produto(produto_id: UUID) -> list[dict]:
    servico_de_produtos.buscar_produto(produto_id)
    client = get_supabase_client()
    receitas = (
        _executar_lista_opcional(
            client.table("receitas_produto")
            .select("*")
            .eq("produto_id", str(produto_id))
            .order("criado_em", desc=True)
        )
    )
    return [_anexar_ingredientes(receita) for receita in receitas]


def listar_produtos_com_receita() -> list[dict]:
    client = get_supabase_client()
    produtos = (
        client.table("produtos")
        .select("id,nome,slug,situacao,ordem_exibicao")
        .eq("situacao", "ativo")
        .order("ordem_exibicao")
        .order("nome")
        .execute()
        .data
    )
    if not produtos:
        return []

    produto_ids = [produto["id"] for produto in produtos]
    receitas = _executar_lista_opcional(
        client.table("receitas_produto")
        .select("*")
        .in_("produto_id", produto_ids)
        .order("criado_em", desc=True)
    )
    receita_por_produto = _receita_mais_recente_por_produto(receitas)
    if not receita_por_produto:
        return []

    ingredientes_por_receita = _contar_ingredientes_por_receita(
        client,
        [receita["id"] for receita in receita_por_produto.values()],
    )
    saida = []
    for produto in produtos:
        receita = receita_por_produto.get(str(produto["id"]))
        if not receita:
            continue
        saida.append(
            {
                "produto_id": produto["id"],
                "nome": produto["nome"],
                "slug": produto.get("slug"),
                "situacao": produto["situacao"],
                "receita_id": receita["id"],
                "receita_nome": receita.get("nome"),
                "rendimento": receita["rendimento"],
                "unidade_rendimento": receita["unidade_rendimento"],
                "status": receita["status"],
                "total_ingredientes": ingredientes_por_receita.get(str(receita["id"]), 0),
            }
        )
    return saida


def buscar_receita(receita_id: UUID | str) -> dict:
    client = get_supabase_client()
    receita = first_or_none(
        _executar_lista_opcional(
            client.table("receitas_produto")
            .select("*")
            .eq("id", str(receita_id))
            .limit(1)
        )
    )
    if not receita:
        raise NotFoundError("Receita", str(receita_id))
    return _anexar_ingredientes(receita)


def criar_custo_adicional(
    produto_id: UUID,
    requisicao: RequisicaoCriarCustoAdicional,
) -> dict:
    client = get_supabase_client()
    servico_de_produtos.buscar_produto(produto_id)
    if requisicao.receita_id:
        receita = buscar_receita(requisicao.receita_id)
        if receita["produto_id"] != str(produto_id):
            raise BadRequestError("A receita informada nao pertence ao produto.")
    return (
        client.table("custos_adicionais_produto")
        .insert(to_db_payload({"produto_id": produto_id, **requisicao.model_dump()}))
        .execute()
        .data[0]
    )


def calcular_custo_do_produto(
    produto_id: UUID,
    receita_id: UUID | None = None,
    data_referencia: date | None = None,
) -> dict:
    data_calculo = data_referencia or date.today()
    produto = servico_de_produtos.buscar_produto(produto_id)
    receita = _resolver_receita(produto_id, receita_id)
    if not receita:
        return {
            "produto_id": str(produto_id),
            "produto": produto["nome"],
            "receita_id": None,
            "custo_total_receita": Decimal("0"),
            "rendimento": None,
            "custo_por_unidade": None,
            "custos_incluidos": _custos_incluidos([], ingredientes_incluidos=False),
            "status": "PENDENTE",
            "data_referencia": data_calculo,
            "ingredientes": [],
            "custos_adicionais": [],
            "pendencias": ["Nenhuma receita cadastrada para o produto."],
        }

    ingredientes = _ingredientes_com_custo_vigente(receita["ingredientes"], data_calculo)
    custos_adicionais = _listar_custos_adicionais(produto_id, receita["id"])
    custo_ingredientes = sum(
        (Decimal(str(item["custo_total_estimado"] or 0)) for item in ingredientes),
        Decimal("0"),
    )
    custo_extra = sum(
        (Decimal(str(item["valor"] or 0)) for item in custos_adicionais),
        Decimal("0"),
    )
    custo_total = _arredondar_moeda(custo_ingredientes + custo_extra)
    rendimento = Decimal(str(receita["rendimento"]))
    custo_por_unidade = _arredondar_moeda(custo_total / rendimento) if rendimento else None
    pendencias = _listar_pendencias(receita, ingredientes, custos_adicionais)
    status = _consolidar_status(
        [receita["status"]]
        + [ingrediente["status"] for ingrediente in ingredientes]
        + [custo["status"] for custo in custos_adicionais]
        + (["PENDENTE"] if pendencias else [])
    )
    return {
        "produto_id": produto["id"],
        "produto": produto["nome"],
        "receita_id": receita["id"],
        "custo_total_receita": custo_total,
        "rendimento": receita["rendimento"],
        "custo_por_unidade": custo_por_unidade,
        "custos_incluidos": _custos_incluidos(
            custos_adicionais,
            ingredientes_incluidos=bool(ingredientes),
        ),
        "status": status,
        "data_referencia": data_calculo,
        "ingredientes": ingredientes,
        "custos_adicionais": custos_adicionais,
        "pendencias": pendencias,
    }


def atualizar_precos_por_compra(requisicao: RequisicaoAtualizarPrecosPorCompra) -> dict:
    resultados = []
    criados = 0
    atualizados = 0
    ignorados = 0

    for item in requisicao.itens:
        resultado = _processar_item_atualizacao_preco(item, requisicao)
        resultados.append(resultado)
        if resultado["acao"] == "criado":
            criados += 1
        elif resultado["acao"] == "atualizado":
            atualizados += 1
        else:
            ignorados += 1

    return {
        "total_itens": len(requisicao.itens),
        "criados": criados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "aplicar": requisicao.aplicar,
        "itens": resultados,
        "avisos": _avisos_atualizacao_precos(resultados, requisicao.aplicar),
    }


async def atualizar_precos_por_nota_arquivo(
    *,
    file: UploadFile,
    vigente_desde: date,
    fornecedor: str | None = None,
    fonte: str | None = None,
    aplicar: bool = True,
    contexto: str | None = None,
) -> dict:
    conteudo = await file.read()
    if not conteudo:
        raise BadRequestError("Arquivo vazio.")
    itens = _extrair_itens_de_nota_com_openai(
        conteudo=conteudo,
        tipo_conteudo=file.content_type,
        contexto=contexto,
    )
    requisicao = RequisicaoAtualizarPrecosPorCompra(
        itens=itens,
        vigente_desde=vigente_desde,
        origem="nota",
        fornecedor=fornecedor,
        fonte=fonte or file.filename,
        aplicar=aplicar,
    )
    resposta = atualizar_precos_por_compra(requisicao)
    resposta["arquivo"] = {
        "nome": file.filename,
        "tipo_conteudo": file.content_type,
        "itens_extraidos": len(itens),
    }
    return resposta


def gerar_lista_compras(requisicao: RequisicaoGerarListaCompras) -> dict:
    grupos: dict[str, dict] = {}
    pendencias: list[str] = []
    multiplicador_margem = Decimal("1") + (
        Decimal(str(requisicao.margem_percentual)) / Decimal("100")
    )

    for item in requisicao.itens:
        produto = servico_de_produtos.buscar_produto(item.produto_id)
        receita = _resolver_receita(item.produto_id, item.receita_id)
        if not receita:
            pendencias.append(f"Produto {produto['nome']} nao tem receita cadastrada.")
            continue
        rendimento = Decimal(str(receita["rendimento"]))
        fator_receita = Decimal(str(item.quantidade)) / rendimento
        for ingrediente in receita["ingredientes"]:
            _acumular_ingrediente_na_lista(
                grupos,
                pendencias,
                ingrediente=ingrediente,
                produto=produto,
                receita=receita,
                quantidade_produto=Decimal(str(item.quantidade)),
                fator_receita=fator_receita,
                data_referencia=requisicao.data_referencia,
            )

    itens_saida = [
        _montar_item_lista_compras(grupo, multiplicador_margem)
        for grupo in grupos.values()
    ]
    total_estimado = _somar_total_estimado_lista(itens_saida)
    resposta = {
        "id": None,
        "nome": requisicao.nome,
        "data_referencia": requisicao.data_referencia,
        "margem_percentual": requisicao.margem_percentual,
        "total_estimado": total_estimado,
        "itens": itens_saida,
        "pendencias": _deduplicar_textos(pendencias),
        "criado_em": None,
    }
    if requisicao.salvar:
        lista = _salvar_lista_compras(resposta, requisicao)
        resposta["id"] = lista["id"]
        resposta["criado_em"] = lista["criado_em"]
    return resposta


def listar_listas_compras(*, limite: int = 50) -> list[dict]:
    listas = _executar_lista_opcional(
        get_supabase_client()
        .table("listas_compras")
        .select("*")
        .order("criado_em", desc=True)
        .limit(limite)
    )
    return [_lista_compras_da_linha(linha) for linha in listas]


def buscar_lista_compras(lista_id: UUID) -> dict:
    linha = first_or_none(
        _executar_lista_opcional(
            get_supabase_client()
            .table("listas_compras")
            .select("*")
            .eq("id", str(lista_id))
            .limit(1)
        )
    )
    if not linha:
        raise NotFoundError("Lista de compras", str(lista_id))
    return _lista_compras_da_linha(linha)


def _processar_item_atualizacao_preco(
    item: ItemAtualizacaoPrecoCompra,
    requisicao: RequisicaoAtualizarPrecosPorCompra,
) -> dict:
    if (
        item.quantidade_comprada is None
        or not item.unidade_compra
        or item.preco_total is None
    ):
        return {
            "nome_informado": item.nome,
            "acao": "ignorado",
            "insumo": None,
            "preco": None,
            "mensagem": "Item sem quantidade, unidade ou preco total.",
            "confianca": item.confianca,
        }

    insumo = (
        buscar_insumo(item.insumo_id)
        if item.insumo_id
        else buscar_insumo_compativel_por_nome(item.nome)
    )
    if not requisicao.aplicar:
        return {
            "nome_informado": item.nome,
            "acao": "simulado",
            "insumo": insumo,
            "preco": None,
            "mensagem": "Aplicacao desativada; nenhum preco foi gravado.",
            "confianca": item.confianca,
        }

    preco_requisicao = RequisicaoRegistrarPrecoInsumo(
        quantidade_comprada=item.quantidade_comprada,
        unidade_compra=item.unidade_compra,
        preco_total=item.preco_total,
        vigente_desde=requisicao.vigente_desde,
        origem=requisicao.origem,
        fornecedor=item.fornecedor or requisicao.fornecedor,
        fonte=requisicao.fonte,
        observacoes=item.observacoes,
        status="CONFIRMADO",
    )
    if insumo:
        if item.categoria and item.categoria != insumo.get("categoria"):
            get_supabase_client().table("insumos").update({"categoria": item.categoria}).eq(
                "id",
                insumo["id"],
            ).execute()
        atualizado = registrar_preco_insumo(UUID(insumo["id"]), preco_requisicao)
        return {
            "nome_informado": item.nome,
            "acao": "atualizado",
            "insumo": atualizado["insumo"],
            "preco": atualizado["preco"],
            "mensagem": "Preco atualizado no historico do insumo existente.",
            "confianca": item.confianca,
        }

    criado = criar_insumo(
        RequisicaoCriarInsumo(
            nome=item.nome,
            categoria=item.categoria,
            quantidade_comprada=item.quantidade_comprada,
            unidade_compra=item.unidade_compra,
            preco_total=item.preco_total,
            status="CONFIRMADO",
            observacoes=item.observacoes,
            vigente_desde=requisicao.vigente_desde,
            fornecedor=item.fornecedor or requisicao.fornecedor,
            fonte=requisicao.fonte,
        )
    )
    preco = buscar_preco_vigente_insumo(criado["id"], requisicao.vigente_desde, obrigatorio=False)
    return {
        "nome_informado": item.nome,
        "acao": "criado",
        "insumo": criado,
        "preco": preco,
        "mensagem": "Insumo criado e preco inicial gravado.",
        "confianca": item.confianca,
    }


def _avisos_atualizacao_precos(resultados: list[dict], aplicar: bool) -> list[str]:
    avisos = []
    if not aplicar:
        avisos.append("Aplicacao desativada: a resposta e apenas uma simulacao.")
    ignorados = [item["nome_informado"] for item in resultados if item["acao"] == "ignorado"]
    if ignorados:
        avisos.append(
            "Alguns itens nao foram gravados por falta de quantidade, unidade ou preco: "
            f"{', '.join(ignorados[:8])}."
        )
    return avisos


def _extrair_itens_de_nota_com_openai(
    *,
    conteudo: bytes,
    tipo_conteudo: str | None,
    contexto: str | None,
) -> list[ItemAtualizacaoPrecoCompra]:
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
        instructions=(
            "Extraia itens de uma nota/cupom de compra para atualizar catalogo de insumos. "
            "Use nomes genericos de ingrediente, removendo marca quando possivel. "
            "Retorne apenas itens com nome legivel; se quantidade, unidade ou preco estiverem "
            "incertos, deixe null e reduza a confianca. Nao invente dados."
        ),
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
                                    "Leia a nota e extraia nome, quantidade comprada, "
                                    "unidade de compra e preco total pago por item."
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
        text={"format": _formato_json_extracao_nota()},
    )
    dados = json.loads(resposta.output_text)
    return [
        ItemAtualizacaoPrecoCompra(
            nome=item.get("nome") or "Item sem nome",
            categoria=item.get("categoria"),
            quantidade_comprada=item.get("quantidade_comprada"),
            unidade_compra=item.get("unidade_compra"),
            preco_total=item.get("preco_total"),
            observacoes=item.get("observacoes"),
            confianca=item.get("confianca"),
        )
        for item in dados.get("itens", [])
        if item.get("nome")
    ]


def _formato_json_extracao_nota() -> dict:
    nullable_string = {"type": ["string", "null"]}
    nullable_number = {"type": ["number", "null"]}
    return {
        "type": "json_schema",
        "name": "extracao_nota_insumos_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["itens", "avisos"],
            "properties": {
                "itens": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "nome",
                            "categoria",
                            "quantidade_comprada",
                            "unidade_compra",
                            "preco_total",
                            "observacoes",
                            "confianca",
                        ],
                        "properties": {
                            "nome": {"type": "string"},
                            "categoria": nullable_string,
                            "quantidade_comprada": nullable_number,
                            "unidade_compra": nullable_string,
                            "preco_total": nullable_number,
                            "observacoes": nullable_string,
                            "confianca": nullable_number,
                        },
                    },
                },
                "avisos": {"type": "array", "items": {"type": "string"}},
            },
        },
        "strict": True,
    }


def _acumular_ingrediente_na_lista(
    grupos: dict[str, dict],
    pendencias: list[str],
    *,
    ingrediente: dict,
    produto: dict,
    receita: dict,
    quantidade_produto: Decimal,
    fator_receita: Decimal,
    data_referencia: date,
) -> None:
    try:
        tipo_unidade, fator_unidade = _resolver_unidade(ingrediente["unidade"])
    except BadRequestError as exc:
        pendencias.append(f"{ingrediente['nome_insumo_no_momento']}: {exc.message}")
        return

    quantidade_base = (
        Decimal(str(ingrediente["quantidade_usada"])) * fator_unidade * fator_receita
    )
    insumo = buscar_insumo(ingrediente["insumo_id"]) if ingrediente.get("insumo_id") else None
    chave = (
        f"insumo:{insumo['id']}"
        if insumo
        else f"nome:{normalizar_nome_insumo(ingrediente['nome_insumo_no_momento'])}"
    )
    if chave not in grupos:
        preco = (
            buscar_preco_vigente_insumo(insumo["id"], data_referencia, obrigatorio=False)
            if insumo
            else None
        )
        grupos[chave] = {
            "chave": chave,
            "insumo_id": insumo["id"] if insumo else None,
            "nome": insumo["nome"] if insumo else ingrediente["nome_insumo_no_momento"],
            "categoria": (insumo or {}).get("categoria"),
            "tipo_unidade": tipo_unidade,
            "quantidade_base": Decimal("0"),
            "custo_unitario_base": Decimal(str(preco["custo_por_unidade"])) if preco else None,
            "status": "CONFIRMADO" if preco else "PENDENTE",
            "observacoes": None if preco else "Sem preco vigente para estimar custo.",
            "contribuicoes": [],
        }
    grupo = grupos[chave]
    if grupo["tipo_unidade"] != tipo_unidade:
        pendencias.append(
            f"{grupo['nome']}: unidades incompativeis entre receitas para lista de compras."
        )
        return
    grupo["quantidade_base"] += quantidade_base
    grupo["contribuicoes"].append(
        {
            "produto_id": produto["id"],
            "produto": produto["nome"],
            "receita_id": receita["id"],
            "quantidade_produto": quantidade_produto,
            "quantidade_base": quantidade_base,
        }
    )


def _montar_item_lista_compras(grupo: dict, multiplicador_margem: Decimal) -> dict:
    quantidade_base = _arredondar_quantidade(grupo["quantidade_base"])
    quantidade_com_margem = _arredondar_quantidade(quantidade_base * multiplicador_margem)
    unidade_sugerida, quantidade_sugerida = _formatar_quantidade_para_compra(
        grupo["tipo_unidade"],
        quantidade_com_margem,
    )
    custo_estimado = None
    if grupo["custo_unitario_base"] is not None:
        custo_estimado = _arredondar_moeda(grupo["custo_unitario_base"] * quantidade_com_margem)
    return {
        "chave": grupo["chave"],
        "insumo_id": grupo["insumo_id"],
        "nome": grupo["nome"],
        "categoria": grupo["categoria"],
        "quantidade_base": quantidade_base,
        "unidade_base": _unidade_base_para_tipo(grupo["tipo_unidade"]),
        "quantidade_sugerida": quantidade_sugerida,
        "unidade_sugerida": unidade_sugerida,
        "custo_unitario_base": grupo["custo_unitario_base"],
        "custo_estimado": custo_estimado,
        "status": grupo["status"],
        "observacoes": grupo["observacoes"],
        "contribuicoes": grupo["contribuicoes"],
    }


def _somar_total_estimado_lista(itens: list[dict]) -> Decimal | None:
    valores = [item["custo_estimado"] for item in itens if item.get("custo_estimado") is not None]
    if not valores:
        return None
    return _arredondar_moeda(sum((Decimal(str(valor)) for valor in valores), Decimal("0")))


def _salvar_lista_compras(resposta: dict, requisicao: RequisicaoGerarListaCompras) -> dict:
    return (
        get_supabase_client()
        .table("listas_compras")
        .insert(
            to_db_payload(
                {
                    "nome": requisicao.nome,
                    "data_referencia": requisicao.data_referencia,
                    "margem_percentual": requisicao.margem_percentual,
                    "parametros": requisicao.model_dump(),
                    "itens": resposta["itens"],
                    "total_estimado": resposta["total_estimado"],
                    "pendencias": resposta["pendencias"],
                }
            )
        )
        .execute()
        .data[0]
    )


def _lista_compras_da_linha(linha: dict) -> dict:
    return {
        "id": linha["id"],
        "nome": linha.get("nome"),
        "data_referencia": linha["data_referencia"],
        "margem_percentual": linha["margem_percentual"],
        "total_estimado": linha.get("total_estimado"),
        "itens": linha.get("itens") or [],
        "pendencias": linha.get("pendencias") or [],
        "criado_em": linha["criado_em"],
    }


def _montar_linha_ingrediente(receita_id: UUID | str, ingrediente) -> dict:
    insumo = buscar_insumo(ingrediente.insumo_id) if ingrediente.insumo_id else None
    if not insumo:
        insumo = buscar_insumo_compativel_por_nome(ingrediente.nome)
    custo_unitario = None
    custo_total = None
    nome = ingrediente.nome
    status = ingrediente.status
    if insumo:
        nome = insumo["nome"]
        preco_vigente = buscar_preco_vigente_insumo(insumo["id"], date.today(), obrigatorio=False)
        custo_unitario = Decimal(str((preco_vigente or insumo)["custo_por_unidade"]))
        unidade_compra = (preco_vigente or insumo)["unidade_compra"]
        custo_total = _calcular_custo_ingrediente(
            custo_unitario,
            ingrediente.quantidade_usada,
            ingrediente.unidade,
            unidade_compra,
        )
        status = _consolidar_status([status, insumo["status"]])
    return to_db_payload(
        {
            "receita_id": receita_id,
            "insumo_id": insumo["id"] if insumo else ingrediente.insumo_id,
            "nome_insumo_no_momento": nome,
            "quantidade_usada": ingrediente.quantidade_usada,
            "unidade": _normalizar_unidade(ingrediente.unidade),
            "custo_unitario_no_momento": custo_unitario,
            "custo_total_estimado": custo_total,
            "status": status,
            "observacoes": ingrediente.observacoes,
        }
    )


def _anexar_ingredientes(receita: dict) -> dict:
    client = get_supabase_client()
    receita["ingredientes"] = _executar_lista_opcional(
        client.table("ingredientes_receita")
        .select("*")
        .eq("receita_id", receita["id"])
        .order("criado_em")
    )
    return receita


def _ingredientes_com_custo_vigente(ingredientes: list[dict], data_referencia: date) -> list[dict]:
    recalculados = []
    for ingrediente in ingredientes:
        item = dict(ingrediente)
        insumo_id = item.get("insumo_id")
        if not insumo_id:
            recalculados.append(item)
            continue
        preco = buscar_preco_vigente_insumo(insumo_id, data_referencia, obrigatorio=False)
        if not preco:
            item["custo_unitario_no_momento"] = None
            item["custo_total_estimado"] = None
            item["status"] = _consolidar_status([item["status"], "PENDENTE"])
            item["preco_insumo_vigente"] = None
            recalculados.append(item)
            continue
        try:
            custo_total = _calcular_custo_ingrediente(
                Decimal(str(preco["custo_por_unidade"])),
                Decimal(str(item["quantidade_usada"])),
                item["unidade"],
                preco["unidade_compra"],
            )
        except BadRequestError as exc:
            item["custo_unitario_no_momento"] = None
            item["custo_total_estimado"] = None
            item["status"] = _consolidar_status([item["status"], "PENDENTE"])
            item["pendencia_calculo"] = exc.message
            recalculados.append(item)
            continue
        item["custo_unitario_no_momento"] = preco["custo_por_unidade"]
        item["custo_total_estimado"] = custo_total
        item["preco_insumo_vigente"] = preco
        recalculados.append(item)
    return recalculados


def buscar_preco_vigente_insumo(
    insumo_id: UUID | str,
    data_referencia: date | None = None,
    *,
    obrigatorio: bool = True,
) -> dict | None:
    data_alvo = data_referencia or date.today()
    linhas = _executar_lista_opcional(
        get_supabase_client()
        .table("insumos_precos")
        .select("*")
        .eq("insumo_id", str(insumo_id))
        .lte("vigente_desde", data_alvo.isoformat())
        .order("vigente_desde", desc=True)
        .order("criado_em", desc=True)
        .limit(1)
    )
    preco = first_or_none(linhas)
    if preco or not obrigatorio:
        return preco
    raise NotFoundError("Preco vigente do insumo", str(insumo_id))


def _anexar_preco_atual(insumo: dict) -> dict:
    preco = buscar_preco_vigente_insumo(insumo["id"], date.today(), obrigatorio=False)
    insumo["preco_atual"] = preco
    if not insumo.get("nome_normalizado"):
        insumo["nome_normalizado"] = normalizar_nome_insumo(insumo["nome"])
    return insumo


def _registrar_preco_insumo_bruto(
    *,
    insumo_id: UUID,
    quantidade_comprada: Decimal,
    unidade_compra: str,
    preco_total: Decimal,
    custo_por_unidade: Decimal,
    vigente_desde: date,
    origem: str,
    fornecedor: str | None,
    fonte: str | None,
    observacoes: str | None,
) -> dict:
    return (
        get_supabase_client()
        .table("insumos_precos")
        .insert(
            to_db_payload(
                {
                    "insumo_id": insumo_id,
                    "quantidade_comprada": quantidade_comprada,
                    "unidade_compra": _normalizar_unidade(unidade_compra),
                    "preco_total": preco_total,
                    "custo_por_unidade": custo_por_unidade,
                    "vigente_desde": vigente_desde,
                    "origem": origem,
                    "fornecedor": fornecedor,
                    "fonte": fonte,
                    "observacoes": observacoes,
                }
            )
        )
        .execute()
        .data[0]
    )


def _dados_de_preco_foram_informados(requisicao: RequisicaoAtualizarInsumo) -> bool:
    return any(
        valor is not None
        for valor in (
            requisicao.quantidade_comprada,
            requisicao.unidade_compra,
            requisicao.preco_total,
        )
    )


def _resolver_receita(produto_id: UUID, receita_id: UUID | None) -> dict | None:
    if receita_id:
        receita = buscar_receita(receita_id)
        if receita["produto_id"] != str(produto_id):
            raise BadRequestError("A receita informada nao pertence ao produto.")
        return receita
    receitas = listar_receitas_do_produto(produto_id)
    return receitas[0] if receitas else None


def _receita_mais_recente_por_produto(receitas: list[dict]) -> dict[str, dict]:
    por_produto = {}
    for receita in receitas:
        produto_id = str(receita["produto_id"])
        if produto_id not in por_produto:
            por_produto[produto_id] = receita
    return por_produto


def _contar_ingredientes_por_receita(client, receita_ids: list[str]) -> dict[str, int]:
    if not receita_ids:
        return {}
    ingredientes = _executar_lista_opcional(
        client.table("ingredientes_receita")
        .select("receita_id")
        .in_("receita_id", receita_ids)
    )
    totais = {str(receita_id): 0 for receita_id in receita_ids}
    for ingrediente in ingredientes:
        receita_id = str(ingrediente["receita_id"])
        totais[receita_id] = totais.get(receita_id, 0) + 1
    return totais


def _listar_custos_adicionais(produto_id: UUID, receita_id: UUID | str | None) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("custos_adicionais_produto").select("*").eq(
        "produto_id", str(produto_id)
    )
    if receita_id:
        consulta = consulta.or_(f"receita_id.is.null,receita_id.eq.{receita_id}")
    return _executar_lista_opcional(consulta.order("criado_em"))


def _calcular_custo_por_unidade(
    preco_total: Decimal,
    quantidade: Decimal,
    unidade: str,
) -> Decimal:
    _, fator = _resolver_unidade(unidade)
    quantidade_base = Decimal(str(quantidade)) * fator
    if quantidade_base <= 0:
        raise BadRequestError("Quantidade comprada precisa ser maior que zero.")
    return _arredondar_custo_unitario(Decimal(str(preco_total)) / quantidade_base)


def _calcular_custo_ingrediente(
    custo_unitario_base: Decimal,
    quantidade_usada: Decimal,
    unidade_usada: str,
    unidade_compra: str,
) -> Decimal:
    tipo_compra, _ = _resolver_unidade(unidade_compra)
    tipo_usado, fator_usado = _resolver_unidade(unidade_usada)
    if tipo_compra != tipo_usado:
        raise BadRequestError(
            "Unidade do ingrediente incompativel com a unidade de compra.",
            {"unidade_compra": unidade_compra, "unidade_usada": unidade_usada},
        )
    quantidade_base = Decimal(str(quantidade_usada)) * fator_usado
    return _arredondar_moeda(custo_unitario_base * quantidade_base)


def _resolver_unidade(unidade: str) -> tuple[str, Decimal]:
    unidade_normalizada = _normalizar_unidade(unidade)
    unidade_com_equivalencia = _resolver_unidade_com_equivalencia_informada(unidade_normalizada)
    if unidade_com_equivalencia:
        return unidade_com_equivalencia
    if unidade_normalizada not in UNIDADES_BASE:
        raise BadRequestError("Unidade de medida ainda nao suportada.", {"unidade": unidade})
    return UNIDADES_BASE[unidade_normalizada]


def _normalizar_unidade(unidade: str) -> str:
    texto = unicodedata.normalize("NFKD", str(unidade).strip().lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    unidade_normalizada = re.sub(r"[^a-z0-9]+", " ", texto).strip()
    unidade_com_equivalencia = _normalizar_unidade_com_equivalencia_informada(
        unidade_normalizada
    )
    if unidade_com_equivalencia:
        return unidade_com_equivalencia
    return _extrair_unidade_de_texto_com_ruido(unidade_normalizada) or unidade_normalizada


def _normalizar_unidade_com_equivalencia_informada(unidade_normalizada: str) -> str | None:
    if _unidade_indica_quantidade_alternativa(unidade_normalizada):
        return None
    padroes = (
        (r"(\d+(?:[,.]\d+)?)\s*(kg|quilo|quilos|kilograma|kilogramas)\b", "kg"),
        (r"(\d+(?:[,.]\d+)?)\s*(g|grama|gramas)\b", "g"),
        (r"(\d+(?:[,.]\d+)?)\s*(ml|mililitro|mililitros)\b", "ml"),
        (r"(\d+(?:[,.]\d+)?)\s*(l|lt|litro|litros)\b", "l"),
        (r"(\d+(?:[,.]\d+)?)\s*(un|und|unidade|unidades)\b", "unidade"),
        (r"(\d+(?:[,.]\d+)?)\s*(ovo|ovos)\b", "ovos"),
    )
    for padrao, unidade in padroes:
        match = re.search(padrao, unidade_normalizada)
        if match:
            quantidade = Decimal(match.group(1).replace(",", "."))
            return f"{_decimal_unidade_str(quantidade)}{unidade}"
    return None


def _decimal_unidade_str(valor: Decimal) -> str:
    texto = format(valor.normalize(), "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def _extrair_unidade_de_texto_com_ruido(texto: str) -> str | None:
    if not texto or texto in UNIDADES_BASE:
        return texto or None
    texto_sem_quantidade = re.sub(r"^\d+(?:[,.]\d+)?\s*", "", texto).strip()
    if texto_sem_quantidade in UNIDADES_BASE:
        return texto_sem_quantidade
    for padrao, unidade in PADROES_UNIDADES_COM_RUIDO:
        if re.search(padrao, texto_sem_quantidade):
            return unidade
    return None


def normalizar_nome_insumo(nome: str | None) -> str:
    texto = unicodedata.normalize("NFKD", str(nome or "").strip().lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9]+", " ", texto).strip()
    substituicoes = {
        "mucarela": "mussarela",
        "mozarela": "mussarela",
        "mozzarella": "mussarela",
        "ovos": "ovo",
        "queijos": "queijo",
    }
    tokens = []
    for token in texto.split():
        token = substituicoes.get(token, token)
        if token in STOPWORDS_INGREDIENTE or token in DESCRITORES_INGREDIENTE:
            continue
        tokens.append(token)
    return " ".join(tokens)


def nomes_insumos_compativeis(nome_a: str | None, nome_b: str | None) -> bool:
    normalizado_a = normalizar_nome_insumo(nome_a)
    normalizado_b = normalizar_nome_insumo(nome_b)
    if not normalizado_a or not normalizado_b:
        return False
    if normalizado_a == normalizado_b:
        return True

    tokens_a = set(normalizado_a.split())
    tokens_b = set(normalizado_b.split())
    tokens_menores = tokens_a if len(tokens_a) <= len(tokens_b) else tokens_b
    tokens_maiores = tokens_b if len(tokens_a) <= len(tokens_b) else tokens_a
    if tokens_menores and tokens_menores <= tokens_maiores:
        return bool(tokens_menores - INGREDIENTES_GENERICOS_PARA_MATCH)

    if len(tokens_a) < 2 and len(tokens_b) < 2:
        return False
    comuns = tokens_a & tokens_b
    if not comuns:
        return False
    cobertura_menor = len(comuns) / min(len(tokens_a), len(tokens_b))
    cobertura_maior = len(comuns) / max(len(tokens_a), len(tokens_b))
    return cobertura_menor >= 0.75 and cobertura_maior >= 0.45


def _unidade_base_para_tipo(tipo_unidade: str) -> str:
    if tipo_unidade == "massa":
        return "g"
    if tipo_unidade == "volume":
        return "ml"
    return "unidade"


def _formatar_quantidade_para_compra(
    tipo_unidade: str,
    quantidade_base: Decimal,
) -> tuple[str, Decimal]:
    quantidade = Decimal(str(quantidade_base))
    if tipo_unidade == "massa" and quantidade >= Decimal("1000"):
        return "kg", _arredondar_quantidade(quantidade / Decimal("1000"))
    if tipo_unidade == "volume" and quantidade >= Decimal("1000"):
        return "l", _arredondar_quantidade(quantidade / Decimal("1000"))
    return _unidade_base_para_tipo(tipo_unidade), _arredondar_quantidade(quantidade)


def _resolver_unidade_com_equivalencia_informada(
    unidade_normalizada: str,
) -> tuple[str, Decimal] | None:
    if _unidade_indica_quantidade_alternativa(unidade_normalizada):
        return None

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(kg|quilo|quilos|kilograma|kilogramas)\b",
        unidade_normalizada,
    )
    if match:
        return "massa", Decimal(match.group(1).replace(",", ".")) * Decimal("1000")

    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(g|grama|gramas)\b", unidade_normalizada)
    if match:
        return "massa", Decimal(match.group(1).replace(",", "."))

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(ml|mililitro|mililitros)\b",
        unidade_normalizada,
    )
    if match:
        return "volume", Decimal(match.group(1).replace(",", "."))

    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(l|lt|litro|litros)\b", unidade_normalizada)
    if match:
        return "volume", Decimal(match.group(1).replace(",", ".")) * Decimal("1000")

    match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(un|und|unidade|unidades|ovo|ovos)\b",
        unidade_normalizada,
    )
    if match:
        return "unidade", Decimal(match.group(1).replace(",", "."))

    return None


def _unidade_indica_quantidade_alternativa(unidade_normalizada: str) -> bool:
    return bool(
        re.search(r"\b(?:ou|ate)\b\s*\d", unidade_normalizada)
        or re.search(r"\d+(?:[,.]\d+)?\s*(?:ou|a|ate|-)\s*\d", unidade_normalizada)
    )


def unidade_suportada(unidade: str | None) -> bool:
    if not unidade:
        return False
    try:
        _resolver_unidade(unidade)
    except BadRequestError:
        return False
    return True


def descrever_unidade_aproximada(unidade: str) -> str | None:
    unidade_normalizada = _normalizar_unidade(unidade)
    descricao = _descrever_unidade_com_equivalencia_informada(unidade_normalizada)
    if descricao:
        return descricao
    return DESCRICOES_UNIDADES_APROXIMADAS.get(unidade_normalizada)


def _descrever_unidade_com_equivalencia_informada(unidade_normalizada: str) -> str | None:
    unidade_resolvida = _resolver_unidade_com_equivalencia_informada(unidade_normalizada)
    if not unidade_resolvida:
        return None
    tipo, fator = unidade_resolvida
    if tipo == "massa":
        return f"{unidade_normalizada} = {fator} g"
    if tipo == "volume":
        return f"{unidade_normalizada} = {fator} ml"
    return f"{unidade_normalizada} = {fator} unidades"


def _consolidar_status(statuses: list[str]) -> str:
    return consolidar_status(statuses)


def _custos_incluidos(
    custos_adicionais: list[dict],
    *,
    ingredientes_incluidos: bool,
) -> dict:
    tipos = {custo["tipo"] for custo in custos_adicionais}
    return {
        "ingredientes": ingredientes_incluidos,
        "embalagem": "embalagem" in tipos,
        "gas": any(custo["nome"].lower() == "gas" for custo in custos_adicionais),
        "energia": any(custo["nome"].lower() == "energia" for custo in custos_adicionais),
        "transporte": "transporte" in tipos,
    }


def _listar_pendencias(
    receita: dict,
    ingredientes: list[dict],
    custos_adicionais: list[dict],
) -> list[str]:
    pendencias = []
    if not ingredientes:
        pendencias.append("Receita sem ingredientes cadastrados.")
    for ingrediente in ingredientes:
        if ingrediente.get("custo_total_estimado") is None:
            pendencias.append(
                f"Ingrediente {ingrediente['nome_insumo_no_momento']} sem custo calculado."
            )
    if Decimal(str(receita["rendimento"])) <= 0:
        pendencias.append("Receita sem rendimento valido.")
    if not custos_adicionais:
        pendencias.append("Custos de embalagem, transporte e indiretos ainda nao informados.")
    return pendencias


def _arredondar_moeda(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _arredondar_custo_unitario(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _arredondar_quantidade(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _deduplicar_textos(textos: list[str]) -> list[str]:
    resultado = []
    vistos = set()
    for texto in textos:
        chave = re.sub(r"\s+", " ", str(texto).strip().lower())
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(str(texto))
    return resultado


def _executar_lista_opcional(consulta) -> list[dict]:
    try:
        return consulta.execute().data
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return []
        raise


def _erro_tabela_ausente(exc: Exception) -> bool:
    mensagem = str(exc)
    return "PGRST205" in mensagem and "Could not find the table" in mensagem
