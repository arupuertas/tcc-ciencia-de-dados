"""Coleções do ChromaDB: nome, campos filtráveis (metadata) e se é vetorial. Campos dos registros em `db/ESQUEMA.md`.

Registros guardam o JSON em `document` e um embedding fixo `[1.0]`. As coleções vetoriais usam
text-embedding-3-small (1536 dimensões, cosseno).
"""

from __future__ import annotations

from dataclasses import dataclass, field

DIMENSAO_REGISTRO = 1
CONFIGURACAO = {"hnsw": {"space": "cosine"}}


@dataclass(frozen=True)
class Colecao:
    nome: str
    descricao: str
    metadados: dict[str, str] = field(default_factory=dict)  # campo -> "str" | "int" | "float" | "bool"
    vetorial: bool = False


ESQUEMA: dict[str, Colecao] = {
    c.nome: c
    for c in [
        Colecao("concursos", "Concursos disponíveis para simulação.", {"nome": "str", "ativo": "bool", "created_ts": "float"}),
        Colecao(
            "perguntas",
            "Banco de perguntas por concurso.",
            {"concurso_id": "str", "grupo": "int", "sequencia": "str", "ordem": "int", "origem_uid": "str", "materia": "str"},
        ),
        Colecao(
            "sessoes",
            "Provas simuladas.",
            {"concurso_id": "str", "status": "str", "ip_hash": "str", "grupo": "int", "created_ts": "float", "ultimo_sinal_ts": "float"},
        ),
        Colecao("respostas", "Respostas avaliadas (id = `<sessao_id>:<ordem>`).", {"sessao_id": "str", "pergunta_id": "str", "ordem": "int"}),
        Colecao("documentos", "Arquivos de estudo enviados no painel.", {"concurso_id": "str", "nome": "str", "status": "str", "created_ts": "float"}),
        Colecao("material_chunks", "Base de material: a única lida durante a prova.", {"documento_id": "str", "concurso_id": "str", "indice": "int"}, vetorial=True),
        Colecao("gabarito_chunks", "Base de gabaritos: só para a busca do painel.", {"pergunta_id": "str", "concurso_id": "str", "indice": "int"}, vetorial=True),
        Colecao("configuracoes", "Configurações do painel (id = chave)."),
        Colecao("segredos", "Chaves de API cifradas (id = nome da chave)."),
        Colecao("api_uso", "Consumo de cada chamada às APIs.", {"provedor": "str", "operacao": "str", "sessao_id": "str", "created_ts": "float"}),
    ]
}


def inicializar(cliente) -> list[str]:
    for c in ESQUEMA.values():
        cliente.get_or_create_collection(c.nome, configuration=CONFIGURACAO)
    return list(ESQUEMA)
