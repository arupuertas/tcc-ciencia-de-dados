"""Isola os testes do banco real.

O `secrets.toml` local aponta para o Chroma Cloud e o Streamlit copia os secrets para o ambiente:
sem isto, os testes gravariam no banco do app. Só `simulador.db` lê as variáveis CHROMA_*.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulador import db  # noqa: E402

_BANCO_REMOTO = {"CHROMA_API_KEY", "CHROMA_TENANT", "CHROMA_DATABASE", "CHROMA_HOST", "CHROMA_PORT", "CHROMA_SSL", "CHROMA_TOKEN"}

_ler = db.segredo_ambiente
db.segredo_ambiente = lambda nome, padrao=None: padrao if nome in _BANCO_REMOTO else _ler(nome, padrao)
db.cliente.cache_clear()


def pytest_sessionstart(session):
    if db.onde_esta_o_banco()[0] != "local":
        raise SystemExit("Os testes estão apontando para um banco remoto; abortado.")
