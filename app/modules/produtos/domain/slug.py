from uuid import UUID

from app.shared.slugs import slugify


def criar_slug_unico(
    nome: str,
    *,
    buscar_por_slug,
    ignorar_id: UUID | None = None,
) -> str:
    slug_base = slugify(nome)
    candidato = slug_base
    sufixo = 2
    while True:
        existente = buscar_por_slug(candidato)
        if not existente or (ignorar_id and existente["id"] == str(ignorar_id)):
            return candidato
        candidato = f"{slug_base}-{sufixo}"
        sufixo += 1
