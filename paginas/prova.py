"""Sala de prova: o avaliador fala, o candidato responde, a banca avalia e a arguição avança."""

from __future__ import annotations

import random
from datetime import datetime
from html import escape

import streamlit as st

from simulador.config_app import obter_config_avaliador
from simulador.ia import IntegracaoError, sintetizar_voz, transcrever_audio
from simulador.limites import registrar_sinal
from simulador.simulacao import EstadoSessao, encerrar_sessao_candidato, obter_estado, responder
from simulador.ui.avatar import render_avatar
from simulador.ui.comum import cabecalho, fixar_parametro, ir, limpar_estado_prova, link, parametro
from simulador.ui.formatos import formato_valido

TRANSICOES = ["Entendi.", "Certo, obrigado.", "Ok, vamos adiante.", "Muito bem.", "Anotado. Seguindo:"]

S = st.session_state


def _saudacao(nome: str, grupo: int) -> str:
    h = datetime.now().hour
    periodo = "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"
    return (
        f"{periodo}{', ' + nome if nome else ''}. Grupo sorteado: {grupo}. Vamos conversar. "
        "Se em algum momento você não entender uma pergunta, basta me dizer que eu repito ou pergunto de outra forma."
    )


def _aviso_contexto(p, contexto: dict | None) -> str:
    if not p or (not p.materia and not p.tema):
        return ""
    mesma_materia = bool(contexto) and contexto.get("materia") == p.materia
    mesmo_tema = bool(contexto) and contexto.get("tema") == p.tema
    if contexto and mesma_materia and mesmo_tema:
        return ""
    partes = ", ".join(x for x in (f"matéria de {p.materia}" if p.materia else "", f"tema {p.tema}" if p.tema else "") if x)
    if not contexto:
        return f"Vamos começar com {partes}."
    if mesma_materia and p.tema:
        return f"Seguimos na mesma matéria, mas agora no tema {p.tema}."
    return f"Agora mudamos de assunto: {partes}."


def _fala_atual(estado: EstadoSessao) -> tuple[str, str] | None:
    if not S.get("prova_saudacao_ok"):
        return "saudacao", _saudacao(S.get("candidato_nome", ""), estado.grupo)
    if S.get("prova_intervencao"):
        return S["prova_intervencao_id"], S["prova_intervencao"]
    p = estado.pergunta_atual
    if not p:
        return None
    # Monta a fala uma vez por pergunta (transição + aviso de matéria/tema).
    if S.get("prova_fala_pergunta_id") != p.id:
        prefixo = " ".join(x for x in (S.get("prova_transicao", ""), _aviso_contexto(p, S.get("prova_contexto"))) if x)
        S["prova_fala_pergunta_id"] = p.id
        S["prova_fala_pergunta"] = f"{prefixo} {p.texto}".strip()
        S["prova_contexto"] = {"materia": p.materia, "tema": p.tema}
        S["prova_transicao"] = ""
    return p.id, S["prova_fala_pergunta"]


def _audio_para(fala_id: str, texto: str, voz: str, sessao_id: str) -> bytes | None:
    audios: dict = S.setdefault("prova_audios", {})
    if fala_id in audios:
        return audios[fala_id]
    try:
        with st.spinner("Preparando a fala do avaliador…"):
            audios[fala_id] = sintetizar_voz(texto, voz, sessao_id)
    except Exception as e:  # noqa: BLE001
        st.warning(f"Sem voz do avaliador ({e}). A arguição segue pelo texto.")
        audios[fala_id] = None
    return audios[fala_id]


def _liberar_para_nova_tentativa(mensagem: str) -> None:
    """Falha na avaliação: libera a pergunta e devolve um gravador limpo.

    Sem isso `prova_processado_<n>` fica marcado e o candidato trava; trocar a tentativa também
    evita reenviar a mesma gravação contra a API que acabou de falhar.
    """
    tentativa = S.get("prova_tentativa", 0)
    S[f"prova_processado_{tentativa}"] = False
    S["prova_tentativa"] = tentativa + 1
    S["prova_erro"] = f"{mensagem} Sua resposta não foi registrada: grave novamente."
    st.rerun()


def _processar_resposta(sessao_id: str, texto: str, quadros: list[bytes]) -> None:
    try:
        with st.spinner("A banca está avaliando sua resposta… isso pode levar alguns segundos."):
            retorno = responder(sessao_id, texto, quadros)
    except IntegracaoError as e:
        return _liberar_para_nova_tentativa(str(e))
    except Exception as e:  # noqa: BLE001
        return _liberar_para_nova_tentativa(f"Falha ao enviar a resposta: {e}")

    S["prova_tentativa"] = S.get("prova_tentativa", 0) + 1
    if retorno.fala:
        S["prova_intervencao"] = retorno.fala
        S["prova_intervencao_id"] = f"fala-{S['prova_tentativa']}"
    else:
        S["prova_intervencao"] = None
        S["prova_transicao"] = retorno.transicao_fala or random.choice(TRANSICOES)
    S["prova_estado"] = retorno.estado
    st.rerun()


def render() -> None:
    cabecalho()
    sessao_id = S.get("sessao_id") or parametro("sessao")
    if not sessao_id:
        st.warning("Nenhuma simulação em andamento.")
        link("concursos", "Escolher um concurso", "🎓")
        return
    S["sessao_id"] = sessao_id
    fixar_parametro("sessao", sessao_id)

    estado: EstadoSessao | None = S.get("prova_estado")
    if not estado or estado.sessao_id != sessao_id:
        try:
            estado = obter_estado(sessao_id)
        except Exception as e:  # noqa: BLE001
            st.error(f"Simulação não encontrada. {e}")
            link("concursos", "Fazer outra simulação")
            return
        S["prova_estado"] = estado

    if estado.status == "finalizada":
        ir("resultado", sessao_id=sessao_id)
    if estado.status != "em_andamento":
        st.warning("Esta simulação foi encerrada.")
        link("concursos", "Fazer outra simulação")
        return

    registrar_sinal(sessao_id)

    try:
        config = obter_config_avaliador()
    except Exception:  # noqa: BLE001
        config = None
    voz = config.voz if config else "onyx"
    formato = formato_valido(S.get("formato_avaliador")) or "foto"

    a, b, c = st.columns([3, 1.2, 1.2])
    with a:
        st.markdown(f'<p class="spo-kicker">{estado.concurso_nome}</p>', unsafe_allow_html=True)
        st.markdown("## Banca examinadora")
    with b:
        st.metric("Pergunta", f"{min(estado.indice + 1, estado.total)} de {estado.total}")
    with c:
        with st.popover("Encerrar avaliação"):
            st.write("Encerrar a avaliação agora? O progresso desta arguição será perdido.")
            if st.button("Sim, encerrar", type="primary"):
                encerrar_sessao_candidato(sessao_id, "encerrada")
                limpar_estado_prova()
                S.pop("sessao_id", None)
                ir("home")

    fala = _fala_atual(estado)
    pergunta = estado.pergunta_atual
    tocadas: set = S.setdefault("prova_tocadas", set())

    esq, dir_ = st.columns([1.3, 1])
    with esq:
        audio = _audio_para(fala[0], fala[1], voz, sessao_id) if fala else None
        autoplay = bool(fala) and fala[0] not in tocadas
        if fala:
            tocadas.add(fala[0])
        render_avatar(formato, audio, autoplay=autoplay, ouvindo=bool(S.get("prova_saudacao_ok")))

        st.info(f"**Grupo sorteado: {estado.grupo}** · todas as perguntas desta arguição vêm deste grupo.")

        with st.container(border=True):
            st.markdown('<p class="spo-kicker">Pergunta do avaliador</p>', unsafe_allow_html=True)
            if not S.get("prova_saudacao_ok"):
                st.markdown(f'<p class="spo-pergunta">{escape(fala[1]) if fala else ""}</p>', unsafe_allow_html=True)
                if st.button("Estou pronto, pode perguntar →", type="primary"):
                    S["prova_saudacao_ok"] = True
                    st.rerun()
            elif pergunta:
                if pergunta.materia or pergunta.tema:
                    st.markdown(f"**{' · '.join(x for x in (pergunta.materia, pergunta.tema) if x)}**")
                if S.get("prova_intervencao"):
                    st.markdown(f'<p class="spo-muted">{escape(S["prova_intervencao"])}</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="spo-pergunta">{escape(pergunta.texto)}</p>', unsafe_allow_html=True)
            else:
                st.markdown("O avaliador está encerrando a arguição…")

    with dir_:
        if not S.get("prova_saudacao_ok") or not pergunta:
            st.markdown('<p class="spo-muted">Aguarde: o avaliador vai cumprimentar você e iniciar a arguição.</p>', unsafe_allow_html=True)
            return

        tentativa = S.get("prova_tentativa", 0)
        if erro := S.pop("prova_erro", None):
            st.error(erro)
        with st.container(border=True):
            st.markdown('<p class="spo-kicker">Sua resposta</p>', unsafe_allow_html=True)
            st.caption(
                "Ouça a pergunta, clique no microfone, responda em voz alta e pare a gravação quando terminar. "
                "Se não entendeu, diga isso na gravação: o avaliador repete ou reformula."
            )
            gravacao = st.audio_input("Gravar resposta", key=f"prova_audio_{tentativa}")
            foto = st.camera_input(
                "Foto durante a resposta (opcional, para leitura de postura)",
                key=f"prova_cam_{tentativa}",
            )
            with st.expander("Prefere digitar a resposta?"):
                texto_digitado = st.text_area("Resposta escrita", key=f"prova_texto_{tentativa}", height=120)
                enviar_texto = st.button("Enviar resposta escrita", key=f"prova_enviar_{tentativa}")

        quadros = [foto.getvalue()] if foto is not None else []
        chave_proc = f"prova_processado_{tentativa}"
        if S.get(chave_proc):
            return

        if gravacao is not None and len(gravacao.getvalue()) > 1000:
            S[chave_proc] = True
            try:
                with st.spinner("Transcrevendo sua resposta…"):
                    texto = transcrever_audio(gravacao.getvalue(), "resposta.wav", sessao_id)
            except IntegracaoError as e:
                return _liberar_para_nova_tentativa(str(e))
            if len(texto) < 5:
                # Guardado na sessão: um st.error sumiria no rerun.
                S["prova_erro"] = "Não captamos sua resposta. Fale novamente com o microfone ativo."
                S["prova_tentativa"] = tentativa + 1
                st.rerun()
            st.markdown(f'<p class="spo-muted">Transcrição: {escape(texto)}</p>', unsafe_allow_html=True)
            _processar_resposta(sessao_id, texto, quadros)
        elif enviar_texto and len((texto_digitado or "").strip()) >= 5:
            S[chave_proc] = True
            _processar_resposta(sessao_id, texto_digitado.strip(), quadros)
