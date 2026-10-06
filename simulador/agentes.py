"""Agentes Agno: classificador de turno, leitor de postura e banca (avaliadores e juiz)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Literal

from agno.agent import Agent
from agno.media import Image
from agno.models.message import Message
from agno.models.openai import OpenAIChat
from agno.models.openai.like import OpenAILike
from pydantic import BaseModel, Field

from .banca import (
    AVALIADORES,
    JUIZ_ID,
    JUIZ_NOME,
    LIMIAR_DIVERGENCIA,
    MAX_ESCLARECIMENTOS,
    AgenteAvaliador,
    AtaBanca,
    Dossie,
    Esclarecimento,
    ParecerAvaliador,
    Veredito,
    VisaoAvaliador,
)
from .config_app import obter_config_banca, obter_config_prompts
from .custos import custo_tokens
from .ia import IntegracaoError, traduzir_erro
from .modelos import PROVEDORES_LLM, chave_do_provedor, separar_modelo
from .segredos import obter_segredo
from .uso import registrar_uso


MARITACA_BASE_URL = "https://chat.maritaca.ai/api"


@dataclass
class Maritaca(OpenAILike):
    """Modelos Sabiá pela API compatível com a OpenAI.

    A Maritaca não aceita `response_format`: sem saída estruturada nativa, o Agno põe o esquema
    no prompt e converte o texto devolvido; o parâmetro é retirado em `get_request_params`.
    """

    id: str = "sabia-4"
    name: str = "Maritaca"
    provider: str = "Maritaca"
    base_url: str = MARITACA_BASE_URL
    supports_native_structured_outputs: bool = False
    supports_json_schema_outputs: bool = False

    def get_request_params(self, *args, **kwargs):
        params = super().get_request_params(*args, **kwargs)
        params.pop("response_format", None)
        return params


@dataclass
class ModeloResolvido:
    id: str
    provedor: str
    modelo: str
    instancia: object


def _aceita_temperatura(provedor: str, modelo: str) -> bool:
    # Modelos de raciocínio (GPT-5, o-series, Sabiá thinking) não aceitam `temperature`.
    if provedor == "maritaca" and "thinking" in modelo:
        return False
    if provedor == "openai" and (modelo.startswith("gpt-5") or modelo[:1] == "o"):
        return False
    return True


def resolver_modelo(id: str, temperatura: float = 0.2) -> ModeloResolvido:
    partes = separar_modelo(id)
    if not partes:
        raise IntegracaoError(f'Modelo inválido na configuração da banca: "{id}".')
    provedor, modelo = partes
    api_key = obter_segredo(chave_do_provedor(provedor))
    if not api_key:
        nome = PROVEDORES_LLM[provedor]["nome"]
        raise IntegracaoError(
            f"A chave da {nome} ({chave_do_provedor(provedor)}) não está configurada. Cadastre-a na aba Chaves de API."
        )
    extra = {"temperature": temperatura} if _aceita_temperatura(provedor, modelo) else {}
    if provedor == "maritaca":
        instancia = Maritaca(id=modelo, api_key=api_key, **extra)
    else:
        instancia = OpenAIChat(id=modelo, api_key=api_key, **extra)
    return ModeloResolvido(id=id, provedor=provedor, modelo=modelo, instancia=instancia)


def status_provedores() -> dict[str, bool]:
    return {p: bool(obter_segredo(chave_do_provedor(p))) for p in PROVEDORES_LLM}


def _registrar(operacao: str, m: ModeloResolvido, saida, sessao_id: str | None) -> None:
    metrics = getattr(saida, "metrics", None)
    entrada = int(getattr(metrics, "input_tokens", 0) or 0)
    saida_t = int(getattr(metrics, "output_tokens", 0) or 0)
    registrar_uso(
        provedor=m.provedor,
        operacao=operacao,
        modelo=m.modelo,
        unidade="tokens",
        quantidade=entrada + saida_t,
        tokens_entrada=entrada,
        tokens_saida=saida_t,
        custo_usd=custo_tokens(m.modelo, entrada, saida_t),
        sessao_id=sessao_id,
    )


def _executar(agent: Agent, entrada, **kwargs):
    try:
        return agent.run(entrada, **kwargs)
    except Exception as e:  # noqa: BLE001
        raise traduzir_erro(e, getattr(agent.model, "provider", None) or "API") from e


def _conteudo(saida, schema: type[BaseModel]) -> BaseModel:
    c = saida.content
    if isinstance(c, schema):
        return c
    if isinstance(c, BaseModel):
        return schema.model_validate(c.model_dump())
    if isinstance(c, dict):
        return schema.model_validate(c)
    if isinstance(c, str):
        try:
            return schema.model_validate_json(c)
        except Exception as e:  # noqa: BLE001
            raise IntegracaoError("Não foi possível interpretar a resposta estruturada da IA.") from e
    raise IntegracaoError("A IA não retornou uma resposta estruturada.")


class TurnoCandidato(BaseModel):
    intencao: Literal["resposta", "repetir", "reformular", "conversa", "pular"] = "resposta"
    fala: str = ""


def instrucoes_do_turno() -> str:
    return obter_config_prompts().texto("turno")


def interpretar_turno(pergunta: str, transcricao: str, sessao_id: str | None = None) -> TurnoCandidato:
    m = resolver_modelo(obter_config_banca().modelo_auxiliar, temperatura=0.4)
    agent = Agent(model=m.instancia, instructions=instrucoes_do_turno(), output_schema=TurnoCandidato, markdown=False)
    try:
        saida = _executar(agent, f"PERGUNTA ATUAL:\n{pergunta}\n\nFALA DO CANDIDATO:\n{transcricao or '(silêncio)'}")
        _registrar("conversacao", m, saida, sessao_id)
        turno = _conteudo(saida, TurnoCandidato)
        return TurnoCandidato(intencao=turno.intencao, fala=(turno.fala or "").strip())
    except IntegracaoError:
        raise
    except Exception:  # na dúvida, trata como resposta para não travar a arguição
        return TurnoCandidato(intencao="resposta", fala="")


class PosturaCandidato(BaseModel):
    nervosismo: int = Field(ge=0, le=10)
    confianca: int = Field(ge=0, le=10)
    lendo: bool
    observacao: str = ""


def instrucoes_da_postura() -> str:
    return obter_config_prompts().texto("postura")


def analisar_postura(
    pergunta: str, transcricao: str, quadros: list[bytes], sessao_id: str | None = None
) -> PosturaCandidato | None:
    quadros = [q for q in quadros if q][:3]
    if not quadros:
        return None
    m = resolver_modelo(obter_config_banca().modelo_visao, temperatura=0.2)
    agent = Agent(model=m.instancia, instructions=instrucoes_da_postura(), output_schema=PosturaCandidato, markdown=False)
    saida = _executar(
        agent,
        f"PERGUNTA:\n{pergunta}\n\nRESPOSTA FALADA (transcrição):\n{transcricao or '(sem fala)'}\n\n"
        "Quadros da webcam durante a resposta em anexo.",
        images=[Image(content=q, format="png" if q[:4] == b"\x89PNG" else "jpeg") for q in quadros],
    )
    _registrar("analise_postura", m, saida, sessao_id)
    try:
        p = _conteudo(saida, PosturaCandidato)
    except IntegracaoError:
        return None
    return PosturaCandidato(
        nervosismo=max(0, min(10, int(p.nervosismo))),
        confianca=max(0, min(10, int(p.confianca))),
        lendo=bool(p.lendo),
        observacao=(p.observacao or "").strip(),
    )


def _lista(itens: list[str]) -> str:
    return "\n".join(f"- {i}" for i in itens)


def _dossie_do_avaliador(agente_ve, d: Dossie) -> str:
    """Dossiê de um avaliador: só o que a visão dele permite."""
    blocos = [
        f"MATÉRIA / TEMA:\n{' / '.join(x for x in (d.materia, d.tema) if x)}" if (d.materia or d.tema) else None,
        f"PERGUNTA DA BANCA:\n{d.pergunta}",
        f"RESPOSTA PADRÃO (NOTA 10):\n{d.resposta_padrao}" if agente_ve.gabarito else None,
        f"PONTOS-CHAVE ESPERADOS:\n{_lista(d.pontos_chave)}" if agente_ve.pontos_chave and d.pontos_chave else None,
        f"FUNDAMENTOS LEGAIS DE REFERÊNCIA:\n{_lista(d.fundamentos_legais)}"
        if agente_ve.fundamentos and d.fundamentos_legais
        else None,
        (
            "BASE DE CONHECIMENTO:\n"
            + ("\n\n".join(f"[Trecho {i + 1}]\n{c}" for i, c in enumerate(d.contexto)) if d.contexto else "Nenhum trecho disponível.")
        )
        if agente_ve.base_conhecimento
        else None,
        f"RESPOSTA TRANSCRITA DO CANDIDATO:\n{d.transcricao or '(o candidato não respondeu)'}",
    ]
    return "\n\n".join(b for b in blocos if b)


def instrucoes_do_avaliador(agente_id: str) -> str:
    c = obter_config_prompts()
    return c.texto(agente_id) + c.regras_saida


def instrucoes_do_juiz() -> str:
    return obter_config_prompts().texto(JUIZ_ID)


@dataclass
class _Opiniao:
    agente: AgenteAvaliador
    parecer: ParecerAvaliador
    prompt: str


def _opinar(agente: AgenteAvaliador, d: Dossie, m: ModeloResolvido) -> _Opiniao:
    prompt = _dossie_do_avaliador(agente.ve, d)
    agent = Agent(model=m.instancia, instructions=instrucoes_do_avaliador(agente.id), output_schema=ParecerAvaliador, markdown=False)
    saida = _executar(agent, prompt)
    _registrar(f"banca_{agente.id}", m, saida, d.sessao_id)
    return _Opiniao(agente=agente, parecer=_conteudo(saida, ParecerAvaliador), prompt=prompt)


def _esclarecer(op: _Opiniao, pergunta_do_juiz: str, d: Dossie, m: ModeloResolvido) -> Esclarecimento:
    """Resposta do avaliador ao juiz, baseada só no que ele mesmo analisou."""
    agent = Agent(model=m.instancia, instructions=instrucoes_do_avaliador(op.agente.id), output_schema=Esclarecimento, markdown=False)
    mensagens = [
        Message(role="user", content=op.prompt),
        Message(role="assistant", content=op.parecer.model_dump_json()),
        Message(
            role="user",
            content=(
                f'O juiz da banca pede um esclarecimento sobre a SUA avaliação:\n"{pergunta_do_juiz}"\n\n'
                "Responda com base no que você já analisou. Revise a nota apenas se o juiz apontou um fato "
                "concreto da resposta que você deixou de considerar; caso contrário, mantenha sua posição "
                "(nota_revisada = null). Não mude de opinião por pressão."
            ),
        ),
    ]
    saida = _executar(agent, mensagens)
    _registrar(f"banca_{op.agente.id}_esclarecimento", m, saida, d.sessao_id)
    return _conteudo(saida, Esclarecimento)


_VE_NADA = VisaoAvaliador(gabarito=False, base_conhecimento=False, pontos_chave=False, fundamentos=False)
_VE_TUDO = VisaoAvaliador(gabarito=True, base_conhecimento=True, pontos_chave=True, fundamentos=True)


def _dossie_do_juiz(d: Dossie, opinioes: list[_Opiniao]) -> str:
    pareceres = "\n\n".join(
        f"### {o.agente.nome} (id: {o.agente.id})\n"
        f"Nota: {o.parecer.nota}\nParecer: {o.parecer.parecer}\n"
        f"Pontos cobertos: {'; '.join(o.parecer.pontos_cobertos) or '-'}\n"
        f"Pontos faltantes: {'; '.join(o.parecer.pontos_faltantes) or '-'}\n"
        f"Alertas: {'; '.join(o.parecer.alertas) or 'nenhum'}"
        for o in opinioes
    )
    return _dossie_do_avaliador(_VE_TUDO, d) + f"\n\nPARECERES INDEPENDENTES DA BANCA:\n\n{pareceres}"


def previa_dos_prompts(d: Dossie) -> list[dict]:
    """Prompt que cada um dos sete agentes receberia para o dossiê, sem chamar modelo (aba Agentes)."""
    itens = [
        {
            "id": "turno",
            "nome": "Classificador de turno",
            "descricao": "Decide se a fala é resposta, pedido de repetição, reformulação, conversa ou desistência.",
            "instrucoes": instrucoes_do_turno(),
            "prompt": f"PERGUNTA ATUAL:\n{d.pergunta}\n\nFALA DO CANDIDATO:\n{d.transcricao or '(silêncio)'}",
            "ve": asdict(_VE_NADA),
        },
        {
            "id": "postura",
            "nome": "Leitor de postura",
            "descricao": "Lê os quadros da webcam: nervosismo, confiança e indícios de leitura.",
            "instrucoes": instrucoes_da_postura(),
            "prompt": (
                f"PERGUNTA:\n{d.pergunta}\n\nRESPOSTA FALADA (transcrição):\n{d.transcricao or '(sem fala)'}\n\n"
                "Quadros da webcam durante a resposta em anexo."
            ),
            "ve": asdict(_VE_NADA),
        },
    ] + [
        {
            "id": a.id,
            "nome": a.nome,
            "descricao": a.descricao,
            "instrucoes": instrucoes_do_avaliador(a.id),
            "prompt": _dossie_do_avaliador(a.ve, d),
            "ve": asdict(a.ve),
        }
        for a in AVALIADORES
    ]
    exemplo = [
        _Opiniao(
            agente=a,
            parecer=ParecerAvaliador(
                nota=7.0,
                parecer="(parecer deste avaliador entra aqui)",
                pontos_cobertos=["(ponto coberto)"],
                pontos_faltantes=["(ponto faltante)"],
                alertas=[],
            ),
            prompt="",
        )
        for a in AVALIADORES
    ]
    itens.append(
        {
            "id": JUIZ_ID,
            "nome": JUIZ_NOME,
            "descricao": "Preside a banca, pode pedir esclarecimentos e fixa a nota final.",
            "instrucoes": instrucoes_do_juiz(),
            "prompt": _dossie_do_juiz(d, exemplo),
            "ve": asdict(_VE_TUDO),
        }
    )
    return itens


def avaliar_com_banca(d: Dossie) -> tuple[Veredito, AtaBanca]:
    config = obter_config_banca()
    m_avaliadores = resolver_modelo(config.modelo_avaliadores)
    m_juiz = resolver_modelo(config.modelo_juiz)

    # Avaliadores em paralelo, sem ver o parecer um do outro.
    with ThreadPoolExecutor(max_workers=len(AVALIADORES)) as pool:
        opinioes = list(pool.map(lambda a: _opinar(a, d, m_avaliadores), AVALIADORES))

    notas = [o.parecer.nota for o in opinioes]
    divergencia = round(max(notas) - min(notas), 1)
    pode_perguntar = divergencia >= LIMIAR_DIVERGENCIA

    deliberacao: list[dict] = []
    perguntas_por_avaliador: dict[str, int] = {}
    ids = ", ".join(o.agente.id for o in opinioes)

    def perguntar_ao_avaliador(agente_id: str, pergunta: str) -> str:
        """Pede a um avaliador da banca um esclarecimento sobre um fato concreto da resposta do candidato.
        Não revele notas nem opiniões de outros avaliadores. No máximo uma pergunta por avaliador.

        Args:
            agente_id: id do avaliador (um de: critico, tranquilo, verificador, independente).
            pergunta: a pergunta objetiva ao avaliador (5 a 600 caracteres).
        """
        total = sum(1 for e in deliberacao if e["tipo"] == "pergunta")
        if total >= MAX_ESCLARECIMENTOS or perguntas_por_avaliador.get(agente_id, 0) >= 1:
            return json.dumps({"erro": "Limite de esclarecimentos atingido. Emita o veredito agora."})
        op = next((o for o in opinioes if o.agente.id == agente_id), None)
        if not op:
            return json.dumps({"erro": f"Avaliador desconhecido. Use um de: {ids}."})
        perguntas_por_avaliador[agente_id] = 1
        deliberacao.append({"tipo": "pergunta", "para": agente_id, "texto": pergunta[:600]})
        e = _esclarecer(op, pergunta, d, m_avaliadores)
        deliberacao.append(
            {"tipo": "esclarecimento", "de": agente_id, "texto": e.esclarecimento, "notaRevisada": e.nota_revisada}
        )
        return e.model_dump_json()

    prompt_juiz = _dossie_do_juiz(d, opinioes)
    # Sem divergência relevante, o juiz não recebe a ferramenta.
    juiz = Agent(
        model=m_juiz.instancia,
        instructions=instrucoes_do_juiz(),
        tools=[perguntar_ao_avaliador] if pode_perguntar else None,
        tool_call_limit=MAX_ESCLARECIMENTOS if pode_perguntar else None,
        output_schema=Veredito,
        markdown=False,
    )
    saida = _executar(juiz, prompt_juiz)
    _registrar("banca_juiz", m_juiz, saida, d.sessao_id)

    try:
        v = _conteudo(saida, Veredito)
    except IntegracaoError:
        # O juiz terminou sem veredito estruturado: pede de novo, sem ferramenta.
        resumo = "\n".join(
            f"Juiz → {e['para']}: {e['texto']}"
            if e["tipo"] == "pergunta"
            else f"{e['de']}: {e['texto']}" + (f" (nota revisada: {e['notaRevisada']})" if e.get("notaRevisada") is not None else "")
            for e in deliberacao
        )
        forcado = Agent(model=m_juiz.instancia, instructions=instrucoes_do_juiz(), output_schema=Veredito, markdown=False)
        saida2 = _executar(
            forcado, f"{prompt_juiz}\n\nDELIBERAÇÃO REALIZADA:\n{resumo or '(nenhuma)'}\n\nEmita agora o veredito final."
        )
        _registrar("banca_juiz_veredito", m_juiz, saida2, d.sessao_id)
        v = _conteudo(saida2, Veredito)

    nota = max(0.0, min(10.0, round(v.nota, 1)))
    veredito = Veredito(nota=nota, justificativa=v.justificativa, pontos_cobertos=v.pontos_cobertos, pontos_faltantes=v.pontos_faltantes)
    ata = AtaBanca(
        avaliadores=[
            {"agenteId": o.agente.id, "nome": o.agente.nome, "modelo": m_avaliadores.id, **o.parecer.model_dump()}
            for o in opinioes
        ],
        deliberacao=deliberacao,
        juiz={"modelo": m_juiz.id, "nota": nota},
        divergencia=divergencia,
    )
    return veredito, ata
