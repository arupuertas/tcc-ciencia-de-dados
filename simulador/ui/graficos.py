"""Gráficos do relatório de resultado (Altair), a partir das tabelas de `simulador.relatorio`.

Cores checadas para fundo branco: marcas com contraste de pelo menos 3:1 e degraus do mapa de calor
com luminosidade crescente num só tom de azul.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .comum import fmt_nota

SERIE = "#1C5CAB"  # o azul da marca (#1F4E8C) é escuro demais para marca de dado
CINZA = "#7B8794"
FAIXA = "#F4F6F9"
TINTA = "#1F2933"
APAGADO = "#5F6B7A"
REGUA = "#C3C9D1"
DEGRAUS = ["#86B6EF", "#5598E7", "#256ABF", "#184F95", "#0D366B"]  # 1, 2, 3, 4, 5 ou mais ocorrências
TEXTO_BRANCO_DESDE = 3  # a partir do terceiro degrau o número fica branco

ESCALA_NOTA = [0, 2, 4, 6, 8, 10]


def _plural(n: int, palavra: str) -> str:
    return f"{n} {palavra}" + ("" if n == 1 else "s")


def _faixas(df: pd.DataFrame) -> pd.DataFrame:
    """Trechos seguidos de perguntas do mesmo momento (início, meio, fim)."""
    faixas: list[dict] = []
    for ordem, momento in zip(df["ordem"], df["momento"]):
        if faixas and faixas[-1]["momento"] == momento and faixas[-1]["ate"] == ordem - 1:
            faixas[-1]["ate"] = ordem
        else:
            faixas.append({"momento": momento, "de": ordem, "ate": ordem})
    return pd.DataFrame(
        [
            {**f, "x1": f["de"] - 0.5, "x2": f["ate"] + 0.5, "centro": (f["de"] + f["ate"]) / 2, "sombra": i % 2 == 1}
            for i, f in enumerate(faixas)
        ]
    )


def evolucao(df: pd.DataFrame, media: float | None) -> alt.LayerChart:
    """Nota de cada pergunta na ordem da prova, com faixas para início, meio e fim e a média como régua."""
    dados = df.assign(
        nota_txt=df["nota"].map(fmt_nota),
        situacao=df["pulou"].map({True: "Pulada", False: "Respondida"}),
        pontos_txt=[f"{c} de {e}" for c, e in zip(df["cobertos"], df["esperados"])],
    )
    n = int(dados["ordem"].max())
    puladas = [int(o) for o in dados.loc[dados["pulou"], "ordem"]]
    x = alt.X(
        "ordem:Q",
        title="Pergunta",
        scale=alt.Scale(domain=[0.5, n + 0.5], nice=False, zero=False),
        axis=alt.Axis(
            values=list(range(1, n + 1)),
            format="d",
            grid=False,
            ticks=False,
            domain=False,
            # "pulada" vai embaixo do número, onde a linha não passa
            labelExpr=f"indexof({puladas}, datum.value) >= 0 ? [datum.label, 'pulada'] : datum.label",
        ),
    )
    y = alt.Y("nota:Q", title="Nota", scale=alt.Scale(domain=[0, 10], nice=False), axis=alt.Axis(values=ESCALA_NOTA, domain=False, ticks=False))
    passar = alt.selection_point(fields=["ordem"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    dica = [
        alt.Tooltip("ordem:Q", title="Pergunta"),
        alt.Tooltip("nota_txt:N", title="Nota"),
        alt.Tooltip("situacao:N", title="Situação"),
        alt.Tooltip("momento:N", title="Momento"),
        alt.Tooltip("materia:N", title="Matéria"),
        alt.Tooltip("tema:N", title="Tema"),
        alt.Tooltip("pontos_txt:N", title="Pontos-chave cobertos"),
    ]
    base = alt.Chart(dados).encode(x=x)

    faixas = _faixas(dados)
    camadas = [
        alt.Chart(faixas[faixas["sombra"]]).mark_rect(color=FAIXA).encode(x="x1:Q", x2="x2:Q"),
        alt.Chart(faixas).mark_text(baseline="bottom", dy=-10, color=APAGADO, fontSize=11).encode(
            x="centro:Q", y=alt.value(0), text="momento:N"
        ),
    ]
    if media is not None:
        camadas.append(alt.Chart(pd.DataFrame({"nota": [media]})).mark_rule(color=CINZA, strokeWidth=1).encode(y=y))
    camadas += [
        base.mark_rule(color=REGUA, strokeWidth=1).encode(opacity=alt.when(passar).then(alt.value(1)).otherwise(alt.value(0))),
        base.mark_line(color=SERIE, strokeWidth=2, strokeJoin="round", strokeCap="round").encode(y=y),
        base.mark_point(filled=True, opacity=1, stroke="white", strokeWidth=2).encode(
            y=y,
            color=alt.Color("situacao:N", scale=alt.Scale(domain=["Respondida", "Pulada"], range=[SERIE, CINZA]), legend=None),
            size=alt.when(passar).then(alt.value(150)).otherwise(alt.value(80)),
        ),
        # alvo invisível do mouse: sem eixo y, cada pergunta vira uma faixa vertical inteira
        base.mark_point(size=1, opacity=0).encode(tooltip=dica).add_params(passar),
    ]
    return alt.layer(*camadas).properties(height=300)  # altura total, com os eixos


def materias(dm: pd.DataFrame) -> alt.LayerChart:
    """Nota média por matéria em barras horizontais, com o valor na ponta."""
    dados = dm.assign(
        rotulo=[f"{m} ({_plural(int(p), 'pergunta')})" for m, p in zip(dm["materia"], dm["perguntas"])],
        media_txt=dm["media"].map(fmt_nota),
        pontos_txt=[f"{int(c)} de {int(e)}" for c, e in zip(dm["cobertos"], dm["esperados"])],
        dentro=dm["media"] >= 8.5,  # barra longa: o valor vai dentro da ponta, senão sairia do gráfico
    )
    base = alt.Chart(dados).encode(
        y=alt.Y("rotulo:N", sort=None, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=260, labelPadding=8, labelFontSize=12)),
        x=alt.X("media:Q", title="Nota média", scale=alt.Scale(domain=[0, 10], nice=False), axis=alt.Axis(values=ESCALA_NOTA, domain=False, ticks=False)),
        tooltip=[
            alt.Tooltip("materia:N", title="Matéria"),
            alt.Tooltip("media_txt:N", title="Nota média"),
            alt.Tooltip("perguntas:Q", title="Perguntas"),
            alt.Tooltip("puladas:Q", title="Puladas"),
            alt.Tooltip("pontos_txt:N", title="Pontos-chave cobertos"),
        ],
    )
    return alt.layer(
        base.mark_bar(color=SERIE, size=18, cornerRadiusEnd=4),
        base.transform_filter(~alt.datum.dentro).mark_text(align="left", dx=6, color=TINTA, fontSize=12).encode(text="media_txt:N"),
        base.transform_filter(alt.datum.dentro).mark_text(align="right", dx=-6, color="white", fontSize=12).encode(text="media_txt:N"),
    ).properties(height=alt.Step(40))


def vicios_por_pergunta(dv: pd.DataFrame, ordens: list[int]) -> alt.LayerChart:
    """Mapa de calor vício x pergunta com o número em cada célula e o total da linha na última coluna."""
    colunas = [f"P{o}" for o in ordens] + ["Total"]
    termos = list(dict.fromkeys(dv["termo"]))
    celulas = dv.assign(
        coluna=["P" + str(o) for o in dv["ordem"]],
        fundo=[DEGRAUS[min(n, len(DEGRAUS)) - 1] if n > 0 else FAIXA for n in dv["n"]],
        cor_texto=["white" if n >= TEXTO_BRANCO_DESDE else TINTA for n in dv["n"]],
        vezes=[_plural(int(n), "vez") if n else "nenhuma" for n in dv["n"]],
    )
    totais = dv.groupby("termo", sort=False, as_index=False)["n"].sum().assign(coluna="Total")
    x = alt.X("coluna:N", sort=colunas, scale=alt.Scale(domain=colunas), title=None, axis=alt.Axis(orient="top", labelAngle=0, ticks=False, domain=False))
    y = alt.Y("termo:N", sort=termos, scale=alt.Scale(domain=termos), title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=160, labelFontSize=12))
    dica = [alt.Tooltip("coluna:N", title="Pergunta"), alt.Tooltip("termo:N", title="Vício"), alt.Tooltip("vezes:N", title="Ocorrências")]
    return alt.layer(
        alt.Chart(celulas).mark_rect(cornerRadius=4, stroke="white", strokeWidth=2).encode(
            x=x, y=y, color=alt.Color("fundo:N", scale=None), tooltip=dica
        ),
        alt.Chart(celulas[celulas["n"] > 0]).mark_text(fontSize=12, fontWeight=600).encode(
            x=x, y=y, text="n:Q", color=alt.Color("cor_texto:N", scale=None), tooltip=dica
        ),
        alt.Chart(totais).mark_text(fontSize=12, fontWeight=700, color=TINTA).encode(x=x, y=y, text="n:Q"),
    ).properties(height=alt.Step(34))
