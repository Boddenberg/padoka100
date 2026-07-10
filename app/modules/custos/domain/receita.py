"""Regras puras de consolidacao de custo de receita."""

from decimal import Decimal


def custos_incluidos(
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


def listar_pendencias(
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
