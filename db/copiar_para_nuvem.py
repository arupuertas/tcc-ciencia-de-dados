"""Copia o banco local para o Chroma Cloud com os embeddings já calculados (sem chamar a OpenAI).

Uso: `python db/copiar_para_nuvem.py [--origem ./dados/chroma] [--sem-sessoes]`. Usa upsert:
pode ser repetido sem duplicar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb  # noqa: E402

from simulador.config import segredo_ambiente  # noqa: E402
from simulador.db import LIMITE_DOCUMENTO, Tabela  # noqa: E402
from simulador.esquema import CONFIGURACAO, ESQUEMA  # noqa: E402

LOTE = 100
SO_REGISTROS_DE_USO = {"sessoes", "respostas", "api_uso"}


def _documento_para_nuvem(doc: str | None, vetorial: bool) -> str | None:
    """Comprime registros grandes como o app faz ao gravar."""
    if doc is None or vetorial or len(doc.encode()) <= LIMITE_DOCUMENTO or not doc.startswith("{"):
        return doc
    return Tabela._documento(json.loads(doc))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origem", default="./dados/chroma", help="pasta do banco local")
    ap.add_argument("--sem-sessoes", action="store_true", help="não copia sessões, respostas e registro de custos")
    args = ap.parse_args()

    api_key = segredo_ambiente("CHROMA_API_KEY")
    if not api_key:
        sys.exit("Falta CHROMA_API_KEY nos secrets (.streamlit/secrets.toml) ou no ambiente.")
    destino = chromadb.CloudClient(
        tenant=segredo_ambiente("CHROMA_TENANT"),
        database=segredo_ambiente("CHROMA_DATABASE") or "simulador",
        api_key=api_key,
    )
    origem = chromadb.PersistentClient(path=args.origem)
    existentes = {c.name for c in origem.list_collections()}

    for definicao in ESQUEMA.values():
        if args.sem_sessoes and definicao.nome in SO_REGISTROS_DE_USO:
            continue
        alvo = destino.get_or_create_collection(definicao.nome, configuration=CONFIGURACAO)
        if definicao.nome not in existentes:
            print(f"{definicao.nome:18} criada vazia (não existe no banco local)")
            continue
        fonte = origem.get_collection(definicao.nome)
        total = fonte.count()
        copiados = 0
        while copiados < total:
            r = fonte.get(limit=LOTE, offset=copiados, include=["embeddings", "documents", "metadatas"])
            if not r["ids"]:
                break
            alvo.upsert(
                ids=r["ids"],
                embeddings=r["embeddings"],
                documents=[_documento_para_nuvem(d, definicao.vetorial) for d in r["documents"]],
                metadatas=r["metadatas"],
            )
            copiados += len(r["ids"])
            print(f"\r{definicao.nome:18} {copiados}/{total}", end="", flush=True)
        print(f"\r{definicao.nome:18} {copiados}/{total} · na nuvem: {alvo.count()}")


if __name__ == "__main__":
    main()
