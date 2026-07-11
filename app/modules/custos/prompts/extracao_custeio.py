"""Prompt e schema JSON da extracao de custeio (texto, audio, imagem).

Qualquer mudanca aqui altera o contrato com o modelo OpenAI; mantenha o
schema em sincronia com app.modules.custos.assistant.rascunho.
"""

INSTRUCOES_EXTRACAO_CUSTEIO = (
    "Voce e um assistente de custeio para uma pequena padaria familiar. "
    "Transforme texto, audio transcrito, formulario ou imagem de nota/print em um rascunho "
    "estruturado de custo. Nunca invente preco, quantidade, unidade, rendimento, produto ou "
    "ingrediente. Quando algo nao estiver claro, deixe null, marque status PRECISA_REVISAR "
    "ou PENDENTE e gere perguntas_sugeridas. Use somente produto_id presente na sessao ou "
    "um produto existente no catalogo enviado. Diferencie quantidade comprada da quantidade "
    "usada na receita. O backend converte medidas como ml, l, g, kg, copo, xicara, "
    "colher de sopa, colher de cha, prato cheio com equivalencia em gramas, ovo e "
    "cartela de ovos. Se a entrada trouxer medida caseira, mantenha a unidade falada "
    "pelo usuario para que a tela mostre revisao; se houver equivalencia explicita, "
    "preserve a equivalencia na unidade, como 'prato cheio (350 g)' ou "
    "'cartela de 30 ovos'. Respeite a finalidade recebida no input: com finalidade "
    "'receita', preencha apenas receita, preparo, quantidade_usada e unidade_usada; "
    "em imagem de receita, medidas como '250 ml de leite' ou '1/2 copo de oleo' "
    "sao sempre quantidade_usada/unidade_usada, nao quantidade_comprada/unidade_compra; "
    "deixe quantidade_comprada, unidade_compra e preco_total como null, mesmo que a "
    "receita tenha medidas, e nao gere perguntas sobre preco, nota ou compra nessa etapa. "
    "Quando faltarem dados de varios ingredientes, agrupe em uma unica pergunta objetiva. "
    "Com finalidade 'compras', preencha quantidade_comprada, "
    "unidade_compra e preco_total; quando a compra vier por embalagem com tamanho "
    "legivel, preserve o tamanho na unidade_compra em vez de usar apenas 'un' "
    "(ex.: 6 caixas de 1 L => quantidade_comprada 6 e unidade_compra '1l'; "
    "2 pacotes de 100 g => quantidade_comprada 2 e unidade_compra '100g'; "
    "1 garrafa de 900 ml => quantidade_comprada 1 e unidade_compra '900ml'). "
    "Deixe quantidade_usada, unidade_usada, preparo e rendimento como null, salvo se "
    "o usuario trouxer isso explicitamente junto. "
    "Ao ler nota/cupom, compare com o rascunho atual e use o nome do ingrediente "
    "da receita quando for equivalente: 'ovos grandes brancos' deve atualizar 'ovos', "
    "'sal iodado/refinado' deve atualizar 'sal' e 'queijo mussarela ralado' pode "
    "atualizar 'queijo meia cura e/ou mussarela ralado'. Nao crie outro ingrediente "
    "so porque a nota tem marca, tipo, cor, tamanho ou descricao comercial. "
    "Com finalidade 'completo', aceite receita e compras na mesma entrada, mas nunca "
    "copie quantidade usada para quantidade comprada por deducao. Para embalagem normalmente "
    "use aplicacao por_unidade; para gas, "
    "energia e transporte use por_receita quando o usuario informar valor do lote/receita. "
    "Status deve ser CONFIRMADO quando o usuario informou explicitamente, ESTIMADO quando "
    "for uma aproximacao declarada, PENDENTE quando faltar dado e PRECISA_REVISAR quando "
    "a leitura estiver incerta. Retorne somente JSON valido no schema solicitado."
)


def instrucoes_extracao_custeio() -> str:
    return INSTRUCOES_EXTRACAO_CUSTEIO


def formato_json_extracao_custeio() -> dict:
    item_nullable_string = {"type": ["string", "null"]}
    item_nullable_number = {"type": ["number", "null"]}
    return {
        "type": "json_schema",
        "name": "extracao_custeio_padoka",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "rascunho",
                "perguntas_sugeridas",
                "avisos",
                "confianca",
            ],
            "properties": {
                "rascunho": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "produto_id",
                        "receita",
                        "ingredientes",
                        "custos_adicionais",
                        "preparo",
                    ],
                    "properties": {
                        "produto_id": item_nullable_string,
                        "receita": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "nome",
                                "rendimento",
                                "unidade_rendimento",
                                "status",
                                "observacoes",
                            ],
                            "properties": {
                                "nome": item_nullable_string,
                                "rendimento": item_nullable_number,
                                "unidade_rendimento": item_nullable_string,
                                "status": {"type": "string"},
                                "observacoes": item_nullable_string,
                            },
                        },
                        "ingredientes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "insumo_id",
                                    "nome",
                                    "categoria",
                                    "quantidade_comprada",
                                    "unidade_compra",
                                    "preco_total",
                                    "quantidade_usada",
                                    "unidade_usada",
                                    "status",
                                    "observacoes",
                                    "confianca",
                                ],
                                "properties": {
                                    "insumo_id": item_nullable_string,
                                    "nome": item_nullable_string,
                                    "categoria": item_nullable_string,
                                    "quantidade_comprada": item_nullable_number,
                                    "unidade_compra": item_nullable_string,
                                    "preco_total": item_nullable_number,
                                    "quantidade_usada": item_nullable_number,
                                    "unidade_usada": item_nullable_string,
                                    "status": {"type": "string"},
                                    "observacoes": item_nullable_string,
                                    "confianca": item_nullable_number,
                                },
                            },
                        },
                        "custos_adicionais": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "tipo",
                                    "nome",
                                    "valor",
                                    "aplicacao",
                                    "status",
                                    "observacoes",
                                    "confianca",
                                ],
                                "properties": {
                                    "tipo": {"type": "string"},
                                    "nome": item_nullable_string,
                                    "valor": item_nullable_number,
                                    "aplicacao": {"type": "string"},
                                    "status": {"type": "string"},
                                    "observacoes": item_nullable_string,
                                    "confianca": item_nullable_number,
                                },
                            },
                        },
                        "preparo": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "modo_preparo",
                                "tempo_preparo_minutos",
                                "tempo_forno_minutos",
                                "temperatura_forno",
                                "observacoes",
                            ],
                            "properties": {
                                "modo_preparo": item_nullable_string,
                                "tempo_preparo_minutos": item_nullable_number,
                                "tempo_forno_minutos": item_nullable_number,
                                "temperatura_forno": item_nullable_string,
                                "observacoes": item_nullable_string,
                            },
                        },
                    },
                },
                "perguntas_sugeridas": {"type": "array", "items": {"type": "string"}},
                "avisos": {"type": "array", "items": {"type": "string"}},
                "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "strict": True,
    }
