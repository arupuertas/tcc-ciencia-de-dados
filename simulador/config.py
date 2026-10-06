"""Configuração do servidor: `st.secrets`, com variáveis de ambiente como alternativa."""

from __future__ import annotations

import os


def _do_streamlit(nome: str) -> str | None:
    try:
        import streamlit as st  # import tardio: o núcleo não depende do Streamlit

        if nome in st.secrets:
            valor = st.secrets[nome]
            return str(valor) if valor is not None else None
    except Exception:
        return None
    return None


def segredo_ambiente(nome: str, padrao: str | None = None) -> str | None:
    valor = _do_streamlit(nome)
    if valor:
        return valor
    valor = os.environ.get(nome)
    return valor if valor else padrao


def inteiro_ambiente(nome: str, padrao: int) -> int:
    bruto = segredo_ambiente(nome)
    try:
        n = int(float(bruto)) if bruto else padrao
    except ValueError:
        return padrao
    return n if n > 0 else padrao
