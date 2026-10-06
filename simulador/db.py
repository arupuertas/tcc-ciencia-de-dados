"""Acesso ao ChromaDB: Chroma Cloud, servidor próprio ou pasta local, conforme os secrets.

`Tabela` guarda registros JSON; `Vetores`, embeddings. As bases `material()` e `gabaritos()` são
separadas para o gabarito de uma pergunta nunca aparecer na avaliação de outra.
"""

from __future__ import annotations

import base64
import json
import uuid
import zlib
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import chromadb

from .config import segredo_ambiente
from .esquema import CONFIGURACAO, DIMENSAO_REGISTRO, ESQUEMA, Colecao

Registro = dict[str, Any]
Where = dict[str, Any]

_EMBED_REGISTRO = [1.0] * DIMENSAO_REGISTRO

LIMITE_DOCUMENTO = 12 * 1024  # folga sob o limite de 16 KiB por documento do Chroma Cloud
PREFIXO_COMPRIMIDO = "z:"  # JSON comprimido (zlib + base64); JSON puro sempre começa com "{"
# O Chroma Cloud corta cada `get` em 300 registros, sem avisar, e limita os lotes de escrita.
LOTE_LEITURA = 300
LOTE_ESCRITA = 100


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def para_ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def novo_id() -> str:
    return str(uuid.uuid4())


@lru_cache(maxsize=1)
def cliente():
    api_key = segredo_ambiente("CHROMA_API_KEY")
    if api_key:
        return chromadb.CloudClient(
            tenant=segredo_ambiente("CHROMA_TENANT"),
            database=segredo_ambiente("CHROMA_DATABASE") or "simulador",
            api_key=api_key,
        )
    host = segredo_ambiente("CHROMA_HOST")
    if host:
        return chromadb.HttpClient(
            host=host,
            port=int(segredo_ambiente("CHROMA_PORT") or 8000),
            ssl=(segredo_ambiente("CHROMA_SSL") or "false").lower() == "true",
            headers={"X-Chroma-Token": t} if (t := segredo_ambiente("CHROMA_TOKEN")) else None,
        )
    return chromadb.PersistentClient(path=segredo_ambiente("CHROMA_PATH") or "./dados/chroma")


def onde_esta_o_banco() -> tuple[str, str, bool]:
    """(tipo, descrição, persistente?). A pasta local some a cada reinício do Streamlit Cloud."""
    if segredo_ambiente("CHROMA_API_KEY"):
        base = segredo_ambiente("CHROMA_DATABASE") or "simulador"
        return "cloud", f"Chroma Cloud · base {base}", True
    if host := segredo_ambiente("CHROMA_HOST"):
        return "servidor", f"Servidor Chroma em {host}", True
    caminho = segredo_ambiente("CHROMA_PATH") or "./dados/chroma"
    return "local", f"Pasta local {caminho}", False


def onde(*condicoes: Where | None, **iguais) -> Where | None:
    """Filtro Chroma: igualdades por kwargs e condições prontas, unidas com $and."""
    partes: list[Where] = [c for c in condicoes if c]
    for k, v in iguais.items():
        partes.append({k: "" if v is None else v})
    if not partes:
        return None
    return partes[0] if len(partes) == 1 else {"$and": partes}


class Tabela:
    def __init__(self, nome: str):
        self.definicao: Colecao = ESQUEMA[nome]
        self._col = None

    @property
    def col(self):
        if self._col is None:
            self._col = cliente().get_or_create_collection(self.definicao.nome, configuration=CONFIGURACAO)
        return self._col

    def _metadata(self, registro: Registro) -> dict:
        meta: dict = {}
        for campo, tipo in self.definicao.metadados.items():
            if campo.endswith("_ts") and campo not in registro:
                valor = para_ts(registro.get(campo[:-3] if campo[:-3] in registro else campo.replace("_ts", "_at")))
            else:
                valor = registro.get(campo)
            if valor is None:
                if tipo == "str":
                    meta[campo] = ""
                continue
            if tipo == "str":
                meta[campo] = str(valor)
            elif tipo == "int":
                meta[campo] = int(valor)
            elif tipo == "float":
                meta[campo] = float(valor)
            elif tipo == "bool":
                meta[campo] = bool(valor)
        if not meta:
            meta["_"] = 1  # o Chroma exige metadata não vazia quando informada
        return meta

    @staticmethod
    def _documento(registro: Registro) -> str:
        texto = json.dumps(registro, ensure_ascii=False, default=str)
        if len(texto.encode()) <= LIMITE_DOCUMENTO:
            return texto
        # O Chroma Cloud recusa documentos acima de 16 KiB; a ata de uma resposta longa passa disso.
        return PREFIXO_COMPRIMIDO + base64.b64encode(zlib.compress(texto.encode(), 9)).decode()

    @staticmethod
    def _registro(documento: str | None) -> Registro:
        if not documento:
            return {}
        if documento.startswith(PREFIXO_COMPRIMIDO):
            documento = zlib.decompress(base64.b64decode(documento[len(PREFIXO_COMPRIMIDO):])).decode()
        return json.loads(documento)

    def inserir(self, registro: Registro, id: str | None = None) -> Registro:
        r = dict(registro)
        r["id"] = id or r.get("id") or novo_id()
        r.setdefault("created_at", agora_iso())
        self.col.add(ids=[r["id"]], embeddings=[_EMBED_REGISTRO], documents=[self._documento(r)], metadatas=[self._metadata(r)])
        return r

    def salvar(self, registro: Registro) -> Registro:
        """Upsert pelo id."""
        r = dict(registro)
        if not r.get("id"):
            raise ValueError("Registro sem id.")
        r.setdefault("created_at", agora_iso())
        self.col.upsert(ids=[r["id"]], embeddings=[_EMBED_REGISTRO], documents=[self._documento(r)], metadatas=[self._metadata(r)])
        return r

    def salvar_varios(self, registros: list[Registro]) -> list[Registro]:
        if not registros:
            return []
        rs = []
        for reg in registros:
            r = dict(reg)
            r["id"] = r.get("id") or novo_id()
            r.setdefault("created_at", agora_iso())
            rs.append(r)
        for i in range(0, len(rs), LOTE_ESCRITA):
            lote = rs[i : i + LOTE_ESCRITA]
            self.col.upsert(
                ids=[r["id"] for r in lote],
                embeddings=[_EMBED_REGISTRO] * len(lote),
                documents=[self._documento(r) for r in lote],
                metadatas=[self._metadata(r) for r in lote],
            )
        return rs

    def atualizar(self, id: str, campos: Registro) -> Registro | None:
        atual = self.obter(id)
        if atual is None:
            return None
        atual.update(campos)
        return self.salvar(atual)

    def atualizar_onde(self, where: Where | None, campos: Registro) -> int:
        itens = self.listar(where)
        for r in itens:
            r.update(campos)
        self.salvar_varios(itens)
        return len(itens)

    def remover(self, ids: list[str] | str) -> None:
        ids = [ids] if isinstance(ids, str) else list(ids)
        for i in range(0, len(ids), LOTE_ESCRITA):
            self.col.delete(ids=ids[i : i + LOTE_ESCRITA])

    def remover_onde(self, where: Where | None) -> None:
        if where is None:
            self.remover(self.ids())
        else:
            self.col.delete(where=where)

    def _paginas(self, where: Where | None, include: list[str], ate: int | None = None):
        """Lê em páginas até vir uma vazia, sem depender do teto de registros por `get` do servidor."""
        lidos = 0
        while ate is None or lidos < ate:
            kwargs = {"include": include, "limit": LOTE_LEITURA, "offset": lidos}
            if where:
                kwargs["where"] = where
            res = self.col.get(**kwargs)
            n = len(res.get("ids") or [])
            if n == 0:
                return
            yield res
            lidos += n

    def ids(self, where: Where | None = None) -> list[str]:
        return [i for res in self._paginas(where, []) for i in res["ids"]]

    def metadados(self, where: Where | None = None) -> list[dict]:
        return [m or {} for res in self._paginas(where, ["metadatas"]) for m in (res.get("metadatas") or [])]

    def obter(self, id: str) -> Registro | None:
        res = self.col.get(ids=[id], include=["documents"])
        docs = res.get("documents") or []
        return self._registro(docs[0]) if docs else None

    def obter_varios(self, ids: list[str]) -> dict[str, Registro]:
        ids = [i for i in dict.fromkeys(ids) if i]
        saida: dict[str, Registro] = {}
        for i in range(0, len(ids), LOTE_LEITURA):
            res = self.col.get(ids=ids[i : i + LOTE_LEITURA], include=["documents"])
            for doc in res.get("documents") or []:
                r = self._registro(doc)
                saida[r["id"]] = r
        return saida

    def listar(self, where: Where | None = None, *, ordenar: str | None = None, desc: bool = False, limite: int | None = None) -> list[Registro]:
        # Sem ordenação dá para parar no limite; com ordenação é preciso ler tudo.
        ate = limite if limite and not ordenar else None
        itens = [self._registro(d) for res in self._paginas(where, ["documents"], ate) for d in (res.get("documents") or [])]
        if ordenar:
            itens.sort(key=lambda r: (r.get(ordenar) is None, r.get(ordenar) if r.get(ordenar) is not None else ""), reverse=desc)
        return itens[:limite] if limite else itens

    def contar(self, where: Where | None = None) -> int:
        if where is None:
            return self.col.count()
        return len(self.ids(where))


class Vetores(Tabela):
    def adicionar(self, registros: list[Registro], embeddings: list[list[float]], textos: list[str]) -> None:
        if not registros:
            return
        for i in range(0, len(registros), LOTE_ESCRITA):
            fatia = slice(i, i + LOTE_ESCRITA)
            self.col.upsert(
                ids=[r["id"] for r in registros[fatia]],
                embeddings=embeddings[fatia],
                documents=textos[fatia],
                metadatas=[self._metadata(r) for r in registros[fatia]],
            )

    def buscar(self, embedding: list[float], where: Where | None = None, n: int = 5) -> list[str]:
        if self.col.count() == 0:
            return []
        n = max(1, min(n, self.col.count()))
        kwargs = {"query_embeddings": [embedding], "n_results": n, "include": ["documents"]}
        if where:
            kwargs["where"] = where
        res = self.col.query(**kwargs)
        docs = res.get("documents") or [[]]
        return list(docs[0])


def T(nome: str) -> Tabela:
    return Tabela(nome)


def material() -> Vetores:
    """Base de material: a única lida durante a prova."""
    return Vetores("material_chunks")


def gabaritos() -> Vetores:
    """Base de gabaritos: nunca lida durante a prova."""
    return Vetores("gabarito_chunks")
