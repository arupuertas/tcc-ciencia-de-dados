"""Indicadores, tabelas e gráficos do relatório de resultado, com respostas montadas à mão."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulador.relatorio import indicadores, tabela_materias, tabela_respostas, tabela_vicios  # noqa: E402
from simulador.ui import graficos  # noqa: E402
from simulador.ui.comum import fmt_duracao  # noqa: E402
from simulador.vicios import detectar_vicios, ranquear_vicios  # noqa: E402


def _resposta(ordem, momento, materia, nota, fala, cobertos=0, faltantes=2, pulou=False):
    return {
        "ordem": ordem,
        "pergunta": f"Pergunta {ordem}?",
        "materia": materia,
        "tema": "Tema",
        "momento": momento,
        "transcricao": fala,
        "pulou": pulou,
        "nota": nota,
        "pontos_cobertos": ["ponto"] * cobertos,
        "pontos_faltantes": ["ponto"] * faltantes,
        "vicios": ranquear_vicios(detectar_vicios(fala)),
    }


RESPOSTAS = [
    _resposta(1, "inicio", "Direito Penal", 0.0, "Pular pergunta", faltantes=3, pulou=True),
    _resposta(2, "meio", "Direito Penal", 6.0, "É... é... então, né, o dolo eventual", cobertos=2, faltantes=1),
    _resposta(3, "meio", "Direito Civil", 9.0, "A prescrição é de dez anos, né?", cobertos=3, faltantes=0),
    _resposta(4, "fim", "Direito Civil", 7.0, "Hum... então, a boa-fé objetiva", cobertos=1, faltantes=1),
]


def test_indicadores():
    ind = indicadores(RESPOSTAS, duracao_segundos=292)
    assert (ind.perguntas, ind.puladas, ind.pontos_cobertos, ind.pontos_esperados) == (4, 1, 6, 11)
    assert ind.vicios == 7 and ind.palavras == 22  # "boa-fé" conta como duas
    assert round(ind.vicios_por_100_palavras, 1) == 31.8
    assert indicadores([], None).pontos_pct is None
    assert fmt_duracao(292) == "4 min 52 s" and fmt_duracao(58.4) == "58 s" and fmt_duracao(3720) == "1 h 2 min"


def test_tabelas():
    materias = tabela_materias(RESPOSTAS)
    assert list(materias["materia"]) == ["Direito Civil", "Direito Penal"]
    assert list(materias["media"]) == [8.0, 3.0] and list(materias["puladas"]) == [0, 1]
    vicios = tabela_vicios(RESPOSTAS).pivot(index="termo", columns="ordem", values="n")
    assert vicios.loc["é... / hum"].tolist() == [0, 2, 0, 1]
    assert vicios.loc["né"].tolist() == [0, 1, 1, 0]
    # além do limite, os menos frequentes viram "outros"
    assert list(dict.fromkeys(tabela_vicios(RESPOSTAS, limite=2)["termo"])) == ["é... / hum", "outros"]


def test_graficos_geram_especificacao_valida():
    # to_dict valida contra o esquema do Vega-Lite
    df = tabela_respostas(RESPOSTAS)
    faixas = graficos._faixas(df)
    assert list(faixas["momento"]) == ["Início", "Meio", "Fim"] and list(faixas["x2"]) == [1.5, 3.5, 4.5]
    graficos.evolucao(df, media=5.5).to_dict()
    graficos.materias(tabela_materias(RESPOSTAS)).to_dict()
    graficos.vicios_por_pergunta(tabela_vicios(RESPOSTAS), [r["ordem"] for r in RESPOSTAS]).to_dict()
