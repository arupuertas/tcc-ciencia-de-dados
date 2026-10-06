"""Detecção de vícios de linguagem em transcrições de prova oral (puro, sem I/O)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

ViciosContagem = dict[str, int]

_LETRA = r"[^\W\d_]"
_RETICENCIAS = r"\s*(?:\.{2,}|…)"
_PAUSA = rf"(?=\s*,|{_RETICENCIAS})"  # seguido de vírgula ou reticências
_PERGUNTA = r"(?=\s*\?)"

# A forma mais longa vem antes. Palavras comuns só contam como muleta: "tipo penal", "bom dia" e
# "é certo que" ficam de fora.
_VICIOS: list[tuple[str, list[str]]] = [
    ("né", ["né"]),
    ("tipo", ["tipo assim", rf"tipo{_PAUSA}"]),
    ("então", ["então"]),
    ("assim", ["assim"]),
    ("aí", ["aí"]),
    # O Whisper escreve a hesitação como "é..." ou "é, é"; o verbo "é" solto não conta.
    (
        "é... / hum",
        ["é{2,}", "e{3,}", "[eé]+h+", rf"é(?={_RETICENCIAS}|,?\s+é(?!{_LETRA}))", rf"ah+(?={_RETICENCIAS})",
         "aham", "ahã", "uhum", "hum+", "hm+", "uhm+", "ahn+", "hã+"],
    ),
    ("deixa eu ver", ["deixa eu ver", "deixa eu pensar", "deixe-me ver", "deixa-me ver"]),
    ("ok", ["okay", "ok"]),
    ("certo?", [rf"certo{_PERGUNTA}"]),
    ("entende?", [rf"(?:entendeu|entende|sabe){_PERGUNTA}"]),
    ("digamos", ["digamos", "vamos dizer"]),
    ("na verdade", ["na verdade"]),
    ("basicamente", ["basicamente"]),
    ("meio que", ["meio que"]),
    ("quer dizer", ["quer dizer", "ou seja"]),
    ("cara", ["cara"]),
    ("olha", ["olha", "olhe"]),
    ("bom...", [rf"bom{_PAUSA}"]),
    ("pra ser sincero", ["pra ser sincero", "para ser sincero", "sinceramente"]),
]

# Uma expressão só, com um grupo por vício: cada trecho conta uma vez ("né?" e "tipo assim" não somam em dobro).
_PADRAO = re.compile(
    rf"(?<!{_LETRA})(?:"
    + "|".join(f"(?P<v{i}>{'|'.join(padroes)})" for i, (_, padroes) in enumerate(_VICIOS))
    + rf")(?!{_LETRA})"
)


def detectar_vicios(transcricao: str) -> ViciosContagem:
    texto = unicodedata.normalize("NFC", transcricao or "").lower()
    return dict(Counter(_VICIOS[int(m.lastgroup[1:])][0] for m in _PADRAO.finditer(texto)))


def somar_vicios(lista: list[ViciosContagem | None]) -> ViciosContagem:
    total: ViciosContagem = {}
    for item in lista:
        for k, v in (item or {}).items():
            try:
                n = int(v)
            except (TypeError, ValueError):
                continue
            if n > 0:
                total[k] = total.get(k, 0) + n
    return total


def ranquear_vicios(contagem: ViciosContagem) -> list[dict]:
    itens = [{"termo": k, "total": int(v)} for k, v in contagem.items() if int(v) > 0]
    return sorted(itens, key=lambda x: (-x["total"], x["termo"]))


def resumir_vicios(contagem: ViciosContagem) -> str | None:
    ranking = ranquear_vicios(contagem)
    if not ranking:
        return None
    total = sum(v["total"] for v in ranking)
    top = ", ".join(f'"{v["termo"]}" ({v["total"]}x)' for v in ranking[:3])
    if total >= 8:
        return (
            f"Foram detectados {total} vícios de linguagem na sua arguição, com destaque para {top}. "
            "Pausar em silêncio no lugar dessas muletas deixa a fala mais firme."
        )
    return (
        f"Poucos vícios de linguagem: {total} no total ({top}). "
        "Sua fala está bem controlada. Mantenha a atenção nessas expressões."
    )
