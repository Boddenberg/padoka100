from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda.esquemas import (
    RequisicaoAtualizarDiaDeVenda,
    RequisicaoCorrigirDiaFechado,
    RequisicaoCorrigirItemVendaDiaFechado,
    RequisicaoCorrigirProducaoDiaFechado,
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoDecisaoSobra,
    RequisicaoFecharDiaDeVenda,
    RequisicaoIniciarDiaDeVenda,
    RequisicaoVendaRetroativaDiaFechado,
)
from app.modules.locais import servico as servico_de_locais
from app.modules.produtos import servico as servico_de_produtos
from app.shared.datas import data_operacional_hoje, validar_data_nao_futura, validar_periodo
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from supabase import Client


def listar_dias_de_venda(
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
) -> list[dict]:
    if data_inicio and data_fim:
        validar_periodo(data_inicio, data_fim)
    elif data_inicio:
        validar_data_nao_futura(data_inicio, campo="data_inicio")
    elif data_fim:
        validar_data_nao_futura(data_fim, campo="data_fim")

    client = get_supabase_client()
    consulta = client.table("dias_de_venda").select("*").order("data_venda", desc=True)
    if data_inicio:
        consulta = consulta.gte("data_venda", data_inicio.isoformat())
    if data_fim:
        consulta = consulta.lte("data_venda", data_fim.isoformat())
    if situacao:
        consulta = consulta.eq("situacao", situacao)
    dias = consulta.execute().data
    return [_anexar_itens_producao(client, dia) for dia in dias]


def criar_dia_de_venda(requisicao: RequisicaoCriarDiaDeVenda) -> dict:
    validar_data_nao_futura(requisicao.data_venda, campo="data_venda")
    client = get_supabase_client()
    nome_local_no_momento = requisicao.nome_local
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        nome_local_no_momento = local["nome"]

    dados_dia = to_db_payload(
        {
            "data_venda": requisicao.data_venda,
            "local_id": requisicao.local_id,
            "nome_local_no_momento": nome_local_no_momento,
            "observacoes": requisicao.observacoes,
            "situacao": "aberto",
        }
    )
    dia_de_venda = client.table("dias_de_venda").insert(dados_dia).execute().data[0]
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_aberto",
        titulo=f"Dia aberto: {dia_de_venda['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda["id"],
        dia_de_venda_id=dia_de_venda["id"],
        detalhes={"nome_local": nome_local_no_momento},
    )

    for item in requisicao.itens_producao:
        salvar_item_producao(UUID(dia_de_venda["id"]), item)

    return buscar_dia_de_venda(UUID(dia_de_venda["id"]))


def iniciar_dia_de_venda(requisicao: RequisicaoIniciarDiaDeVenda) -> dict:
    client = get_supabase_client()
    data_venda = requisicao.data_venda or data_operacional_hoje()
    validar_data_nao_futura(data_venda, campo="data_venda")
    dia_atual_existente = _buscar_dia_aberto_por_data(client, data_venda)
    criar_nova_abertura = requisicao.criar_nova_abertura or _requisicao_indica_nova_abertura(
        requisicao,
        dia_atual_existente=dia_atual_existente,
    )
    dia_atual = None if criar_nova_abertura else dia_atual_existente
    dia_anterior = _buscar_dia_aberto_anterior(client, data_venda)
    sobras_pendentes = []
    if dia_anterior:
        sobras_pendentes = _calcular_sobras_pendentes(client, dia_anterior["id"])
    else:
        dia_anterior, sobras_pendentes = _buscar_dia_fechado_anterior_com_sobra_pendente(
            client,
            data_venda,
        )

    if not dia_anterior:
        if dia_atual:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)
            return {
                "acao": "dia_atual_aberto",
                "mensagem": "O dia de venda de hoje ja esta aberto.",
                "data_venda": data_venda,
                "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])),
                "dia_anterior": None,
                "sobras_pendentes": [],
                "decisoes_sobra": _listar_decisoes_sobra_do_destino(client, dia_atual["id"]),
            }
        if requisicao.decisoes_sobra:
            raise BadRequestError("Nao ha dia anterior com sobra pendente.")

        dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, None)
        mensagem = (
            "Nova abertura criada para este dia."
            if dia_atual_existente and criar_nova_abertura
            else "Dia de venda iniciado."
        )
        return {
            "acao": "dia_iniciado",
            "mensagem": mensagem,
            "data_venda": data_venda,
            "dia_de_venda": dia_atual,
            "dia_anterior": None,
            "sobras_pendentes": [],
            "decisoes_sobra": [],
        }

    if sobras_pendentes:
        decisoes_existentes = []
        if dia_atual:
            decisoes_existentes = _listar_decisoes_sobra_por_origem_destino(
                client,
                dia_origem_id=dia_anterior["id"],
                dia_destino_id=dia_atual["id"],
            )
        if not requisicao.decisoes_sobra and not decisoes_existentes:
            return {
                "acao": "decidir_sobras",
                "mensagem": (
                    "Existe sobra do dia anterior. Escolha o que usar hoje antes de iniciar."
                ),
                "data_venda": data_venda,
                "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])) if dia_atual else None,
                "dia_anterior": _anexar_itens_producao(client, dia_anterior),
                "sobras_pendentes": sobras_pendentes,
                "decisoes_sobra": [],
            }
        if not dia_atual:
            dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, dia_anterior)
        else:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)

        if decisoes_existentes:
            decisoes_sobra = decisoes_existentes
        else:
            decisoes_sobra = _registrar_decisoes_sobra(
                client,
                dia_origem=dia_anterior,
                dia_destino=dia_atual,
                sobras_pendentes=sobras_pendentes,
                decisoes=requisicao.decisoes_sobra,
            )
    else:
        if requisicao.decisoes_sobra:
            raise BadRequestError("O dia anterior nao tem sobra pendente.")
        decisoes_sobra = []
        if not dia_atual:
            dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, dia_anterior)
        else:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)

    if dia_anterior["situacao"] == "fechado":
        dia_anterior_saida = buscar_dia_de_venda(UUID(dia_anterior["id"]))
        mensagem = "Novo dia iniciado com sobras do dia anterior."
    else:
        dia_anterior_saida = fechar_dia_de_venda(
            UUID(dia_anterior["id"]),
            RequisicaoFecharDiaDeVenda(observacoes=requisicao.observacoes_fechamento_dia_anterior),
        )
        mensagem = "Dia anterior fechado e novo dia iniciado."

    return {
        "acao": "dia_iniciado",
        "mensagem": mensagem,
        "data_venda": data_venda,
        "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])),
        "dia_anterior": dia_anterior_saida,
        "sobras_pendentes": [],
        "decisoes_sobra": decisoes_sobra,
    }


def buscar_dia_de_venda_atual(*, data_venda: date | None = None) -> dict:
    if data_venda:
        validar_data_nao_futura(data_venda, campo="data_venda")

    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .order("aberto_em", desc=True)
    )
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    dia_de_venda = first_or_none(consulta.limit(1).execute().data)
    if not dia_de_venda:
        raise NotFoundError(
            "Dia de venda aberto",
            data_venda.isoformat() if data_venda else "atual",
        )
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_dia_de_venda(dia_de_venda_id: UUID | str) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_linha_dia_de_venda(client: Client, dia_de_venda_id: UUID | str) -> dict:
    dia_de_venda = first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("id", str(dia_de_venda_id))
        .limit(1)
        .execute()
        .data
    )
    if not dia_de_venda:
        raise NotFoundError("Dia de venda", str(dia_de_venda_id))
    return dia_de_venda


def atualizar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoAtualizarDiaDeVenda,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel editar um dia fechado.")

    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        dados_atualizacao["nome_local_no_momento"] = local["nome"]
    elif requisicao.nome_local is not None:
        dados_atualizacao["nome_local_no_momento"] = requisicao.nome_local
    dados_atualizacao.pop("nome_local", None)

    if dados_atualizacao:
        dia_de_venda = (
            client.table("dias_de_venda")
            .update(to_db_payload(dados_atualizacao))
            .eq("id", str(dia_de_venda_id))
            .execute()
            .data[0]
        )
        registrar_evento_na_linha_do_tempo(
            client,
            tipo_evento="dia_de_venda_atualizado",
            titulo=f"Dia atualizado: {dia_de_venda['data_venda']}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_de_venda_id,
            dia_de_venda_id=dia_de_venda_id,
            detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
        )
    return _anexar_itens_producao(client, dia_de_venda)


def salvar_item_producao(dia_de_venda_id: UUID, requisicao: RequisicaoCriarItemProducao) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel alterar a producao de um dia fechado.")

    snapshot = servico_de_produtos.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
    )
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    dados_item = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda_id,
            "produto_id": requisicao.produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco["preco_venda"],
            "preco_custo_unitario_no_momento": preco["preco_custo"],
            "quantidade_produzida": requisicao.quantidade_produzida,
            "observacoes": requisicao.observacoes,
        }
    )

    existente = first_or_none(
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("produto_id", str(requisicao.produto_id))
        .limit(1)
        .execute()
        .data
    )
    if existente:
        item = (
            client.table("itens_producao")
            .update(dados_item)
            .eq("id", existente["id"])
            .execute()
            .data[0]
        )
        tipo_evento = "item_producao_atualizado"
        titulo = f"Producao atualizada: {produto['nome']}"
    else:
        item = client.table("itens_producao").insert(dados_item).execute().data[0]
        tipo_evento = "item_producao_adicionado"
        titulo = f"Producao adicionada: {produto['nome']}"

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento=tipo_evento,
        titulo=titulo,
        tipo_entidade="item_producao",
        entidade_id=item["id"],
        dia_de_venda_id=dia_de_venda_id,
        detalhes={
            "produto_id": str(requisicao.produto_id),
            "quantidade_produzida": requisicao.quantidade_produzida,
            "preco_venda_unitario_no_momento": preco["preco_venda"],
        },
    )
    return item


def fechar_dia_de_venda(dia_de_venda_id: UUID, requisicao: RequisicaoFecharDiaDeVenda) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        return _anexar_itens_producao(client, dia_de_venda)

    dados_atualizacao = {
        "situacao": "fechado",
        "fechado_em": datetime.now(UTC),
    }
    if requisicao.observacoes is not None:
        dados_atualizacao["observacoes"] = requisicao.observacoes
    dia_fechado = (
        client.table("dias_de_venda")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(dia_de_venda_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_fechado",
        titulo=f"Dia fechado: {dia_fechado['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda_id,
        dia_de_venda_id=dia_de_venda_id,
    )
    return _anexar_itens_producao(client, dia_fechado)


def corrigir_dia_fechado(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCorrigirDiaFechado,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] != "fechado":
        raise BadRequestError("Somente dias fechados podem receber correcao retroativa.")

    if not any(
        [
            requisicao.producoes,
            requisicao.itens_venda,
            requisicao.vendas_adicionadas,
            requisicao.vendas_canceladas,
        ]
    ):
        raise BadRequestError("Informe ao menos uma alteracao para corrigir o dia fechado.")

    alteracoes: list[dict] = []
    for producao in requisicao.producoes:
        alteracao = _corrigir_producao_em_dia_fechado(client, dia_de_venda, producao)
        if alteracao:
            alteracoes.append(alteracao)

    for item_venda in requisicao.itens_venda:
        alteracao = _corrigir_item_venda_em_dia_fechado(client, dia_de_venda, item_venda)
        if alteracao:
            alteracoes.append(alteracao)

    for venda_retroativa in requisicao.vendas_adicionadas:
        alteracoes.append(
            _registrar_venda_retroativa_em_dia_fechado(dia_de_venda, venda_retroativa)
        )

    for cancelamento in requisicao.vendas_canceladas:
        alteracao = _cancelar_venda_em_correcao(
            dia_de_venda,
            cancelamento.venda_id,
            cancelamento.motivo,
        )
        if alteracao:
            alteracoes.append(alteracao)

    if not alteracoes:
        raise BadRequestError("Nenhuma alteracao aplicavel foi encontrada para a correcao.")

    correcao = (
        client.table("correcoes_dia_fechado")
        .insert(
            to_db_payload(
                {
                    "dia_de_venda_id": dia_de_venda_id,
                    "usuario_id": requisicao.usuario_id,
                    "motivo": requisicao.motivo,
                    "alteracoes": alteracoes,
                }
            )
        )
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="CORRECAO_DIA_FECHADO",
        titulo=f"Correcao retroativa: {dia_de_venda['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda_id,
        dia_de_venda_id=dia_de_venda_id,
        detalhes={
            "correcao_id": correcao["id"],
            "usuario_id": requisicao.usuario_id,
            "motivo": requisicao.motivo,
            "alteracoes": alteracoes,
        },
    )
    return correcao


def _corrigir_producao_em_dia_fechado(
    client: Client,
    dia_de_venda: dict,
    requisicao: RequisicaoCorrigirProducaoDiaFechado,
) -> dict | None:
    existente = first_or_none(
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .eq("produto_id", str(requisicao.produto_id))
        .limit(1)
        .execute()
        .data
    )
    if existente:
        dados_atualizacao = {"quantidade_produzida": requisicao.quantidade_produzida}
        if requisicao.observacoes is not None:
            dados_atualizacao["observacoes"] = requisicao.observacoes

        alteracoes = []
        if existente["quantidade_produzida"] != requisicao.quantidade_produzida:
            alteracoes.append(
                {
                    "campo": "quantidade_produzida",
                    "valor_anterior": existente["quantidade_produzida"],
                    "valor_novo": requisicao.quantidade_produzida,
                }
            )
        if (
            requisicao.observacoes is not None
            and existente.get("observacoes") != requisicao.observacoes
        ):
            alteracoes.append(
                {
                    "campo": "observacoes",
                    "valor_anterior": existente.get("observacoes"),
                    "valor_novo": requisicao.observacoes,
                }
            )
        if not alteracoes:
            return None

        client.table("itens_producao").update(to_db_payload(dados_atualizacao)).eq(
            "id",
            existente["id"],
        ).execute()
        return {
            "tipo": "PRODUCAO_CORRIGIDA",
            "produto_id": existente["produto_id"],
            "produto": existente["nome_produto_no_momento"],
            "item_producao_id": existente["id"],
            "alteracoes": alteracoes,
        }

    snapshot = servico_de_produtos.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
    )
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    dados_item = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda["id"],
            "produto_id": requisicao.produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco["preco_venda"],
            "preco_custo_unitario_no_momento": preco["preco_custo"],
            "quantidade_produzida": requisicao.quantidade_produzida,
            "observacoes": requisicao.observacoes,
        }
    )
    item = client.table("itens_producao").insert(dados_item).execute().data[0]
    return {
        "tipo": "PRODUCAO_ADICIONADA",
        "produto_id": item["produto_id"],
        "produto": item["nome_produto_no_momento"],
        "item_producao_id": item["id"],
        "alteracoes": [
            {
                "campo": "quantidade_produzida",
                "valor_anterior": None,
                "valor_novo": item["quantidade_produzida"],
            }
        ],
    }


def _corrigir_item_venda_em_dia_fechado(
    client: Client,
    dia_de_venda: dict,
    requisicao: RequisicaoCorrigirItemVendaDiaFechado,
) -> dict | None:
    item = first_or_none(
        client.table("itens_venda")
        .select("*")
        .eq("id", str(requisicao.item_venda_id))
        .limit(1)
        .execute()
        .data
    )
    if not item:
        raise NotFoundError("Item de venda", str(requisicao.item_venda_id))
    if item["dia_de_venda_id"] != dia_de_venda["id"]:
        raise BadRequestError(
            "O item de venda informado nao pertence ao dia fechado.",
            {
                "item_venda_id": str(requisicao.item_venda_id),
                "dia_de_venda_id": dia_de_venda["id"],
            },
        )
    if item["quantidade"] == requisicao.quantidade:
        return None

    preco_venda = Decimal(str(item["preco_venda_unitario_no_momento"]))
    preco_custo = Decimal(str(item["preco_custo_unitario_no_momento"]))
    valor_total_venda = preco_venda * requisicao.quantidade
    valor_total_custo = preco_custo * requisicao.quantidade
    item_atualizado = (
        client.table("itens_venda")
        .update(
            to_db_payload(
                {
                    "quantidade": requisicao.quantidade,
                    "valor_total_venda": valor_total_venda,
                    "valor_total_custo": valor_total_custo,
                }
            )
        )
        .eq("id", str(requisicao.item_venda_id))
        .execute()
        .data[0]
    )
    return {
        "tipo": "ITEM_VENDA_CORRIGIDO",
        "venda_id": item["venda_id"],
        "item_venda_id": item["id"],
        "produto_id": item["produto_id"],
        "produto": item["nome_produto_no_momento"],
        "alteracoes": [
            {
                "campo": "quantidade",
                "valor_anterior": item["quantidade"],
                "valor_novo": item_atualizado["quantidade"],
            },
            {
                "campo": "valor_total_venda",
                "valor_anterior": item["valor_total_venda"],
                "valor_novo": item_atualizado["valor_total_venda"],
            },
        ],
    }


def _registrar_venda_retroativa_em_dia_fechado(
    dia_de_venda: dict,
    requisicao: RequisicaoVendaRetroativaDiaFechado,
) -> dict:
    from app.modules.vendas import servico as servico_de_vendas
    from app.modules.vendas.esquemas import RequisicaoItemVendido, RequisicaoRegistrarVenda

    venda = servico_de_vendas.registrar_venda(
        RequisicaoRegistrarVenda(
            dia_de_venda_id=UUID(dia_de_venda["id"]),
            itens=[
                RequisicaoItemVendido(produto_id=item.produto_id, quantidade=item.quantidade)
                for item in requisicao.itens
            ],
            tipo_entrada="manual",
            texto_original=requisicao.texto_original,
            observacoes=requisicao.observacoes,
            ocorrido_em=requisicao.ocorrido_em,
        ),
        permitir_dia_fechado=True,
        detalhes_evento={"origem": "correcao_dia_fechado"},
    )
    return {
        "tipo": "VENDA_ADICIONADA",
        "venda_id": venda["id"],
        "alteracoes": [
            {
                "campo": "venda",
                "valor_anterior": None,
                "valor_novo": {
                    "venda_id": venda["id"],
                    "itens": venda["itens"],
                    "ocorrido_em": venda["ocorrido_em"],
                },
            }
        ],
    }


def _cancelar_venda_em_correcao(
    dia_de_venda: dict,
    venda_id: UUID,
    motivo: str | None,
) -> dict | None:
    from app.modules.vendas import servico as servico_de_vendas
    from app.modules.vendas.esquemas import RequisicaoCancelarVenda

    venda_antes = servico_de_vendas.buscar_venda(venda_id)
    if venda_antes["dia_de_venda_id"] != dia_de_venda["id"]:
        raise BadRequestError(
            "A venda informada nao pertence ao dia fechado.",
            {"venda_id": str(venda_id), "dia_de_venda_id": dia_de_venda["id"]},
        )
    if venda_antes["situacao"] == "cancelada":
        return None

    venda_cancelada = servico_de_vendas.cancelar_venda(
        venda_id,
        RequisicaoCancelarVenda(motivo=motivo),
    )
    return {
        "tipo": "VENDA_CANCELADA",
        "venda_id": venda_cancelada["id"],
        "alteracoes": [
            {
                "campo": "situacao",
                "valor_anterior": venda_antes["situacao"],
                "valor_novo": venda_cancelada["situacao"],
            },
            {
                "campo": "motivo_cancelamento",
                "valor_anterior": venda_antes.get("motivo_cancelamento"),
                "valor_novo": venda_cancelada.get("motivo_cancelamento"),
            },
        ],
    }


def _anexar_itens_producao(client: Client, dia_de_venda: dict) -> dict:
    itens = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
    dia_de_venda["itens_producao"] = itens
    dia_de_venda["sobras_usadas_hoje"] = _listar_decisoes_sobra_do_destino(
        client,
        dia_de_venda["id"],
    )
    return dia_de_venda


def _buscar_dia_aberto_por_data(client: Client, data_venda: date) -> dict | None:
    return first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .eq("data_venda", data_venda.isoformat())
        .order("aberto_em", desc=True)
        .limit(1)
        .execute()
        .data
    )


def _buscar_dia_aberto_anterior(client: Client, data_venda: date) -> dict | None:
    dia = first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .lt("data_venda", data_venda.isoformat())
        .order("data_venda", desc=True)
        .order("aberto_em", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if dia and _dia_parece_seed_analytics(dia):
        return None
    return dia


def _buscar_dia_fechado_anterior_com_sobra_pendente(
    client: Client,
    data_venda: date,
) -> tuple[dict | None, list[dict]]:
    dia = first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "fechado")
        .lt("data_venda", data_venda.isoformat())
        .order("data_venda", desc=True)
        .order("fechado_em", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not dia or _dia_parece_seed_analytics(dia):
        return None, []
    if _dia_tem_decisao_de_sobra_como_origem(client, dia["id"]):
        return None, []
    sobras_pendentes = _calcular_sobras_pendentes(client, dia["id"])
    if not sobras_pendentes:
        return None, []
    return dia, sobras_pendentes


def _dia_parece_seed_analytics(dia: dict) -> bool:
    texto = " ".join(
        [
            str(dia.get("nome_local_no_momento") or ""),
            str(dia.get("observacoes") or ""),
        ]
    ).lower()
    return "seed analytics" in texto or "seed_analytics" in texto


def _dia_tem_decisao_de_sobra_como_origem(client: Client, dia_de_venda_id: UUID | str) -> bool:
    decisao = first_or_none(
        client.table("decisoes_sobra")
        .select("id")
        .eq("dia_origem_id", str(dia_de_venda_id))
        .limit(1)
        .execute()
        .data
    )
    return decisao is not None


def _requisicao_indica_nova_abertura(
    requisicao: RequisicaoIniciarDiaDeVenda,
    *,
    dia_atual_existente: dict | None,
) -> bool:
    if not dia_atual_existente:
        return False
    return any(
        [
            bool(requisicao.itens_producao),
            requisicao.observacoes is not None,
            requisicao.local_id is not None,
            requisicao.nome_local is not None,
        ]
    )


def _criar_dia_de_venda_para_inicio(
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    dia_anterior: dict | None,
) -> dict:
    local_id = requisicao.local_id
    nome_local = requisicao.nome_local
    if not local_id and nome_local is None and dia_anterior:
        local_id = dia_anterior.get("local_id")
        nome_local = None if local_id else dia_anterior.get("nome_local_no_momento")

    return criar_dia_de_venda(
        RequisicaoCriarDiaDeVenda(
            data_venda=data_venda,
            local_id=local_id,
            nome_local=nome_local,
            observacoes=requisicao.observacoes,
            itens_producao=requisicao.itens_producao,
        )
    )


def _salvar_itens_producao_informados(
    dia_de_venda_id: UUID,
    itens_producao: list[RequisicaoCriarItemProducao],
) -> None:
    for item in itens_producao:
        salvar_item_producao(dia_de_venda_id, item)


def _calcular_sobras_pendentes(client: Client, dia_de_venda_id: UUID | str) -> list[dict]:
    itens_producao = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    vendas_ativas = (
        client.table("vendas")
        .select("id")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        itens_venda = (
            client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )

    decisoes_sobra_usadas = (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .execute()
        .data
    )

    vendidos_por_produto: dict[str, int] = {}
    for item in itens_venda:
        produto_id = item["produto_id"]
        vendidos_por_produto[produto_id] = (
            vendidos_por_produto.get(produto_id, 0) + item["quantidade"]
        )

    disponiveis_por_produto: dict[str, dict] = {}
    for item in itens_producao:
        produto_id = item["produto_id"]
        disponiveis_por_produto[produto_id] = {
            "produto_id": produto_id,
            "nome_produto": item["nome_produto_no_momento"],
            "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
            "quantidade_disponivel": item["quantidade_produzida"],
        }

    for decisao in decisoes_sobra_usadas:
        quantidade_usada = decisao["quantidade_usada_hoje"]
        if quantidade_usada <= 0:
            continue
        produto_id = decisao["produto_id"]
        if produto_id not in disponiveis_por_produto:
            disponiveis_por_produto[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": decisao["nome_produto_no_momento"],
                "url_imagem_produto": decisao.get("url_imagem_produto_no_momento"),
                "quantidade_disponivel": 0,
            }
        disponiveis_por_produto[produto_id]["quantidade_disponivel"] += quantidade_usada

    sobras = []
    for item in disponiveis_por_produto.values():
        quantidade_sobra = item["quantidade_disponivel"] - vendidos_por_produto.get(
            item["produto_id"],
            0,
        )
        if quantidade_sobra <= 0:
            continue
        sobras.append(
            {
                "produto_id": item["produto_id"],
                "nome_produto": item["nome_produto"],
                "url_imagem_produto": item.get("url_imagem_produto"),
                "quantidade_sobra": quantidade_sobra,
                "quantidade_sugerida_para_usar": quantidade_sobra,
            }
        )
    return sorted(sobras, key=lambda item: item["nome_produto"])


def _registrar_decisoes_sobra(
    client: Client,
    *,
    dia_origem: dict,
    dia_destino: dict,
    sobras_pendentes: list[dict],
    decisoes: list[RequisicaoDecisaoSobra],
) -> list[dict]:
    if not decisoes:
        raise BadRequestError("Informe a decisao para cada sobra pendente.")

    sobras_por_produto = {sobra["produto_id"]: sobra for sobra in sobras_pendentes}
    decisoes_por_produto: dict[str, RequisicaoDecisaoSobra] = {}
    for decisao in decisoes:
        produto_id = str(decisao.produto_id)
        if produto_id in decisoes_por_produto:
            raise BadRequestError("Ha decisao de sobra repetida para o mesmo produto.")
        decisoes_por_produto[produto_id] = decisao

    produtos_pendentes = set(sobras_por_produto)
    produtos_decididos = set(decisoes_por_produto)
    produtos_faltando = produtos_pendentes - produtos_decididos
    produtos_extras = produtos_decididos - produtos_pendentes
    if produtos_faltando or produtos_extras:
        raise BadRequestError(
            "As decisoes de sobra precisam corresponder exatamente as sobras pendentes.",
            {
                "produtos_faltando": sorted(produtos_faltando),
                "produtos_sem_sobra_pendente": sorted(produtos_extras),
            },
        )

    linhas = []
    for produto_id, sobra in sobras_por_produto.items():
        decisao = decisoes_por_produto[produto_id]
        quantidade_usada = decisao.quantidade_usada_hoje
        quantidade_sobra = sobra["quantidade_sobra"]
        quantidade_nao_usada = decisao.quantidade_nao_usada_hoje
        if quantidade_nao_usada is None:
            quantidade_nao_usada = quantidade_sobra - quantidade_usada
        if quantidade_nao_usada < 0:
            raise BadRequestError(
                "A quantidade usada hoje nao pode ser maior que a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                },
            )
        if quantidade_usada + quantidade_nao_usada != quantidade_sobra:
            raise BadRequestError(
                "A soma entre sobra usada hoje e nao usada hoje deve fechar a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                    "quantidade_nao_usada_hoje": quantidade_nao_usada,
                },
            )

        linhas.append(
            to_db_payload(
                {
                    "dia_origem_id": dia_origem["id"],
                    "dia_destino_id": dia_destino["id"],
                    "produto_id": produto_id,
                    "nome_produto_no_momento": sobra["nome_produto"],
                    "url_imagem_produto_no_momento": sobra.get("url_imagem_produto"),
                    "quantidade_sobra_origem": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                    "quantidade_nao_usada_hoje": quantidade_nao_usada,
                    "observacoes": decisao.observacoes,
                }
            )
        )

    decisoes_registradas = client.table("decisoes_sobra").insert(linhas).execute().data
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="sobras_decididas",
        titulo="Sobras do dia anterior decididas",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_destino["id"],
        dia_de_venda_id=dia_destino["id"],
        detalhes={
            "dia_origem_id": dia_origem["id"],
            "itens": [
                {
                    "produto_id": decisao["produto_id"],
                    "quantidade_sobra_origem": decisao["quantidade_sobra_origem"],
                    "quantidade_usada_hoje": decisao["quantidade_usada_hoje"],
                    "quantidade_nao_usada_hoje": decisao["quantidade_nao_usada_hoje"],
                }
                for decisao in decisoes_registradas
            ],
        },
    )
    return decisoes_registradas


def _listar_decisoes_sobra_do_destino(client: Client, dia_de_venda_id: UUID | str) -> list[dict]:
    return (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .order("nome_produto_no_momento")
        .execute()
        .data
    )


def _listar_decisoes_sobra_por_origem_destino(
    client: Client,
    *,
    dia_origem_id: UUID | str,
    dia_destino_id: UUID | str,
) -> list[dict]:
    return (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_origem_id", str(dia_origem_id))
        .eq("dia_destino_id", str(dia_destino_id))
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
