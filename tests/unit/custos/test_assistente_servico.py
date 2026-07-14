from decimal import Decimal
from uuid import UUID

from app.modules.custos import assistente_servico

PRODUTO_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_estado_estima_custo_quando_unidades_sao_incompativeis(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Pao de Queijo",
            "preco_atual": {"preco_venda": "3.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Pao de Queijo", "rendimento": "30", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "calda especial",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                    "status": "CONFIRMADO",
                }
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    # Unidades incompativeis nao travam mais o custeio: o custo sai como
    # estimativa aproximada (1 embalagem inteira) com avisos para o usuario.
    assert estado["pendencias"] == []
    assert estado["situacao"] == "pronto_para_confirmar"
    (calda,) = estado["custo_simulado"]["ingredientes"]
    assert calda["calculo_estimado"] is True
    assert calda["custo_total_estimado"] == "5.00"
    assert estado["custo_simulado"]["calculo_aproximado"] is True
    assert any("embalagem" in aviso for aviso in estado["avisos"])
    assert any("estimativa aproximada" in aviso for aviso in estado["avisos"])


def test_estado_infere_embalagens_comuns_e_equivalencia_explicita(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Pao de Queijo",
            "preco_atual": {"preco_venda": "25.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Pao de Queijo", "rendimento": "30", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "leite integral",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                    "status": "CONFIRMADO",
                },
                {
                    "nome": "oleo",
                    "quantidade_usada": "0.5",
                    "unidade_usada": "copo",
                    "quantidade_comprada": "2",
                    "unidade_compra": "un",
                    "preco_total": "20",
                    "status": "CONFIRMADO",
                },
                {
                    "nome": "queijo ralado parmesao",
                    "quantidade_usada": "1",
                    "unidade_usada": "pacote",
                    "quantidade_comprada": "2",
                    "unidade_compra": "100g",
                    "preco_total": "10",
                    "status": "CONFIRMADO",
                },
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    assert estado["situacao"] == "pronto_para_confirmar"
    assert estado["pendencias"] == []
    leite, oleo, parmesao = estado["custo_simulado"]["ingredientes"]
    assert leite["unidade_compra_calculo"] == "1l"
    assert leite["calculo_estimado"] is True
    assert oleo["unidade_compra_calculo"] == "900ml"
    assert oleo["calculo_estimado"] is True
    assert parmesao["unidade_usada_calculo"] == "g"
    assert parmesao["quantidade_usada_calculo"] == "100"
    assert parmesao["unidade_compra_calculo"] == "100g"


def test_estado_converte_medida_caseira_para_massa_quando_compra_e_kg(monkeypatch):
    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assistente_servico.servico_de_produtos,
        "buscar_produto",
        lambda *args, **kwargs: {
            "id": str(PRODUTO_ID),
            "nome": "Bolo",
            "preco_atual": {"preco_venda": "10.00"},
        },
    )

    estado = assistente_servico._montar_estado_da_sessao(
        {
            "produto_id": str(PRODUTO_ID),
            "receita": {"nome": "Bolo", "rendimento": "10", "status": "CONFIRMADO"},
            "ingredientes": [
                {
                    "nome": "farinha de trigo",
                    "quantidade_usada": "2",
                    "unidade_usada": "xicara",
                    "quantidade_comprada": "1",
                    "unidade_compra": "kg",
                    "preco_total": "5",
                    "status": "CONFIRMADO",
                }
            ],
            "custos_adicionais": [],
        },
        produto_id=PRODUTO_ID,
    )

    assert estado["pendencias"] == []
    (farinha,) = estado["custo_simulado"]["ingredientes"]
    assert farinha["quantidade_usada_calculo"] == "240"
    assert farinha["unidade_usada_calculo"] == "g"
    assert farinha["calculo_estimado"] is True


def test_simulacao_recalcula_custo_de_insumo_com_custo_gravado_em_semantica_antiga(monkeypatch):
    # Linha real do banco: 6 litros de leite por R$ 32,94, mas custo_por_unidade
    # gravado como 5.49 (R$/litro, semantica antiga) em vez de 0.00549 (R$/ml).
    # A conta deve sair do preco pago, nunca do custo gravado.
    insumo_id = UUID("33333333-3333-3333-3333-333333333333")
    monkeypatch.setattr(
        assistente_servico.servico_de_custos,
        "buscar_insumo",
        lambda *args, **kwargs: {
            "id": str(insumo_id),
            "nome": "leite integral",
            "unidade_compra": "l",
            "quantidade_comprada": "6",
            "preco_total": "32.94",
            "custo_por_unidade": "5.490000",
            "status": "CONFIRMADO",
        },
    )

    custo_total, custo_unitario, pendencia, _ = assistente_servico._simular_ingrediente(
        {
            "insumo_id": str(insumo_id),
            "nome": "leite integral",
            "quantidade_usada": "250",
            "unidade_usada": "ml",
        }
    )

    assert pendencia is None
    assert custo_unitario == Decimal("0.005490")
    assert custo_total == Decimal("1.37")


def test_simulacao_usa_custo_gravado_quando_nao_da_para_recalcular(monkeypatch):
    insumo_id = UUID("33333333-3333-3333-3333-333333333333")
    monkeypatch.setattr(
        assistente_servico.servico_de_custos,
        "buscar_insumo",
        lambda *args, **kwargs: {
            "id": str(insumo_id),
            "nome": "ovos",
            "unidade_compra": "un",
            "quantidade_comprada": None,
            "preco_total": None,
            "custo_por_unidade": "0.90",
            "status": "CONFIRMADO",
        },
    )

    custo_total, custo_unitario, pendencia, _ = assistente_servico._simular_ingrediente(
        {
            "insumo_id": str(insumo_id),
            "nome": "ovos",
            "quantidade_usada": "12",
            "unidade_usada": "un",
        }
    )

    assert pendencia is None
    assert custo_unitario == Decimal("0.90")
    assert custo_total == Decimal("10.80")


def test_embalagem_sem_dado_deterministico_usa_equivalencia_da_ia(monkeypatch):
    from app.modules.custos import conversao_ia

    monkeypatch.setattr(
        conversao_ia,
        "_consultar_llm",
        lambda **kwargs: {"quantidade": 500, "unidade": "g", "confianca": 0.9},
    )

    inferencia = assistente_servico._inferir_unidade_da_embalagem_do_ingrediente(
        {
            "nome": "mistura para pao caseiro",
            "unidade_compra": "pacote",
        }
    )

    assert inferencia is not None
    assert inferencia["unidade"] == "500g"
    assert "estimada por IA" in inferencia["descricao"]


def test_consolidar_pendencia_legada_de_unidade_incompativel_nao_vira_compra_generica():
    pendencia = (
        "Ingrediente 1: leite integral: Unidade do ingrediente incompativel "
        "com a unidade de compra."
    )

    resultado = assistente_servico._consolidar_pendencias_para_fase(
        [pendencia],
        {
            "ingredientes": [
                {
                    "nome": "leite integral",
                    "quantidade_usada": "250",
                    "unidade_usada": "ml",
                    "quantidade_comprada": "6",
                    "unidade_compra": "un",
                    "preco_total": "30",
                }
            ]
        },
        fase="coletando_precos",
    )

    assert resultado == [pendencia]


def test_confirmacao_persiste_unidade_de_compra_inferida(monkeypatch):
    capturado = {}
    insumo_id = UUID("22222222-2222-2222-2222-222222222222")

    monkeypatch.setattr(
        assistente_servico,
        "_buscar_insumo_existente_para_ingrediente",
        lambda *args, **kwargs: None,
    )

    def criar_insumo(requisicao, **kwargs):
        capturado["requisicao"] = requisicao
        return {"id": str(insumo_id)}

    monkeypatch.setattr(
        assistente_servico.servico_de_custos,
        "criar_insumo",
        criar_insumo,
    )

    resultado = assistente_servico._resolver_ou_criar_insumo(
        {
            "nome": "leite integral",
            "quantidade_usada": "250",
            "unidade_usada": "ml",
            "quantidade_comprada": "6",
            "unidade_compra": "un",
            "preco_total": "32.94",
            "observacoes": "Cupom mostra leite integral 3% TP 1L.",
            "status": "CONFIRMADO",
        }
    )

    assert resultado == insumo_id
    assert capturado["requisicao"].quantidade_comprada == Decimal("6")
    assert capturado["requisicao"].unidade_compra == "1l"
    assert capturado["requisicao"].preco_total == Decimal("32.94")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.filtros = []

    def select(self, *a, **k):
        return self

    def eq(self, campo, valor):
        self.filtros.append(("eq", campo, valor))
        return self

    def neq(self, campo, valor):
        self.filtros.append(("neq", campo, valor))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class _R:
            pass

        r = _R()
        r.data = self._rows
        return r


class _FakeClient:
    def __init__(self, rows):
        self.query = _FakeQuery(rows)

    def table(self, _nome):
        return self.query


def _preparar_lookup(monkeypatch, rows):
    cliente = _FakeClient(rows)
    monkeypatch.setattr(assistente_servico, "get_supabase_client", lambda: cliente)
    # Passa a sessão bruta adiante para checar QUAL foi escolhida sem tocar no DB.
    monkeypatch.setattr(assistente_servico, "_montar_sessao_saida", lambda sessao: sessao)
    return cliente


def test_sessao_do_produto_prefere_a_confirmada(monkeypatch):
    rows = [
        {"id": "draft", "situacao": "rascunho", "criado_em": "2026-07-16"},
        {"id": "conf", "situacao": "confirmado", "criado_em": "2026-07-15"},
    ]
    cliente = _preparar_lookup(monkeypatch, rows)
    escolhida = assistente_servico.buscar_sessao_do_produto(PRODUTO_ID, usuario_id=PRODUTO_ID)
    assert escolhida["id"] == "conf"
    # Escopo por produto, por usuário e sem as descartadas.
    assert ("eq", "produto_id", str(PRODUTO_ID)) in cliente.query.filtros
    assert ("eq", "usuario_id", str(PRODUTO_ID)) in cliente.query.filtros
    assert ("neq", "situacao", "descartado") in cliente.query.filtros


def test_sessao_do_produto_usa_rascunho_mais_recente_sem_confirmada(monkeypatch):
    rows = [
        {"id": "novo", "situacao": "pronto_para_confirmar", "criado_em": "2026-07-16"},
        {"id": "velho", "situacao": "rascunho", "criado_em": "2026-07-10"},
    ]
    _preparar_lookup(monkeypatch, rows)
    escolhida = assistente_servico.buscar_sessao_do_produto(PRODUTO_ID)
    assert escolhida["id"] == "novo"


def test_sessao_do_produto_sem_sessoes_retorna_none(monkeypatch):
    _preparar_lookup(monkeypatch, [])
    assert assistente_servico.buscar_sessao_do_produto(PRODUTO_ID) is None
