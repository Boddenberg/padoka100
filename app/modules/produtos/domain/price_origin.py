def normalizar_origem_preco(
    origem: str | None,
    gerado_por_ia: bool | None = None,
) -> tuple[str, bool]:
    origem_normalizada = "ia" if gerado_por_ia else (origem or "manual")
    return origem_normalizada, origem_normalizada == "ia"
