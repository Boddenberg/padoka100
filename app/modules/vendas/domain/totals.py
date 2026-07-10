from datetime import date
from decimal import Decimal
from uuid import UUID

from app.infra.supabase.payload import to_db_payload
from app.modules.produtos import public as produtos_public


def montar_dados_item_vendido(
    venda_id: str,
    dia_de_venda: dict,
    produto_id: UUID,
    quantidade: int,
) -> dict:
    data_venda = date.fromisoformat(dia_de_venda["data_venda"])
    snapshot = produtos_public.buscar_snapshot_do_produto(produto_id, data_venda)
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    preco_venda = Decimal(str(preco["preco_venda"]))
    preco_custo = Decimal(str(preco["preco_custo"]))
    return to_db_payload(
        {
            "venda_id": venda_id,
            "dia_de_venda_id": dia_de_venda["id"],
            "produto_id": produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco_venda,
            "preco_custo_unitario_no_momento": preco_custo,
            "quantidade": quantidade,
            "valor_total_venda": preco_venda * quantidade,
            "valor_total_custo": preco_custo * quantidade,
        }
    )
