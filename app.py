"""Simulador de Prova Oral para Promotor de Justiça do MPMG. Entrada: `streamlit run app.py`."""

from __future__ import annotations

import streamlit as st

from paginas import admin, auth, concursos, home, prova, resultado, sala
from simulador.ui.comum import aplicar_estilo

st.set_page_config(
    page_title="Simulador de Prova Oral · MPMG",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

rotas = {
    "home": st.Page(home.render, title="Início", url_path="inicio", default=True),
    "concursos": st.Page(concursos.render, title="Concursos", url_path="concursos"),
    "sala": st.Page(sala.render, title="Sala de espera", url_path="sala"),
    "prova": st.Page(prova.render, title="Prova oral", url_path="prova"),
    "resultado": st.Page(resultado.render, title="Resultado", url_path="resultado"),
    "auth": st.Page(auth.render, title="Acesso administrativo", url_path="auth"),
    "admin": st.Page(admin.render, title="Painel", url_path="admin"),
}
st.session_state["_rotas"] = rotas

aplicar_estilo()
st.navigation(list(rotas.values()), position="hidden").run()
