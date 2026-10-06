"""Indicadores e tabelas do relatório de resultado (puro, sem I/O).

Recebe as respostas de `simulacao.obter_resultado`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .vicios import ViciosContagem, ranquear_vicios, somar_vicios

MOMENTO_ROTULO = {"inicio": "Início", "meio": "Meio", "fim": "Fim"}


@dataclass
class Indicadores:
    perguntas: int
    puladas: int
    pontos_cobertos: int
    pontos_esperados: int
    vicios: int
    palavras: int
    duracao_segundos: int | None

    @property
    def pontos_pct(self) -> float | None:
        return self.pontos_cobertos / self.pontos_esperados if self.pontos_esperados else None

    @property
    def vicios_por_100_palavras(self) -> float | None:
        return 100 * self.vicios / self.palavras if self.palavras else None


def contar_palavras(texto: str | None) -> int:
    return len(re.findall(r"\w+", texto or ""))


def _contagem(resposta: dict) -> ViciosContagem:
    return {v["termo"]: v["total"] for v in resposta["vicios"]}


def vicios_da_prova(respostas: list[dict]) -> ViciosContagem:
    return somar_vicios([_contagem(r) for r in respostas])


def indicadores(respostas: list[dict], duracao_segundos: int | None) -> Indicadores:
    return Indicadores(
        perguntas=len(respostas),
        puladas=sum(1 for r in respostas if r["pulou"]),
        pontos_cobertos=sum(len(r["pontos_cobertos"]) for r in respostas),
        pontos_esperados=sum(len(r["pontos_cobertos"]) + len(r["pontos_faltantes"]) for r in respostas),
        vicios=sum(vicios_da_prova(respostas).values()),
        palavras=sum(contar_palavras(r["transcricao"]) for r in respostas),
        duracao_segundos=duracao_segundos,
    )


def tabela_respostas(respostas: list[dict]) -> pd.DataFrame:
    """Uma linha por pergunta, na ordem da prova."""
    return pd.DataFrame(
        [
            {
                "ordem": r["ordem"],
                "momento": MOMENTO_ROTULO.get(r["momento"] or "", "Sem momento"),
                "materia": r["materia"],
                "tema": r["tema"] or "",
                "nota": r["nota"],
                "pulou": r["pulou"],
                "cobertos": len(r["pontos_cobertos"]),
                "esperados": len(r["pontos_cobertos"]) + len(r["pontos_faltantes"]),
                "vicios": sum(_contagem(r).values()),
                "pergunta": r["pergunta"],
            }
            for r in respostas
        ]
    )


def tabela_materias(respostas: list[dict]) -> pd.DataFrame:
    """Nota média por matéria, da maior para a menor."""
    por_materia = (
        tabela_respostas(respostas)
        .groupby("materia", as_index=False)
        .agg(
            perguntas=("ordem", "size"),
            media=("nota", "mean"),
            cobertos=("cobertos", "sum"),
            esperados=("esperados", "sum"),
            puladas=("pulou", "sum"),
        )
    )
    return por_materia.sort_values(["media", "materia"], ascending=[False, True], ignore_index=True)


def tabela_vicios(respostas: list[dict], limite: int = 8) -> pd.DataFrame:
    """Vício x pergunta em formato longo, com os zeros. Além do limite, os menos frequentes viram "outros"."""
    ranking = [v["termo"] for v in ranquear_vicios(vicios_da_prova(respostas))]
    termos = ranking if len(ranking) <= limite else ranking[: limite - 1]
    linhas = []
    for r in respostas:
        contagem = _contagem(r)
        for termo in termos:
            linhas.append({"termo": termo, "ordem": r["ordem"], "n": contagem.get(termo, 0)})
        if len(termos) < len(ranking):
            outros = sum(n for t, n in contagem.items() if t not in termos)
            linhas.append({"termo": "outros", "ordem": r["ordem"], "n": outros})
    return pd.DataFrame(linhas, columns=["termo", "ordem", "n"])
