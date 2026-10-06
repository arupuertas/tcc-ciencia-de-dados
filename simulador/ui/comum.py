"""Utilidades das páginas: navegação, cabeçalho, rodapé e assets."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[2] / "assets"


@lru_cache(maxsize=32)
def asset_data_url(nome: str, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode((ASSETS / nome).read_bytes()).decode()}"


def limpar_estado_prova() -> None:
    for k in [k for k in st.session_state if k.startswith("prova_")]:
        del st.session_state[k]


def rotas() -> dict:
    return st.session_state.get("_rotas", {})


def ir(nome: str, **estado) -> None:
    for k, v in estado.items():
        st.session_state[k] = v
    pagina = rotas().get(nome)
    if pagina is None:
        st.error(f"Página desconhecida: {nome}")
        st.stop()
    st.switch_page(pagina)


def link(nome: str, rotulo: str, icone: str | None = None) -> None:
    pagina = rotas().get(nome)
    if pagina is not None:
        st.page_link(pagina, label=rotulo, icon=icone)


def cabecalho() -> None:
    from .projeto import CURSO, INSTITUICAO, NATUREZA, TITULO

    esq, dir_ = st.columns([6, 1])
    with esq:
        st.markdown(
            f'<div class="spo-cabecalho"><div class="spo-kicker">{NATUREZA} · {CURSO} · {INSTITUICAO}</div>'
            f'<div class="spo-titulo">{TITULO}</div></div>',
            unsafe_allow_html=True,
        )
    with dir_:
        if st.session_state.get("admin_user_id"):
            link("admin", "Painel")
        else:
            link("auth", "Administração")
    st.markdown("---")


def rodape() -> None:
    from .projeto import ANO, AUTOR, INSTITUICAO, NATUREZA, ORIENTADOR

    partes = [f"Autor: {AUTOR}"] + ([f"Orientador: {ORIENTADOR}"] if ORIENTADOR else []) + [INSTITUICAO, str(ANO)]
    st.markdown("---")
    st.markdown(
        f'<p class="spo-muted">{NATUREZA}. Protótipo acadêmico, sem fins comerciais. As perguntas vêm de '
        f"arguições reais do concurso e foram anonimizadas.<br>{' · '.join(partes)}</p>",
        unsafe_allow_html=True,
    )


AZUL = "#1F4E8C"

ESTILO = """
<style>
.spo-cabecalho { padding-top:.2rem; }
.spo-titulo { font-size:1.35rem; font-weight:700; color:#1F2933; letter-spacing:-0.01em; }
.spo-card { border:1px solid #DDE3EA; border-radius:8px; padding:1rem 1.1rem; background:#FFFFFF; margin-bottom:.8rem; }
.spo-card h4 { margin:.2rem 0 .3rem; }
.spo-muted { color:#5F6B7A; font-size:.9rem; }
.spo-nota { font-size:3rem; color:#1F4E8C; font-weight:700; line-height:1; }
.spo-badge { display:inline-block; padding:.15rem .5rem; border-radius:4px; background:#E8EEF7; color:#163A69; font-size:.8rem; font-weight:600; }
.spo-badge-cinza { background:#EEF0F3; color:#3B4552; }
.spo-badge-vermelho { background:#FDE3E3; color:#9B1C1C; }
.spo-pergunta { font-size:1.15rem; line-height:1.5; }
.spo-kicker { text-transform:uppercase; letter-spacing:.12em; font-size:.7rem; color:#1F4E8C; }
.spo-etapa { font-size:.75rem; font-weight:700; color:#1F4E8C; text-transform:uppercase; letter-spacing:.1em; }
/* indicadores do resultado: a nota ocupa duas linhas à esquerda; no celular, a linha inteira */
.spo-kpis { display:grid; grid-template-columns:minmax(0,1.2fr) repeat(2,minmax(0,1fr)); gap:.75rem; margin:.5rem 0 1rem; }
.spo-kpi { border:1px solid #DDE3EA; border-radius:8px; padding:.85rem 1rem; background:#FFFFFF; }
.spo-kpi-principal { grid-row:span 2; display:flex; flex-direction:column; justify-content:center; }
.spo-kpi-rotulo { color:#5F6B7A; font-size:.85rem; }
.spo-kpi-valor { color:#1F2933; font-size:1.6rem; font-weight:600; line-height:1.25; margin:.2rem 0 .15rem; }
.spo-kpi-detalhe { color:#5F6B7A; font-size:.8rem; }
@media (max-width:640px) {
  .spo-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .spo-kpi-principal { grid-column:1 / -1; grid-row:auto; }
}
/* sem o ícone de link que o Streamlit põe ao lado dos títulos */
[data-testid="stHeaderActionElements"] { display:none !important; }
</style>
"""


def aplicar_estilo() -> None:
    st.markdown(ESTILO, unsafe_allow_html=True)


def ip_cliente() -> str | None:
    try:
        return st.context.ip_address
    except Exception:  # noqa: BLE001
        return None


def parametro(nome: str) -> str | None:
    try:
        v = st.query_params.get(nome)
    except Exception:  # noqa: BLE001
        return None
    return v if isinstance(v, str) and v else None


def fixar_parametro(nome: str, valor: str) -> None:
    try:
        if st.query_params.get(nome) != valor:
            st.query_params[nome] = valor
    except Exception:  # noqa: BLE001
        pass


def fmt_nota(n: float | None, casas: int = 1) -> str:
    return "-" if n is None else f"{n:.{casas}f}".replace(".", ",")


def fmt_duracao(segundos: float | None) -> str:
    if segundos is None:
        return "-"
    minutos, s = divmod(round(segundos), 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas} h {minutos} min"
    return f"{minutos} min {s} s" if minutos else f"{s} s"
