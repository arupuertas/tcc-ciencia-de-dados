"""Login do administrador com usuário e senha vindos dos secrets."""

from __future__ import annotations

import hmac

from .config import segredo_ambiente

ADMIN_ID = "admin"


def entrar(usuario: str, senha: str) -> str:
    esperado_usuario = (segredo_ambiente("ADMIN_USUARIO") or "admin").strip().lower()
    esperado_senha = segredo_ambiente("ADMIN_SENHA") or ""
    if not esperado_senha:
        raise ValueError("Defina ADMIN_SENHA nos secrets para liberar o painel.")
    ok_usuario = hmac.compare_digest(usuario.strip().lower().encode(), esperado_usuario.encode())
    ok_senha = hmac.compare_digest(senha.encode(), esperado_senha.encode())
    if not (ok_usuario and ok_senha):
        raise ValueError("Usuário ou senha inválidos.")
    return ADMIN_ID


def sou_admin(user_id: str | None) -> bool:
    return user_id == ADMIN_ID
