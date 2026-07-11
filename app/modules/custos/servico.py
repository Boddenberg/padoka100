import base64
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import executar_lista_opcional, tabela_ausente
from app.modules.custos.domain import (
    ingredientes as _ingredientes,
)
from app.modules.custos.domain import (
    receita as _receita,
)
from app.modules.custos.domain import (
    unidades as _unidades,
)
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

# Compatibilidade: a logica pura de unidades, matching de ingrediente e
# consolidacao de receita vive em app.modules.custos.domain. Mantemos aliases
# sob os nomes ja usados aqui e por app.modules.custos.assistente_servico.
_calcular_custo_por_unidade = _unidades.calcular_custo_por_unidade
_calcular_custo_ingrediente = _unidades.calcular_custo_ingrediente
_resolver_unidade = _unidades.resolver_unidade
_normalizar_unidade = _unidades.normalizar_unidade
_normalizar_unidade_com_equivalencia_informada = (
    _unidades.normalizar_unidade_com_equivalencia_informada
)
_decimal_unidade_str = _unidades.decimal_unidade_str
_extrair_unidade_de_texto_com_ruido = _unidades.extrair_unidade_de_texto_com_ruido
_unidade_base_para_tipo = _unidades.unidade_base_para_tipo
_formatar_quantidade_para_compra = _unidades.formatar_quantidade_para_compra
_resolver_unidade_com_equivalencia_informada = (
    _unidades.resolver_unidade_com_equivalencia_informada
)
_unidade_indica_quantidade_alternativa = _unidades.unidade_indica_quantidade_alternativa
_descrever_unidade_com_equivalencia_informada = (
    _unidades.descrever_unidade_com_equivalencia_informada
)
_arredondar_moeda = _unidades.arredondar_moeda
_arredondar_custo_unitario = _unidades.arredondar_custo_unitario
_arredondar_quantidade = _unidades.arredondar_quantidade
unidade_suportada = _unidades.unidade_suportada
descrever_unidade_aproximada = _unidades.descrever_unidade_aproximada
normalizar_nome_insumo = _ingredientes.normalizar_nome_insumo
nomes_insumos_compativeis = _ingredientes.nomes_insumos_compativeis
_deduplicar_textos = _ingredientes.deduplicar_textos
_custos_incluidos = _receita.custos_incluidos
_listar_pendencias = _receita.listar_pendencias
_consolidar_status = consolidar_status


def listar_insumos(*, usuario_id: UUID | str | None = None) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("insumos").select("*")
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    insumos = _executar_lista_opcional(consulta.order("nome"))
    return [_anexar_preco_atual(insumo) for insumo in insumos]


def criar_insumo(
    requisicao: RequisicaoCriarInsumo,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    existente = buscar_insumo_compativel_por_nome(requisicao.nome, usuario_id=usuario_id)
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
            usuario_id=usuario_id,
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
                    "usuario_id": usuario_id,
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
    return buscar_insumo(UUID(insumo["id"]), usuario_id=usuario_id)


def atualizar_insumo(
    insumo_id: UUID,
    requisicao: RequisicaoAtualizarInsumo,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    insumo = buscar_insumo(insumo_id, usuario_id=usuario_id)
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
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    insumo = buscar_insumo(insumo_id, usuario_id=usuario_id)
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


def listar_precos_insumo(insumo_id: UUID, *, usuario_id: UUID | str | None = None) -> list[dict]:
    buscar_insumo(insumo_id, usuario_id=usuario_id)
    client = get_supabase_client()
    return _executar_lista_opcional(
        client.table("insumos_precos")
        .select("*")
        .eq("insumo_id", str(insumo_id))
        .order("vigente_desde", desc=True)
        .order("criado_em", desc=True)
    )


def buscar_insumo(insumo_id: UUID | str, *, usuario_id: UUID | str | None = None) -> dict:
    client = get_supabase_client()
    consulta = client.table("insumos").select("*").eq("id", str(insumo_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    insumo = first_or_none(_executar_lista_opcional(consulta.limit(1)))
    if not insumo:
        raise NotFoundError("Insumo", str(insumo_id))
    return _anexar_preco_atual(insumo)


def buscar_insumo_compativel_por_nome(
    nome: str | None,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    if not nome:
        return None
    consulta = get_supabase_client().table("insumos").select("*")
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    insumos = _executar_lista_opcional(consulta)
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


def criar_receita(
    produto_id: UUID,
    requisicao: RequisicaoCriarReceita,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    produto = servico_de_produtos.buscar_produto(produto_id, usuario_id=usuario_id)
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
                    "usuario_id": usuario_id,
                }
            )
        )
        .execute()
        .data[0]
    )
    if requisicao.ingredientes:
        linhas = [
            _montar_linha_ingrediente(receita["id"], ingrediente, usuario_id=usuario_id)
            for ingrediente in requisicao.ingredientes
        ]
        client.table("ingredientes_receita").insert(linhas).execute()
    return buscar_receita(receita["id"], usuario_id=usuario_id)


def listar_receitas_do_produto(
    produto_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    servico_de_produtos.buscar_produto(produto_id, usuario_id=usuario_id)
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


def listar_produtos_com_receita(*, usuario_id: UUID | str | None = None) -> list[dict]:
    client = get_supabase_client()
    consulta = (
        client.table("produtos")
        .select("id,nome,slug,situacao,ordem_exibicao")
        .eq("situacao", "ativo")
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    produtos = consulta.order("ordem_exibicao").order("nome").execute().data
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


def buscar_receita(receita_id: UUID | str, *, usuario_id: UUID | str | None = None) -> dict:
    client = get_supabase_client()
    consulta = client.table("receitas_produto").select("*").eq("id", str(receita_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    receita = first_or_none(_executar_lista_opcional(consulta.limit(1)))
    if not receita:
        raise NotFoundError("Receita", str(receita_id))
    return _anexar_ingredientes(receita)


def criar_custo_adicional(
    produto_id: UUID,
    requisicao: RequisicaoCriarCustoAdicional,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    servico_de_produtos.buscar_produto(produto_id, usuario_id=usuario_id)
    if requisicao.receita_id:
        receita = buscar_receita(requisicao.receita_id, usuario_id=usuario_id)
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
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    data_calculo = data_referencia or date.today()
    produto = servico_de_produtos.buscar_produto(produto_id, usuario_id=usuario_id)
    receita = _resolver_receita(produto_id, receita_id, usuario_id=usuario_id)
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


def atualizar_precos_por_compra(
    requisicao: RequisicaoAtualizarPrecosPorCompra,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    resultados = []
    criados = 0
    atualizados = 0
    ignorados = 0

    for item in requisicao.itens:
        resultado = _processar_item_atualizacao_preco(item, requisicao, usuario_id=usuario_id)
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
    usuario_id: UUID | str | None = None,
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
    resposta = atualizar_precos_por_compra(requisicao, usuario_id=usuario_id)
    resposta["arquivo"] = {
        "nome": file.filename,
        "tipo_conteudo": file.content_type,
        "itens_extraidos": len(itens),
    }
    return resposta


def gerar_lista_compras(
    requisicao: RequisicaoGerarListaCompras,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    grupos: dict[str, dict] = {}
    pendencias: list[str] = []
    multiplicador_margem = Decimal("1") + (
        Decimal(str(requisicao.margem_percentual)) / Decimal("100")
    )

    for item in requisicao.itens:
        produto = servico_de_produtos.buscar_produto(item.produto_id, usuario_id=usuario_id)
        receita = _resolver_receita(item.produto_id, item.receita_id, usuario_id=usuario_id)
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
                usuario_id=usuario_id,
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
        lista = _salvar_lista_compras(resposta, requisicao, usuario_id=usuario_id)
        resposta["id"] = lista["id"]
        resposta["criado_em"] = lista["criado_em"]
    return resposta


def listar_listas_compras(
    *,
    limite: int = 50,
    usuario_id: UUID | str | None = None,
) -> list[dict]:
    consulta = get_supabase_client().table("listas_compras").select("*")
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    listas = _executar_lista_opcional(consulta.order("criado_em", desc=True).limit(limite))
    return [_lista_compras_da_linha(linha) for linha in listas]


def buscar_lista_compras(lista_id: UUID, *, usuario_id: UUID | str | None = None) -> dict:
    consulta = get_supabase_client().table("listas_compras").select("*").eq("id", str(lista_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    linha = first_or_none(_executar_lista_opcional(consulta.limit(1)))
    if not linha:
        raise NotFoundError("Lista de compras", str(lista_id))
    return _lista_compras_da_linha(linha)


def _processar_item_atualizacao_preco(
    item: ItemAtualizacaoPrecoCompra,
    requisicao: RequisicaoAtualizarPrecosPorCompra,
    *,
    usuario_id: UUID | str | None = None,
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
        buscar_insumo(item.insumo_id, usuario_id=usuario_id)
        if item.insumo_id
        else buscar_insumo_compativel_por_nome(item.nome, usuario_id=usuario_id)
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
        atualizado = registrar_preco_insumo(
            UUID(insumo["id"]),
            preco_requisicao,
            usuario_id=usuario_id,
        )
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
        ),
        usuario_id=usuario_id,
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
    usuario_id: UUID | str | None = None,
) -> None:
    try:
        tipo_unidade, fator_unidade = _resolver_unidade(ingrediente["unidade"])
    except BadRequestError as exc:
        pendencias.append(f"{ingrediente['nome_insumo_no_momento']}: {exc.message}")
        return

    quantidade_base = (
        Decimal(str(ingrediente["quantidade_usada"])) * fator_unidade * fator_receita
    )
    insumo = (
        buscar_insumo(ingrediente["insumo_id"], usuario_id=usuario_id)
        if ingrediente.get("insumo_id")
        else None
    )
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


def _salvar_lista_compras(
    resposta: dict,
    requisicao: RequisicaoGerarListaCompras,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
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
                    "usuario_id": usuario_id,
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


def _montar_linha_ingrediente(
    receita_id: UUID | str,
    ingrediente,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    insumo = (
        buscar_insumo(ingrediente.insumo_id, usuario_id=usuario_id)
        if ingrediente.insumo_id
        else None
    )
    if not insumo:
        insumo = buscar_insumo_compativel_por_nome(ingrediente.nome, usuario_id=usuario_id)
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


def _resolver_receita(
    produto_id: UUID,
    receita_id: UUID | None,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    if receita_id:
        receita = buscar_receita(receita_id, usuario_id=usuario_id)
        if receita["produto_id"] != str(produto_id):
            raise BadRequestError("A receita informada nao pertence ao produto.")
        return receita
    receitas = listar_receitas_do_produto(produto_id, usuario_id=usuario_id)
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


# Helpers centralizados em infra; aliases preservam os nomes locais.
_executar_lista_opcional = executar_lista_opcional
_erro_tabela_ausente = tabela_ausente
