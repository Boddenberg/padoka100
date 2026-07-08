import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.custos.esquemas import (
    RequisicaoAtualizarInsumo,
    RequisicaoCriarCustoAdicional,
    RequisicaoCriarInsumo,
    RequisicaoCriarReceita,
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

STATUS_ORDEM = {
    "CONFIRMADO": 0,
    "ESTIMADO": 1,
    "PENDENTE": 2,
    "PRECISA_REVISAR": 3,
}


def listar_insumos() -> list[dict]:
    client = get_supabase_client()
    return _executar_lista_opcional(client.table("insumos").select("*").order("nome"))


def criar_insumo(requisicao: RequisicaoCriarInsumo) -> dict:
    client = get_supabase_client()
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
                    **requisicao.model_dump(),
                    "unidade_compra": _normalizar_unidade(requisicao.unidade_compra),
                    "custo_por_unidade": custo_por_unidade,
                }
            )
        )
        .execute()
        .data[0]
    )
    return insumo


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

    return (
        client.table("insumos")
        .update(to_db_payload(dados))
        .eq("id", str(insumo_id))
        .execute()
        .data[0]
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
    return insumo


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


def calcular_custo_do_produto(produto_id: UUID, receita_id: UUID | None = None) -> dict:
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
            "ingredientes": [],
            "custos_adicionais": [],
            "pendencias": ["Nenhuma receita cadastrada para o produto."],
        }

    ingredientes = receita["ingredientes"]
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
        "ingredientes": ingredientes,
        "custos_adicionais": custos_adicionais,
        "pendencias": pendencias,
    }


def _montar_linha_ingrediente(receita_id: UUID | str, ingrediente) -> dict:
    insumo = buscar_insumo(ingrediente.insumo_id) if ingrediente.insumo_id else None
    custo_unitario = None
    custo_total = None
    nome = ingrediente.nome
    status = ingrediente.status
    if insumo:
        nome = insumo["nome"]
        custo_unitario = Decimal(str(insumo["custo_por_unidade"]))
        custo_total = _calcular_custo_ingrediente(
            custo_unitario,
            ingrediente.quantidade_usada,
            ingrediente.unidade,
            insumo["unidade_compra"],
        )
        status = _consolidar_status([status, insumo["status"]])
    return to_db_payload(
        {
            "receita_id": receita_id,
            "insumo_id": ingrediente.insumo_id,
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


def _resolver_receita(produto_id: UUID, receita_id: UUID | None) -> dict | None:
    if receita_id:
        receita = buscar_receita(receita_id)
        if receita["produto_id"] != str(produto_id):
            raise BadRequestError("A receita informada nao pertence ao produto.")
        return receita
    receitas = listar_receitas_do_produto(produto_id)
    return receitas[0] if receitas else None


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
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _resolver_unidade_com_equivalencia_informada(
    unidade_normalizada: str,
) -> tuple[str, Decimal] | None:
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
    if not statuses:
        return "PENDENTE"
    return max(statuses, key=lambda status: STATUS_ORDEM.get(status, 0))


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
