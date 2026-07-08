import base64
import hashlib
import secrets
from secrets import compare_digest

ITERACOES_SENHA = 210_000
TAMANHO_SALT = 16


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def gerar_hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(TAMANHO_SALT)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, ITERACOES_SENHA)
    return "pbkdf2_sha256${}${}${}".format(
        ITERACOES_SENHA,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes, salt_b64, digest_b64 = senha_hash.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        digest_esperado = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, int(iteracoes))
        return compare_digest(digest, digest_esperado)
    except (ValueError, TypeError):
        return False


def gerar_token_acesso() -> str:
    return secrets.token_urlsafe(48)


def gerar_hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
