"""Orquestracao do seed de vendas para testes de agentes e analytics."""

from datetime import date, timedelta
from decimal import Decimal
from random import Random
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.core.errors import AppError, BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.admin import seed_gerador, seed_repositorio
from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake
from app.modules.auth import servico as servico_de_auth
from app.modules.produtos import servico as servico_de_produtos
from app.modules.produtos.esquemas import RequisicaoCriarProduto, RequisicaoCriarVersaoDePreco
from app.shared.datas import data_operacional_hoje

PRODUTOS_FAKE = [
    ("[Seed] Pao Frances", Decimal("1.20"), Decimal("0.45")),
    ("[Seed] Pao de Queijo", Decimal("4.50"), Decimal("1.40")),
    ("[Seed] Pao Sovado", Decimal("8.90"), Decimal("3.10")),
    ("[Seed] Broa de Milho", Decimal("6.50"), Decimal("2.20")),
    ("[Seed] Rosca Doce", Decimal("7.90"), Decimal("2.70")),
    ("[Seed] Baguete", Decimal("9.50"), Decimal("3.40")),
    ("[Seed] Sonho", Decimal("6.00"), Decimal("2.10")),
    ("[Seed] Croissant", Decimal("12.00"), Decimal("4.80")),
]


def gerar_vendas_fake(
    requisicao: RequisicaoGerarVendasFake,
    *,
    usuario_autenticado: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    """Gera um lote para o usuario escolhido e opcionalmente o persiste.

    ``usuario_id`` foi mantido para chamadas internas antigas. A rota HTTP usa
    ``usuario_autenticado``, que tambem fornece e-mail/nome para a resposta.
    """
    client = get_supabase_client()
    usuario_alvo = _resolver_usuario_alvo(
        client,
        requisicao,
        usuario_autenticado=usuario_autenticado,
        usuario_id_legado=usuario_id,
    )
    alvo_id = UUID(str(usuario_alvo["id"]))
    datas = _resolver_datas(requisicao)
    lote_id = uuid4()
    seed = requisicao.seed if requisicao.seed is not None else uuid4().int % 1_000_000_000
    rng = Random(seed)
    avisos: list[str] = []

    produtos, snapshots = _resolver_produtos_e_snapshots(
        requisicao,
        datas,
        rng,
        avisos,
        usuario_id=alvo_id,
    )
    lote = seed_gerador.montar_lote(
        requisicao=requisicao,
        datas=datas,
        produtos=produtos,
        snapshots=snapshots,
        rng=rng,
        lote_id=lote_id,
        seed=seed,
        usuario_id=alvo_id,
    )
    if requisicao.somente_simular:
        if requisicao.limpar_seed_anterior:
            avisos.append("limpar_seed_anterior foi ignorado porque somente_simular=true.")
        avisos.append("Simulacao concluida: nenhuma venda, dia ou sobra foi gravada.")
    else:
        if requisicao.limpar_seed_anterior:
            removidos = seed_repositorio.limpar_seed_anterior(
                client,
                datas,
                requisicao.marcador,
                usuario_id=alvo_id,
            )
            if removidos:
                avisos.append(f"{removidos} dia(s) seed anterior removido(s) no periodo.")
        seed_repositorio.persistir_lote(client, lote)

    return {
        "lote_id": lote_id,
        "seed": seed,
        "somente_simulacao": requisicao.somente_simular,
        "usuario": {
            "id": alvo_id,
            "email": usuario_alvo["email"],
            "nome": usuario_alvo.get("nome"),
        },
        "periodo_inicio": min(datas),
        "periodo_fim": max(datas),
        "total_dias": len(lote["dias_saida"]),
        "total_vendas": lote["total_vendas"],
        "total_itens_venda": lote["total_itens_venda"],
        "total_unidades_produzidas": lote["total_unidades_produzidas"],
        "total_unidades_vendidas": lote["total_unidades_vendidas"],
        "total_vendas_canceladas": lote["total_vendas_canceladas"],
        "total_unidades_sobra_reaproveitadas": lote["total_unidades_sobra_reaproveitadas"],
        "total_unidades_sobra_descartadas": lote["total_unidades_sobra_descartadas"],
        "total_unidades_sobrando": lote["total_unidades_sobrando"],
        "produtos_usados": list(lote["produtos_usados"].values()),
        "dias": lote["dias_saida"],
        "avisos": avisos,
    }


def _resolver_usuario_alvo(
    client,
    requisicao: RequisicaoGerarVendasFake,
    *,
    usuario_autenticado: dict | None,
    usuario_id_legado: UUID | str | None,
) -> dict:
    if requisicao.usuario_id:
        usuario = servico_de_auth.buscar_linha_usuario(requisicao.usuario_id)
    elif requisicao.usuario_email:
        linhas = (
            client.table("usuarios")
            .select("*")
            .ilike("email", requisicao.usuario_email)
            .limit(2)
            .execute()
            .data
        )
        usuario = linhas[0] if linhas else None
        if not usuario:
            raise NotFoundError("Usuario", requisicao.usuario_email)
    elif requisicao.usuario_nome:
        linhas = (
            client.table("usuarios")
            .select("*")
            .ilike("nome", f"%{requisicao.usuario_nome}%")
            .limit(10)
            .execute()
            .data
        )
        if not linhas:
            raise NotFoundError("Usuario", requisicao.usuario_nome)
        if len(linhas) > 1:
            raise BadRequestError(
                "O nome informado corresponde a mais de um usuario. "
                "Use usuario_id ou usuario_email.",
                {
                    "usuarios_encontrados": [
                        {"id": linha["id"], "email": linha.get("email"), "nome": linha.get("nome")}
                        for linha in linhas
                    ]
                },
            )
        usuario = linhas[0]
    elif usuario_autenticado:
        usuario = usuario_autenticado
    elif usuario_id_legado:
        usuario = servico_de_auth.buscar_linha_usuario(usuario_id_legado)
    else:
        raise BadRequestError("Informe o usuario que recebera a massa de teste.")

    if usuario.get("situacao") != "ativo":
        raise BadRequestError(
            "O usuario escolhido nao esta ativo.",
            {"usuario_id": str(usuario["id"]), "situacao": usuario.get("situacao")},
        )
    return usuario


def _resolver_datas(requisicao: RequisicaoGerarVendasFake) -> list[date]:
    hoje = data_operacional_hoje()
    if requisicao.datas:
        datas = sorted(set(requisicao.datas))
    else:
        if requisicao.data_inicio and requisicao.data_fim:
            inicio, fim = requisicao.data_inicio, requisicao.data_fim
        elif requisicao.data_inicio:
            inicio = requisicao.data_inicio
            fim = min(hoje, inicio + timedelta(days=requisicao.quantidade_dias - 1))
        elif requisicao.data_fim:
            fim = requisicao.data_fim
            inicio = fim - timedelta(days=requisicao.quantidade_dias - 1)
        else:
            fim = hoje - timedelta(days=1)
            inicio = fim - timedelta(days=requisicao.quantidade_dias - 1)
        datas = [inicio + timedelta(days=offset) for offset in range((fim - inicio).days + 1)]

    if not datas:
        raise BadRequestError("Informe ao menos uma data para gerar o historico fake.")
    futuras = [data for data in datas if data > hoje]
    if futuras:
        raise BadRequestError(
            "Nao e possivel gerar vendas fake em datas futuras.",
            {"datas_futuras": [data.isoformat() for data in futuras]},
        )
    if len(datas) > 120:
        raise BadRequestError("Gere no maximo 120 dias por chamada.")
    return datas


def _resolver_produtos_e_snapshots(
    requisicao: RequisicaoGerarVendasFake,
    datas: list[date],
    rng: Random,
    avisos: list[str],
    *,
    usuario_id: UUID,
) -> tuple[list[dict], dict[tuple[str, date], dict]]:
    if requisicao.produto_ids:
        candidatos = [
            servico_de_produtos.buscar_produto(
                produto_id,
                data_preco=min(datas),
                usuario_id=usuario_id,
            )
            for produto_id in requisicao.produto_ids
        ]
    else:
        candidatos = servico_de_produtos.listar_produtos(
            somente_ativos=True,
            data_preco=min(datas),
            usuario_id=usuario_id,
        )

    produtos, snapshots = _filtrar_e_montar_snapshots(candidatos, datas, avisos)
    if produtos:
        for produto in produtos:
            produto["_origem_seed"] = "existente"
        avisos.append(f"Foram priorizados {len(produtos)} produto(s) existente(s) do usuario.")
        return produtos, snapshots

    if requisicao.produto_ids:
        raise BadRequestError(
            "Nenhum dos produtos informados possui preco vigente em todo o periodo."
        )
    if not requisicao.criar_produtos_fake_se_necessario:
        raise BadRequestError(
            "O usuario nao possui produtos com preco vigente e a criacao "
            "de fallback esta desativada."
        )

    quantidade = min(
        len(PRODUTOS_FAKE),
        max(1, min(requisicao.produtos_por_dia_max, max(requisicao.produtos_por_dia_min, 4))),
    )
    if requisicao.somente_simular:
        produtos, snapshots = _produtos_fake_em_memoria(datas, quantidade, rng, usuario_id)
        avisos.append(
            "O usuario nao possui catalogo elegivel; produtos seed foram "
            "simulados sem persistencia."
        )
        return produtos, snapshots

    produtos_fake = _garantir_produtos_fake(datas, quantidade, rng, usuario_id=usuario_id)
    produtos, snapshots = _filtrar_e_montar_snapshots(produtos_fake, datas, avisos)
    if not produtos:
        raise BadRequestError("Nao foi possivel criar produtos seed com preco vigente no periodo.")
    for produto in produtos:
        produto["_origem_seed"] = "seed"
    avisos.append(
        "O usuario nao possuia catalogo elegivel; produtos seed foram criados ou reutilizados."
    )
    return produtos, snapshots


def _filtrar_e_montar_snapshots(
    produtos: list[dict],
    datas: list[date],
    avisos: list[str],
) -> tuple[list[dict], dict[tuple[str, date], dict]]:
    produtos = _deduplicar_produtos(produtos)
    if not produtos:
        return [], {}
    versoes_por_produto = _listar_versoes_de_preco_para_periodo(
        [str(produto["id"]) for produto in produtos],
        min(datas),
        max(datas),
    )
    validos = []
    snapshots: dict[tuple[str, date], dict] = {}
    for produto in produtos:
        produto_id = str(produto["id"])
        versoes = versoes_por_produto.get(produto_id, [])
        precos_por_data = {
            data_venda: _selecionar_preco_vigente(versoes, data_venda) for data_venda in datas
        }
        if any(preco is None for preco in precos_por_data.values()):
            avisos.append(f"Produto {produto['nome']} ignorado por falta de preco no periodo.")
            continue
        validos.append(dict(produto))
        for data_venda, preco in precos_por_data.items():
            snapshots[(produto_id, data_venda)] = {"produto": produto, "preco": preco}
    return validos, snapshots


def _listar_versoes_de_preco_para_periodo(
    produto_ids: list[str],
    inicio: date,
    fim: date,
) -> dict[str, list[dict[str, Any]]]:
    if not produto_ids:
        return {}
    linhas = (
        get_supabase_client()
        .table("versoes_preco_produto")
        .select("*")
        .in_("produto_id", produto_ids)
        .lte("vigente_desde", fim.isoformat())
        .or_(f"vigente_ate.is.null,vigente_ate.gte.{inicio.isoformat()}")
        .order("produto_id")
        .order("vigente_desde")
        .execute()
        .data
    )
    por_produto: dict[str, list[dict[str, Any]]] = {produto_id: [] for produto_id in produto_ids}
    for linha in linhas:
        por_produto.setdefault(str(linha["produto_id"]), []).append(linha)
    return por_produto


def _selecionar_preco_vigente(
    versoes: list[dict[str, Any]],
    data_alvo: date,
) -> dict[str, Any] | None:
    preco_vigente = None
    for versao in versoes:
        vigente_desde = _parse_data_db(versao["vigente_desde"])
        vigente_ate = versao.get("vigente_ate")
        if vigente_desde > data_alvo:
            continue
        if vigente_ate and _parse_data_db(vigente_ate) < data_alvo:
            continue
        if not preco_vigente or vigente_desde >= _parse_data_db(preco_vigente["vigente_desde"]):
            preco_vigente = versao
    return preco_vigente


def _parse_data_db(valor: date | str) -> date:
    return valor if isinstance(valor, date) else date.fromisoformat(valor)


def _garantir_produtos_fake(
    datas: list[date],
    quantidade: int,
    rng: Random,
    *,
    usuario_id: UUID,
) -> list[dict]:
    client = get_supabase_client()
    existentes = (
        client.table("produtos")
        .select("*")
        .like("nome", "[Seed]%")
        .eq("situacao", "ativo")
        .eq("usuario_id", str(usuario_id))
        .execute()
        .data
    )
    por_nome = {produto["nome"]: produto for produto in existentes}
    specs = PRODUTOS_FAKE.copy()
    rng.shuffle(specs)
    produtos = []
    for nome, preco_venda, preco_custo in specs[:quantidade]:
        produto = por_nome.get(nome)
        if produto:
            _garantir_preco_seed(
                produto["id"],
                min(datas),
                preco_venda,
                preco_custo,
                usuario_id=usuario_id,
            )
            produtos.append(
                servico_de_produtos.buscar_produto(
                    UUID(str(produto["id"])),
                    data_preco=min(datas),
                    usuario_id=usuario_id,
                )
            )
            continue
        produtos.append(
            servico_de_produtos.criar_produto(
                RequisicaoCriarProduto(
                    nome=nome,
                    descricao="Produto fake para testes de historico, agentes e analytics.",
                    preco_venda=preco_venda,
                    preco_custo=preco_custo,
                    vigente_desde=min(datas),
                    motivo_preco="Seed analytics",
                ),
                usuario_id=usuario_id,
            )
        )
    return produtos


def _garantir_preco_seed(
    produto_id: UUID | str,
    data_inicio: date,
    preco_venda: Decimal,
    preco_custo: Decimal,
    *,
    usuario_id: UUID,
) -> None:
    try:
        servico_de_produtos.buscar_snapshot_do_produto(
            produto_id,
            data_inicio,
            usuario_id=usuario_id,
        )
    except AppError:
        servico_de_produtos.criar_versao_de_preco(
            UUID(str(produto_id)),
            RequisicaoCriarVersaoDePreco(
                preco_venda=preco_venda,
                preco_custo=preco_custo,
                vigente_desde=data_inicio,
                motivo="Seed analytics retroativo",
            ),
            usuario_id=usuario_id,
        )


def _produtos_fake_em_memoria(
    datas: list[date],
    quantidade: int,
    rng: Random,
    usuario_id: UUID,
) -> tuple[list[dict], dict[tuple[str, date], dict]]:
    specs = PRODUTOS_FAKE.copy()
    rng.shuffle(specs)
    produtos = []
    snapshots = {}
    for nome, preco_venda, preco_custo in specs[:quantidade]:
        produto_id = uuid5(NAMESPACE_URL, f"padoka-seed:{usuario_id}:{nome}")
        preco_id = uuid5(NAMESPACE_URL, f"padoka-seed-preco:{usuario_id}:{nome}:{min(datas)}")
        produto = {
            "id": produto_id,
            "nome": nome,
            "url_imagem_principal": None,
            "_origem_seed": "seed",
        }
        preco = {
            "id": preco_id,
            "produto_id": produto_id,
            "preco_venda": preco_venda,
            "preco_custo": preco_custo,
            "vigente_desde": min(datas),
            "vigente_ate": None,
        }
        produtos.append(produto)
        for data_venda in datas:
            snapshots[(str(produto_id), data_venda)] = {"produto": produto, "preco": preco}
    return produtos, snapshots


def _deduplicar_produtos(produtos: list[dict]) -> list[dict]:
    vistos: set[str] = set()
    saida = []
    for produto in produtos:
        produto_id = str(produto["id"])
        if produto_id not in vistos:
            vistos.add(produto_id)
            saida.append(produto)
    return saida
