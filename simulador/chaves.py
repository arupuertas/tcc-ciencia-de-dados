"""Catálogo das chaves de API que o painel permite cadastrar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChaveId = Literal["MARITACA_API_KEY", "OPENAI_API_KEY"]


@dataclass(frozen=True)
class ChaveInfo:
    id: ChaveId
    nome: str
    descricao: str
    grupo: str
    secreta: bool = True
    testavel: bool = True


CHAVES: list[ChaveInfo] = [
    ChaveInfo(
        "MARITACA_API_KEY",
        "Maritaca AI",
        "Modelos Sabiá, treinados para o português e o contexto brasileiro: banca de avaliadores, juiz e "
        "classificador de turno.",
        "Modelos de linguagem",
    ),
    ChaveInfo(
        "OPENAI_API_KEY",
        "OpenAI",
        "Transcrição (Whisper), voz do avaliador (TTS), embeddings da base e leitura de postura (visão). "
        "A Maritaca não oferece esses serviços.",
        "Modelos de linguagem",
    ),
]
