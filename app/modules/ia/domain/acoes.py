"""Acoes que a IA pode interpretar a partir de um comando."""

ACAO_REGISTRAR_VENDA = "registrar_venda"
ACAO_REGISTRAR_PRODUCAO = "registrar_producao"
ACAO_CRIAR_PRODUTO = "criar_produto"
ACAO_CRIAR_PRODUTOS = "criar_produtos"
ACAO_ABRIR_DIA_DE_VENDA = "abrir_dia_de_venda"
ACAO_FECHAR_DIA_DE_VENDA = "fechar_dia_de_venda"
ACAO_CANCELAR_VENDA = "cancelar_venda"
ACAO_CANCELAR_ITEM_VENDA = "cancelar_item_venda"
ACAO_DESCONHECIDO = "desconhecido"

ACOES_SUPORTADAS = {
    ACAO_REGISTRAR_VENDA,
    ACAO_REGISTRAR_PRODUCAO,
    ACAO_CRIAR_PRODUTO,
    ACAO_CRIAR_PRODUTOS,
    ACAO_ABRIR_DIA_DE_VENDA,
    ACAO_FECHAR_DIA_DE_VENDA,
    ACAO_CANCELAR_VENDA,
    ACAO_CANCELAR_ITEM_VENDA,
    ACAO_DESCONHECIDO,
}
