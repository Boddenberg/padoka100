from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel

PAPEIS_VALIDOS = "^(usuario|administrador|dono)$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UsuarioSaida(ApiModel):
    id: UUID
    email: str = Field(pattern=EMAIL_PATTERN)
    nome: str | None = None
    foto_url: str | None = None
    data_nascimento: date | None = None
    telefone: str | None = None
    papel: str
    situacao: str
    criado_em: datetime
    atualizado_em: datetime


class RequisicaoRegistrarUsuario(ApiModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    senha: str = Field(min_length=8, max_length=128)
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    foto_url: str | None = None
    data_nascimento: date | None = None
    telefone: str | None = Field(default=None, max_length=40)


class RequisicaoLogin(ApiModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    senha: str = Field(min_length=1, max_length=128)


class RespostaLogin(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: datetime
    usuario: UsuarioSaida


class RequisicaoAtualizarPerfil(ApiModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    foto_url: str | None = None
    data_nascimento: date | None = None
    telefone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)


class RequisicaoTrocarSenha(ApiModel):
    senha_atual: str = Field(min_length=1, max_length=128)
    nova_senha: str = Field(min_length=8, max_length=128)


class RequisicaoAtualizarPapel(ApiModel):
    papel: str = Field(pattern=PAPEIS_VALIDOS)


class SessaoAutenticada(ApiModel):
    usuario: UsuarioSaida
    sessao_id: UUID | None = None
    via_api_key: bool = False
