import streamlit as st

from simulador.simulacao import listar_concursos_publicos
from simulador.ui.comum import cabecalho, ir, rodape
from simulador.ui.projeto import DADOS_DA_PESQUISA

ETAPAS = [
    (
        "Pipeline de extração",
        "Gravações de arguições reais são transcritas (faster-whisper large-v3), separadas por falante "
        "(pyannote 3.1) e convertidas em pares de pergunta e resposta por um modelo de linguagem. Cada item "
        "passa por verificação das citações legais e por um revisor cego antes de entrar no banco.",
    ),
    (
        "Banco de perguntas reais",
        "Perguntas organizadas como na prova real: por grupo temático, pelo momento da arguição (início, meio "
        "e fim) e pelas cadeias de desdobramento que o examinador conduz. Os dados pessoais dos candidatos "
        "foram removidos.",
    ),
    (
        "Simulação e avaliação multiagente",
        "O avaliador lê as perguntas em voz alta e a resposta falada é transcrita. Quatro agentes independentes, "
        "cada um com acesso diferente ao gabarito, avaliam a resposta; um juiz pondera os pareceres e pode pedir "
        "esclarecimentos antes do veredito. Os agentes usam os modelos Sabiá, da Maritaca AI.",
    ),
]


def _iniciar() -> None:
    """Com um único concurso ativo, vai direto para a sala de espera."""
    try:
        concursos = listar_concursos_publicos()
    except Exception:  # noqa: BLE001
        concursos = []
    if len(concursos) == 1:
        ir("sala", concurso_id=concursos[0]["id"])
    ir("concursos")


def render() -> None:
    cabecalho()
    st.markdown('<p class="spo-kicker">Protótipo acadêmico</p>', unsafe_allow_html=True)
    st.markdown("## Simulação da arguição oral do concurso de Promotor de Justiça do Ministério Público de Minas Gerais")
    st.markdown(
        "Este protótipo reproduz a dinâmica da prova oral com perguntas extraídas de arguições reais do concurso. "
        "O sistema combina um pipeline de extração de dados, que transforma as gravações em um banco de perguntas "
        "estruturado, com uma banca de agentes de inteligência artificial, que avalia cada resposta do candidato "
        "e justifica a nota."
    )
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Iniciar simulação", type="primary", width="stretch"):
            _iniciar()
    with c2:
        st.markdown(
            '<p class="spo-muted" style="margin-top:.6rem">Requer microfone. Use o Chrome ou o Edge.</p>',
            unsafe_allow_html=True,
        )

    st.markdown("### Arquitetura da solução")
    cols = st.columns(3)
    for i, (titulo, texto) in enumerate(ETAPAS):
        with cols[i]:
            st.markdown(
                f'<div class="spo-card"><div class="spo-etapa">Etapa {i + 1}</div>'
                f"<h4>{titulo}</h4><p class='spo-muted'>{texto}</p></div>",
                unsafe_allow_html=True,
            )

    st.markdown("### Base de dados da pesquisa")
    st.table({"Item": [a for a, _ in DADOS_DA_PESQUISA], "Valor": [b for _, b in DADOS_DA_PESQUISA]}, hide_index=True)

    rodape()
