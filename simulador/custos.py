"""Tabela de preços das APIs usadas pelo simulador (valores em dólar)."""

from __future__ import annotations

from .modelos import MODELOS

PROVEDORES: dict[str, dict[str, str]] = {
    "maritaca": {
        "nome": "Maritaca AI",
        "descricao": "Modelos Sabiá: banca de avaliadores, juiz e classificador de turno.",
    },
    "openai": {
        "nome": "OpenAI",
        "descricao": "Transcrição (Whisper), voz do avaliador (TTS), leitura de postura (visão) e embeddings da base.",
    },
}

_TOKENS = {"text-embedding-3-small": (0.02, 0)}  # os modelos de texto vêm do catálogo
WHISPER_POR_MINUTO = 0.006
TTS_POR_MIL_CARACTERES = 0.015


def custo_tokens(modelo: str, entrada: int, saida: int) -> float:
    preco = _TOKENS.get(modelo)
    if preco is None:
        cat = next((m for m in MODELOS if m.modelo == modelo or m.id == modelo), None)
        preco = (cat.preco_entrada, cat.preco_saida) if cat else None
    if not preco:
        return 0.0
    return (entrada * preco[0] + saida * preco[1]) / 1_000_000


def custo_whisper(segundos: float) -> float:
    return (segundos / 60) * WHISPER_POR_MINUTO


def custo_tts(caracteres: int) -> float:
    return (caracteres / 1000) * TTS_POR_MIL_CARACTERES


def formatar_usd(valor: float) -> str:
    if valor >= 1:
        return f"US$ {valor:.2f}"
    return f"US$ {valor:.3f}" if valor >= 0.01 else f"US$ {valor:.4f}"


def formatar_duracao(segundos: float | None) -> str:
    if segundos is None:
        return "-"
    m, s = int(segundos // 60), int(round(segundos % 60))
    return f"{m} min {s:02d}s" if m > 0 else f"{s}s"
