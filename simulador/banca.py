"""Tipos e regras da banca. A execução está em `simulador.agentes`."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class VisaoAvaliador:
    """O que cada avaliador vê do dossiê."""

    gabarito: bool
    base_conhecimento: bool
    pontos_chave: bool
    fundamentos: bool


@dataclass(frozen=True)
class AgenteAvaliador:
    id: str
    nome: str
    descricao: str
    ve: VisaoAvaliador


class ParecerAvaliador(BaseModel):
    nota: float = Field(ge=0, le=10)
    parecer: str = Field(min_length=1)
    pontos_cobertos: list[str]
    pontos_faltantes: list[str]
    alertas: list[str]


class Esclarecimento(BaseModel):
    esclarecimento: str = Field(min_length=1)
    nota_revisada: float | None = Field(default=None, ge=0, le=10)


class Veredito(BaseModel):
    nota: float = Field(ge=0, le=10)
    justificativa: str = Field(min_length=1)
    pontos_cobertos: list[str]
    pontos_faltantes: list[str]


@dataclass
class Dossie:
    pergunta: str
    resposta_padrao: str
    transcricao: str
    contexto: list[str]
    pontos_chave: list[str]
    fundamentos_legais: list[str]
    materia: str | None = None
    tema: str | None = None
    sessao_id: str | None = None


@dataclass
class AtaBanca:
    """Ata da deliberação, guardada em `respostas.pareceres`."""

    avaliadores: list[dict]
    deliberacao: list[dict]
    juiz: dict
    divergencia: float

    def para_json(self) -> dict:
        return asdict(self)


LIMIAR_DIVERGENCIA = 1.5
MAX_ESCLARECIMENTOS = 3

AVALIADORES: list[AgenteAvaliador] = [
    AgenteAvaliador(
        id="critico",
        nome="Avaliador crítico",
        descricao="Rigoroso: cobra precisão técnica e fundamentação.",
        ve=VisaoAvaliador(gabarito=True, base_conhecimento=False, pontos_chave=True, fundamentos=True),
    ),
    AgenteAvaliador(
        id="tranquilo",
        nome="Avaliador tranquilo",
        descricao="Valoriza raciocínio e clareza; distingue lacuna de erro.",
        ve=VisaoAvaliador(gabarito=True, base_conhecimento=False, pontos_chave=True, fundamentos=False),
    ),
    AgenteAvaliador(
        id="verificador",
        nome="Verificador da base",
        descricao="Compara afirmação por afirmação com a base de conhecimento.",
        ve=VisaoAvaliador(gabarito=True, base_conhecimento=True, pontos_chave=False, fundamentos=True),
    ),
    AgenteAvaliador(
        id="independente",
        nome="Jurista independente",
        descricao="Não vê gabarito nem base: julga só com o próprio conhecimento.",
        ve=VisaoAvaliador(gabarito=False, base_conhecimento=False, pontos_chave=False, fundamentos=False),
    ),
]

JUIZ_ID = "juiz"
JUIZ_NOME = "Juiz da banca"


def nome_agente(id: str) -> str:
    if id == JUIZ_ID:
        return JUIZ_NOME
    return next((a.nome for a in AVALIADORES if a.id == id), id)