"""Inicio do dia operacional de venda.

Orquestra: localizar dia atual/anterior, calcular e decidir sobras do dia
anterior, criar o novo dia e fechar o anterior quando aplicavel. Todo o calculo
de sobra vive em ``domain.sobras``; aqui fica a coordenacao com o banco.
"""

from datetime import date
from uuid import UUID

from app.core.errors import BadRequestError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.payload import first_or_none, to_db_payload
from app.modules.dias_de_venda import servico as servico_dias
from app.modules.dias_de_venda.domain.regras_dia import (
    dia_parece_seed_analytics,
    requisicao_indica_nova_abertura,
)
from app.modules.dias_de_venda.domain.sobras import (
    calcular_sobras_pendentes,
    montar_linhas_decisoes_sobra,
    somar_sobras_ja_decididas_por_produto,
)
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCriarDiaDeVenda,
    RequisicaoFecharDiaDeVenda,
    RequisicaoIniciarDiaDeVenda,
)
from app.shared.datas import data_operacional_hoje, validar_data_nao_futura
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from supabase import Client


def iniciar_dia_de_venda(requisicao: RequisicaoIniciarDiaDeVenda) -> dict:
    client = get_supabase_client()
    data_venda = requisicao.data_venda or data_operacional_hoje()
    validar_data_nao_futura(data_venda, campo="data_venda")

    dia_atual_existente = _buscar_dia_aberto_por_data(client, data_venda)
    criar_nova_abertura = requisicao.criar_nova_abertura or requisicao_indica_nova_abertura(
        requisicao,
        dia_atual_existente=dia_atual_existente,
    )
    dia_atual = None if criar_nova_abertura else dia_atual_existente

    dia_anterior = _buscar_dia_aberto_anterior(client, data_venda)
    if dia_anterior:
        sobras_pendentes = _calcular_sobras_pendentes(client, dia_anterior["id"])
    else:
        dia_anterior, sobras_pendentes = _buscar_dia_fechado_anterior_com_sobra_pendente(
            client,
            data_venda,
        )

    if not dia_anterior:
        return _responder_sem_dia_anterior(
            client,
            requisicao,
            data_venda,
            dia_atual=dia_atual,
            dia_atual_existente=dia_atual_existente,
            criar_nova_abertura=criar_nova_abertura,
        )

    if sobras_pendentes:
        resposta_ou_estado = _decidir_sobras_do_dia_anterior(
            client,
            requisicao,
            data_venda,
            dia_atual=dia_atual,
            dia_anterior=dia_anterior,
            sobras_pendentes=sobras_pendentes,
        )
        if "acao" in resposta_ou_estado:
            return resposta_ou_estado
        dia_atual = resposta_ou_estado["dia_atual"]
        decisoes_sobra = resposta_ou_estado["decisoes_sobra"]
    else:
        if requisicao.decisoes_sobra:
            raise BadRequestError("O dia anterior nao tem sobra pendente.")
        decisoes_sobra = []
        dia_atual = _garantir_dia_atual(client, requisicao, data_venda, dia_atual, dia_anterior)

    return _finalizar_dia_iniciado(
        requisicao,
        data_venda,
        dia_atual=dia_atual,
        dia_anterior=dia_anterior,
        decisoes_sobra=decisoes_sobra,
    )


def _responder_sem_dia_anterior(
    client: Client,
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    *,
    dia_atual: dict | None,
    dia_atual_existente: dict | None,
    criar_nova_abertura: bool,
) -> dict:
    if dia_atual:
        _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)
        decisoes_destino = servico_dias.listar_decisoes_sobra_do_destino(client, dia_atual["id"])
        return {
            "acao": "dia_atual_aberto",
            "mensagem": "O dia de venda de hoje ja esta aberto.",
            "data_venda": data_venda,
            "dia_de_venda": servico_dias.buscar_dia_de_venda(UUID(dia_atual["id"])),
            "dia_anterior": None,
            "sobras_pendentes": [],
            "decisoes_sobra": decisoes_destino,
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


def _decidir_sobras_do_dia_anterior(
    client: Client,
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    *,
    dia_atual: dict | None,
    dia_anterior: dict,
    sobras_pendentes: list[dict],
) -> dict:
    """Retorna ou uma resposta 'decidir_sobras' (contem 'acao') ou o estado
    resolvido {'dia_atual', 'decisoes_sobra'} para seguir o fluxo."""
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
            "dia_de_venda": (
                servico_dias.buscar_dia_de_venda(UUID(dia_atual["id"])) if dia_atual else None
            ),
            "dia_anterior": servico_dias.anexar_itens_producao(client, dia_anterior),
            "sobras_pendentes": sobras_pendentes,
            "decisoes_sobra": [],
        }

    dia_atual = _garantir_dia_atual(client, requisicao, data_venda, dia_atual, dia_anterior)
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
    return {"dia_atual": dia_atual, "decisoes_sobra": decisoes_sobra}


def _garantir_dia_atual(
    client: Client,
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    dia_atual: dict | None,
    dia_anterior: dict | None,
) -> dict:
    if not dia_atual:
        return _criar_dia_de_venda_para_inicio(requisicao, data_venda, dia_anterior)
    _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)
    return dia_atual


def _finalizar_dia_iniciado(
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    *,
    dia_atual: dict,
    dia_anterior: dict,
    decisoes_sobra: list[dict],
) -> dict:
    if dia_anterior["situacao"] == "fechado":
        dia_anterior_saida = servico_dias.buscar_dia_de_venda(UUID(dia_anterior["id"]))
        mensagem = "Novo dia iniciado com sobras do dia anterior."
    else:
        dia_anterior_saida = servico_dias.fechar_dia_de_venda(
            UUID(dia_anterior["id"]),
            RequisicaoFecharDiaDeVenda(observacoes=requisicao.observacoes_fechamento_dia_anterior),
        )
        mensagem = "Dia anterior fechado e novo dia iniciado."

    return {
        "acao": "dia_iniciado",
        "mensagem": mensagem,
        "data_venda": data_venda,
        "dia_de_venda": servico_dias.buscar_dia_de_venda(UUID(dia_atual["id"])),
        "dia_anterior": dia_anterior_saida,
        "sobras_pendentes": [],
        "decisoes_sobra": decisoes_sobra,
    }


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
    if dia and dia_parece_seed_analytics(dia):
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
    if not dia or dia_parece_seed_analytics(dia):
        return None, []
    sobras_pendentes = _calcular_sobras_pendentes(client, dia["id"])
    if not sobras_pendentes:
        return None, []
    return dia, sobras_pendentes


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

    return servico_dias.criar_dia_de_venda(
        RequisicaoCriarDiaDeVenda(
            data_venda=data_venda,
            local_id=local_id,
            nome_local=nome_local,
            observacoes=requisicao.observacoes,
            itens_producao=requisicao.itens_producao,
        )
    )


def _salvar_itens_producao_informados(dia_de_venda_id: UUID, itens_producao) -> None:
    for item in itens_producao:
        servico_dias.salvar_item_producao(dia_de_venda_id, item)


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
            client.table("itens_venda").select("*").in_("venda_id", venda_ids).execute().data
        )
    decisoes_sobra_usadas = (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    sobras_ja_decididas = _somar_sobras_ja_decididas_por_produto(client, dia_de_venda_id)
    return calcular_sobras_pendentes(
        itens_producao,
        itens_venda,
        decisoes_sobra_usadas,
        sobras_ja_decididas,
    )


def _somar_sobras_ja_decididas_por_produto(
    client: Client,
    dia_de_venda_id: UUID | str,
) -> dict[str, int]:
    decisoes_sobra_origem = (
        client.table("decisoes_sobra")
        .select("produto_id, quantidade_sobra_origem")
        .eq("dia_origem_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    return somar_sobras_ja_decididas_por_produto(decisoes_sobra_origem)


def _registrar_decisoes_sobra(
    client: Client,
    *,
    dia_origem: dict,
    dia_destino: dict,
    sobras_pendentes: list[dict],
    decisoes: list,
) -> list[dict]:
    linhas = montar_linhas_decisoes_sobra(
        dia_origem=dia_origem,
        dia_destino=dia_destino,
        sobras_pendentes=sobras_pendentes,
        decisoes=decisoes,
    )
    decisoes_registradas = (
        client.table("decisoes_sobra")
        .insert([to_db_payload(linha) for linha in linhas])
        .execute()
        .data
    )
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
