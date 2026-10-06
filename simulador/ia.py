"""Chamadas diretas à OpenAI: embeddings, Whisper e voz."""

from __future__ import annotations

import re
from functools import lru_cache

from openai import OpenAI

from .custos import custo_tokens, custo_tts, custo_whisper
from .segredos import obter_segredo
from .uso import registrar_uso

EMBEDDING_MODEL = "text-embedding-3-small"
TTS_MODEL = "gpt-4o-mini-tts"
WHISPER_MODEL = "whisper-1"

# Sem um exemplo de fala hesitante, o Whisper apaga "é..." e "hum" da transcrição e os vícios somem.
PROMPT_TRANSCRICAO = "É... é... eu, é... acho que... hum... é... é... então... é... né? Ééé... é..."

INSTRUCAO_VOZ = (
    "Fale em português do Brasil, com tom formal, pausado e institucional, "
    "como um examinador de banca de concurso público."
)


class IntegracaoError(Exception):
    """Erro com mensagem pronta para o usuário."""


def chave_openai() -> str:
    key = obter_segredo("OPENAI_API_KEY")
    if not key:
        raise IntegracaoError("A chave da OpenAI ainda não foi configurada. Cadastre-a na aba Chaves de API do painel.")
    return key


@lru_cache(maxsize=4)
def _cliente(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def cliente() -> OpenAI:
    return _cliente(chave_openai())


def traduzir_erro(e: Exception, provedor: str = "OpenAI") -> IntegracaoError:
    if isinstance(e, IntegracaoError):
        return e
    print(f"[ia] erro da {provedor}: {e!r}")
    status = getattr(e, "status_code", None)
    if status == 401:
        return IntegracaoError(f"A chave da {provedor} foi recusada (401). Verifique a chave cadastrada.")
    if status == 429:
        return IntegracaoError(f"A {provedor} retornou limite de uso ou cota excedida (429). Verifique o saldo da conta.")
    if status:
        return IntegracaoError(f"A {provedor} retornou erro {status}. Tente novamente em instantes.")
    return IntegracaoError(f"A {provedor} não respondeu como esperado. Tente novamente em instantes.")


def gerar_embeddings(textos: list[str], sessao_id: str | None = None) -> list[list[float]]:
    try:
        res = cliente().embeddings.create(model=EMBEDDING_MODEL, input=textos)
    except Exception as e:
        raise traduzir_erro(e) from e
    tokens = getattr(res.usage, "prompt_tokens", 0) or 0
    registrar_uso(
        provedor="openai",
        operacao="embeddings",
        modelo=EMBEDDING_MODEL,
        unidade="tokens",
        quantidade=tokens,
        tokens_entrada=tokens,
        custo_usd=custo_tokens(EMBEDDING_MODEL, tokens, 0),
        sessao_id=sessao_id,
    )
    return [d.embedding for d in res.data]


def eco_do_prompt(texto: str) -> bool:
    """Áudio sem fala pode voltar como pedaços do prompt; aí a transcrição só tem palavras dele."""
    palavras = set(re.findall(r"\w+", texto.lower()))
    return bool(palavras) and palavras <= set(re.findall(r"\w+", PROMPT_TRANSCRICAO.lower()))


def transcrever_audio(dados: bytes, nome_arquivo: str = "resposta.wav", sessao_id: str | None = None) -> str:
    try:
        res = cliente().audio.transcriptions.create(
            file=(nome_arquivo, dados),
            model=WHISPER_MODEL,
            language="pt",
            prompt=PROMPT_TRANSCRICAO,
            response_format="verbose_json",
        )
    except Exception as e:
        raise traduzir_erro(e) from e
    segundos = float(getattr(res, "duration", 0) or 0)
    registrar_uso(
        provedor="openai",
        operacao="transcricao",
        modelo=WHISPER_MODEL,
        unidade="segundos",
        quantidade=round(segundos, 2),
        custo_usd=custo_whisper(segundos),
        sessao_id=sessao_id,
    )
    texto = (getattr(res, "text", "") or "").strip()
    return "" if eco_do_prompt(texto) else texto


def sintetizar_voz(texto: str, voz: str, sessao_id: str | None = None) -> bytes:
    try:
        res = cliente().audio.speech.create(
            model=TTS_MODEL,
            voice=voz,
            input=texto,
            instructions=INSTRUCAO_VOZ,
            response_format="mp3",
        )
        dados = res.content
    except Exception as e:
        raise traduzir_erro(e) from e
    registrar_uso(
        provedor="openai",
        operacao="voz_avaliador",
        modelo=TTS_MODEL,
        unidade="caracteres",
        quantidade=len(texto),
        custo_usd=custo_tts(len(texto)),
        sessao_id=sessao_id,
    )
    return dados
