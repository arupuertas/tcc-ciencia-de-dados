from html import escape

import streamlit as st

from simulador.banca import nome_agente
from simulador.relatorio import Indicadores, indicadores, tabela_materias, tabela_respostas, tabela_vicios, vicios_da_prova
from simulador.simulacao import obter_resultado
from simulador.ui import graficos
from simulador.ui.comum import cabecalho, fixar_parametro, fmt_duracao, fmt_nota, link, parametro
from simulador.vicios import resumir_vicios


def _indicadores(nota_final: float | None, ind: Indicadores) -> None:
    pontos = "-" if ind.pontos_pct is None else f"{round(100 * ind.pontos_pct)}%"
    taxa = ind.vicios_por_100_palavras
    por_pergunta = ind.duracao_segundos / ind.perguntas if ind.duracao_segundos and ind.perguntas else None
    blocos = [
        ("Pontos-chave cobertos", pontos, f"{ind.pontos_cobertos} de {ind.pontos_esperados} pontos esperados"),
        ("Perguntas puladas", str(ind.puladas), f"de {ind.perguntas} perguntas"),
        ("Vícios de linguagem", str(ind.vicios), "" if taxa is None else f"{fmt_nota(taxa)} a cada 100 palavras"),
        ("Tempo de prova", fmt_duracao(ind.duracao_segundos), "" if por_pergunta is None else f"cerca de {fmt_duracao(por_pergunta)} por pergunta"),
    ]
    html = (
        '<div class="spo-kpis"><div class="spo-kpi spo-kpi-principal"><div class="spo-kpi-rotulo">Nota final</div>'
        f'<div class="spo-nota">{fmt_nota(nota_final, 2)} <span style="font-size:1rem;color:#888">/ 10</span></div>'
        f'<div class="spo-kpi-detalhe">média das {ind.perguntas} perguntas</div></div>'
        + "".join(
            f'<div class="spo-kpi"><div class="spo-kpi-rotulo">{rotulo}</div><div class="spo-kpi-valor">{valor}</div>'
            f'<div class="spo-kpi-detalhe">{detalhe}</div></div>'
            for rotulo, valor, detalhe in blocos
        )
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _tabela(respostas: list[dict]):
    df = tabela_respostas(respostas)
    return df.assign(
        nota=df["nota"].map(fmt_nota),
        pontos=[f"{c} de {e}" for c, e in zip(df["cobertos"], df["esperados"])],
        situacao=df["pulou"].map({True: "Pulada", False: "Respondida"}),
    )[["ordem", "momento", "materia", "tema", "nota", "pontos", "vicios", "situacao"]].rename(
        columns={
            "ordem": "Pergunta",
            "momento": "Momento",
            "materia": "Matéria",
            "tema": "Tema",
            "nota": "Nota",
            "pontos": "Pontos-chave cobertos",
            "vicios": "Vícios",
            "situacao": "Situação",
        }
    )


def _ata(ata: dict) -> None:
    with st.expander(f"⚖️ Ata da banca · divergência {fmt_nota(ata.get('divergencia', 0))}"):
        cols = st.columns(2)
        for i, p in enumerate(ata.get("avaliadores", [])):
            with cols[i % 2]:
                st.markdown(
                    f"**{p.get('nome')}** <span class='spo-badge'>{fmt_nota(p.get('nota'))}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f'<p class="spo-muted">{escape(p.get("parecer", ""))}</p>', unsafe_allow_html=True)
                if p.get("alertas"):
                    st.markdown(f"<p style='color:#9b1c1c;font-size:.85rem'>Alertas: {escape('; '.join(p['alertas']))}</p>", unsafe_allow_html=True)
        delib = ata.get("deliberacao", [])
        if delib:
            st.markdown("**Deliberação**")
            for e in delib:
                if e.get("tipo") == "pergunta":
                    st.markdown(f"- **Juiz → {nome_agente(e.get('para', ''))}:** {e.get('texto', '')}")
                else:
                    rev = f" _(nota revisada: {fmt_nota(e['notaRevisada'])})_" if e.get("notaRevisada") is not None else ""
                    st.markdown(f"- **{nome_agente(e.get('de', ''))}:** {e.get('texto', '')}{rev}")
        juiz = ata.get("juiz", {})
        st.caption(
            f"Nota final do juiz: {fmt_nota(juiz.get('nota'))}"
            + ("" if delib else " · sem divergência relevante, decidiu sem esclarecimentos")
        )


def render() -> None:
    cabecalho()
    sessao_id = st.session_state.get("sessao_id") or parametro("sessao")
    if not sessao_id:
        st.warning("Nenhuma simulação selecionada.")
        link("concursos", "Fazer uma simulação", "🎓")
        return
    fixar_parametro("sessao", sessao_id)

    try:
        estado, respostas = obter_resultado(sessao_id)
    except Exception as e:  # noqa: BLE001
        st.error(f"Não foi possível carregar esta simulação. {e}")
        return

    st.markdown(f'<p class="spo-kicker">{estado.concurso_nome}</p>', unsafe_allow_html=True)
    st.markdown("# Resultado da sua prova oral")
    if not respostas:
        st.info("Nenhuma resposta foi registrada nesta simulação.")
        link("concursos", "Fazer outra simulação", "🔁")
        return
    _indicadores(estado.nota_final, indicadores(respostas, estado.duracao_segundos))

    evolucao, materias = st.columns([3, 2])
    with evolucao, st.container(border=True):
        st.markdown("#### 📈 Evolução ao longo da arguição")
        media = "" if estado.nota_final is None else f" A linha cinza é a sua média ({fmt_nota(estado.nota_final, 2)})."
        st.caption("Nota de cada pergunta, na ordem da prova." + media)
        st.altair_chart(graficos.evolucao(tabela_respostas(respostas), estado.nota_final), width="stretch")
    with materias, st.container(border=True):
        st.markdown("#### 📚 Desempenho por matéria")
        st.caption("Nota média em cada matéria, de 0 a 10.")
        st.altair_chart(graficos.materias(tabela_materias(respostas)), width="stretch")

    with st.container(border=True):
        st.markdown("#### 💬 Vícios de linguagem")
        contagem = vicios_da_prova(respostas)
        if not contagem:
            st.markdown("Nenhum vício de linguagem recorrente foi identificado na sua fala. Excelente sinal.")
        else:
            st.markdown(resumir_vicios(contagem))
            st.caption("Quantas vezes cada vício apareceu em cada pergunta (P1 é a primeira).")
            ordens = [r["ordem"] for r in respostas]
            # largura pelo número de perguntas, para as células não esticarem em telas largas
            st.altair_chart(graficos.vicios_por_pergunta(tabela_vicios(respostas), ordens), width=160 + 80 * (len(ordens) + 1))

    if estado.postura_resumo:
        st.info(f"👁️ **Postura e confiança**: {estado.postura_resumo}\n\n"
                "Leitura feita a partir das fotos da sua câmera durante as respostas (expressão, olhar e postura).")

    with st.expander("📋 Dados dos gráficos"):
        st.dataframe(_tabela(respostas), hide_index=True, width="stretch")

    st.markdown("## Respostas avaliadas")
    for r in respostas:
        with st.container(border=True):
            a, b = st.columns([6, 1])
            with a:
                st.markdown(f"### {r['ordem']}. {r['pergunta']}")
            with b:
                st.markdown(f"<span class='spo-badge' style='font-size:1rem'>{fmt_nota(r['nota'])}</span>", unsafe_allow_html=True)
            st.markdown('<p class="spo-kicker">Sua resposta</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="spo-muted">{escape(r["transcricao"] or "")}</p>', unsafe_allow_html=True)
            if r["vicios"]:
                st.markdown(" ".join(f"<span class='spo-badge spo-badge-cinza'>{v['termo']} × {v['total']}</span>" for v in r["vicios"]), unsafe_allow_html=True)
            if r["justificativa"]:
                st.markdown('<p class="spo-kicker">Avaliação da banca</p>', unsafe_allow_html=True)
                st.markdown(r["justificativa"])
            if r["ata"]:
                _ata(r["ata"])
            if r["pontos_cobertos"] or r["pontos_faltantes"]:
                for p in r["pontos_cobertos"]:
                    st.markdown(f"✅ {p}")
                for p in r["pontos_faltantes"]:
                    st.markdown(f"❌ {p}")
            if r["nervosismo"] is not None or r["confianca"] is not None or r["postura_observacao"]:
                chips = []
                if r["nervosismo"] is not None:
                    chips.append(f"Nervosismo: {r['nervosismo']}/10")
                if r["confianca"] is not None:
                    chips.append(f"Confiança: {r['confianca']}/10")
                if r["lendo"] is not None:
                    chips.append("Indícios de leitura" if r["lendo"] else "Sem indícios de leitura")
                st.markdown("**Postura na câmera** · " + " · ".join(chips))
                if r["postura_observacao"]:
                    st.caption(r["postura_observacao"])

    c1, c2 = st.columns(2)
    with c1:
        link("concursos", "Fazer outra simulação", "🔁")
    with c2:
        link("home", "Voltar ao início", "🏠")
