"""Banca com modelo simulado: avaliadores em paralelo, ferramenta do juiz e ata. Sem rede."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CHAVES_CRIPTO_SECRET", "segredo-de-teste")

import pytest  # noqa: E402

from simulador import agentes, personas  # noqa: E402
from simulador.banca import AVALIADORES, Dossie, Esclarecimento, ParecerAvaliador, Veredito  # noqa: E402
from simulador.config_app import ConfigBanca  # noqa: E402


class _Saida(SimpleNamespace):
    pass


def _saida(conteudo):
    return _Saida(content=conteudo, metrics=SimpleNamespace(input_tokens=10, output_tokens=5))


@pytest.fixture
def banca_simulada(monkeypatch):
    monkeypatch.setattr(agentes, "obter_config_banca", lambda: ConfigBanca("openai:gpt-4o-mini", "openai:gpt-4o"))
    monkeypatch.setattr(agentes, "obter_segredo", lambda _id: "sk-teste")
    monkeypatch.setattr(agentes, "registrar_uso", lambda **kw: None)

    notas = {"critico": 3.0, "tranquilo": 8.0, "verificador": 6.0, "independente": 7.0}
    chamadas = {"juiz": 0}

    def run(self, entrada, **kwargs):
        schema = self.output_schema
        if schema is ParecerAvaliador:
            agente = next(a for a in AVALIADORES if personas.PADRAO[a.id] in (self.instructions or ""))
            return _saida(ParecerAvaliador(nota=notas[agente.id], parecer=f"parecer {agente.id}", pontos_cobertos=["x"], pontos_faltantes=[], alertas=[]))
        if schema is Esclarecimento:
            return _saida(Esclarecimento(esclarecimento="mantenho", nota_revisada=None))
        if schema is Veredito:
            chamadas["juiz"] += 1
            if self.tools:
                r = self.tools[0]("critico", "O candidato citou o art. 18: isso não atende ao ponto?")
                assert "mantenho" in r
                r2 = self.tools[0]("critico", "de novo?")
                assert "Limite" in r2  # uma pergunta por avaliador
            return _saida(Veredito(nota=6.5, justificativa="ok", pontos_cobertos=["x"], pontos_faltantes=["y"]))
        raise AssertionError(f"schema inesperado: {schema}")

    monkeypatch.setattr(agentes.Agent, "run", run)
    return chamadas


def _dossie() -> Dossie:
    return Dossie(
        pergunta="O que é tutela provisória?",
        resposta_padrao="Gabarito.",
        transcricao="Resposta do candidato.",
        contexto=["trecho 1"],
        pontos_chave=["a", "b"],
        fundamentos_legais=["art. 300 CPC"],
        materia="Processo Civil",
        tema="Tutela",
        sessao_id=None,
    )


def test_banca_com_divergencia_delibera(banca_simulada):
    veredito, ata = agentes.avaliar_com_banca(_dossie())
    assert veredito.nota == 6.5
    assert len(ata.avaliadores) == 4
    assert ata.divergencia == 5.0
    assert [e["tipo"] for e in ata.deliberacao] == ["pergunta", "esclarecimento"]
    assert ata.juiz == {"modelo": "openai:gpt-4o", "nota": 6.5}
    assert banca_simulada["juiz"] == 1


def test_dossie_respeita_visao_do_avaliador():
    d = _dossie()
    independente = next(a for a in AVALIADORES if a.id == "independente")
    texto = agentes._dossie_do_avaliador(independente.ve, d)
    assert "RESPOSTA PADRÃO" not in texto and "BASE DE CONHECIMENTO" not in texto
    critico = next(a for a in AVALIADORES if a.id == "critico")
    texto = agentes._dossie_do_avaliador(critico.ve, d)
    assert "RESPOSTA PADRÃO" in texto and "FUNDAMENTOS LEGAIS" in texto and "BASE DE CONHECIMENTO" not in texto


def test_resolver_modelo_temperatura(monkeypatch):
    monkeypatch.setattr(agentes, "obter_segredo", lambda _id: "k")
    assert agentes.resolver_modelo("openai:gpt-4o").instancia.temperature == 0.2
    assert agentes.resolver_modelo("openai:gpt-5-mini").instancia.temperature is None
    sabia = agentes.resolver_modelo("maritaca:sabia-4").instancia
    assert isinstance(sabia, agentes.Maritaca) and sabia.temperature == 0.2
    assert str(sabia.base_url) == "https://chat.maritaca.ai/api"
    assert agentes.resolver_modelo("maritaca:sabia-4-thinking").instancia.temperature is None
    with pytest.raises(agentes.IntegracaoError):
        agentes.resolver_modelo("invalido")


def test_maritaca_estrutura_por_prompt_sem_response_format(monkeypatch):
    """A Maritaca não aceita `response_format`: o esquema vai no prompt e o texto vira o modelo Pydantic."""
    import json as _json

    from openai.resources.chat.completions import Completions
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice
    from openai.types.completion_usage import CompletionUsage

    monkeypatch.setattr(agentes, "obter_segredo", lambda _id: "chave-teste")
    enviado = {}

    def falso_create(self, **kwargs):
        enviado.update(kwargs)
        corpo = {"nota": 8.5, "parecer": "Boa resposta.", "pontos_cobertos": ["a"], "pontos_faltantes": [], "alertas": []}
        return ChatCompletion(
            id="x", created=0, model=kwargs["model"], object="chat.completion",
            choices=[Choice(index=0, finish_reason="stop",
                            message=ChatCompletionMessage(role="assistant", content="```json\n" + _json.dumps(corpo) + "\n```"))],
            usage=CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    monkeypatch.setattr(Completions, "create", falso_create)
    m = agentes.resolver_modelo("maritaca:sabiazinho-4")
    saida = agentes.Agent(model=m.instancia, instructions="Avalie.", output_schema=ParecerAvaliador, markdown=False).run("Resposta do candidato.")

    assert enviado["model"] == "sabiazinho-4"
    assert "response_format" not in enviado
    sistema = next(msg["content"] for msg in enviado["messages"] if msg["role"] == "system")
    assert "pontos_cobertos" in sistema and "nota" in sistema      # o esquema foi para o prompt
    parecer = agentes._conteudo(saida, ParecerAvaliador)
    assert parecer.nota == 8.5 and parecer.pontos_cobertos == ["a"]
