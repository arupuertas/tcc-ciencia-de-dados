"""Configurações do painel, guardadas na coleção `configuracoes`."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from .config import inteiro_ambiente
from .db import T, agora_iso
from .modelos import (
    MODELO_PADRAO_AUXILIAR,
    MODELO_PADRAO_AVALIADORES,
    MODELO_PADRAO_JUIZ,
    MODELO_PADRAO_VISAO,
    separar_modelo,
)
from .personas import PADRAO, REGRAS_SAIDA_AVALIADOR

TTL_S = 30
_cache: dict[str, tuple[Any, float]] = {}


def _com_cache(chave: str, ler):
    agora = time.time()
    guardado = _cache.get(chave)
    if guardado and agora - guardado[1] < TTL_S:
        return guardado[0]
    valor = ler()
    _cache[chave] = (valor, agora)
    return valor


def _ler(chave: str) -> dict:
    registro = T("configuracoes").obter(chave)
    valor = registro.get("valor") if registro else None
    return valor if isinstance(valor, dict) else {}


def _salvar(chave: str, valor: dict) -> None:
    T("configuracoes").salvar({"id": chave, "valor": valor, "updated_at": agora_iso()})
    _cache.pop(chave, None)


VOZ_PADRAO = "onyx"


@dataclass
class ConfigAvaliador:
    voz: str


def obter_config_avaliador() -> ConfigAvaliador:
    def ler():
        v = _ler("avaliador")
        return ConfigAvaliador(voz=(v.get("voz") or "").strip() or VOZ_PADRAO)

    return _com_cache("avaliador", ler)


def salvar_config_avaliador(config: ConfigAvaliador) -> ConfigAvaliador:
    config = ConfigAvaliador(voz=config.voz.strip() or VOZ_PADRAO)
    _salvar("avaliador", asdict(config))
    return config


@dataclass
class ConfigBanca:
    modelo_avaliadores: str
    modelo_juiz: str
    # classificador de turno
    modelo_auxiliar: str = MODELO_PADRAO_AUXILIAR
    # leitor de postura: precisa enxergar imagem
    modelo_visao: str = MODELO_PADRAO_VISAO


def obter_config_banca() -> ConfigBanca:
    def ler():
        v = _ler("banca")

        def valido(x):
            return x if isinstance(x, str) and separar_modelo(x) else None

        return ConfigBanca(
            modelo_avaliadores=valido(v.get("modeloAvaliadores")) or MODELO_PADRAO_AVALIADORES,
            modelo_juiz=valido(v.get("modeloJuiz")) or MODELO_PADRAO_JUIZ,
            modelo_auxiliar=valido(v.get("modeloAuxiliar")) or MODELO_PADRAO_AUXILIAR,
            modelo_visao=valido(v.get("modeloVisao")) or MODELO_PADRAO_VISAO,
        )

    return _com_cache("banca", ler)


def salvar_config_banca(config: ConfigBanca) -> ConfigBanca:
    for m in (config.modelo_avaliadores, config.modelo_juiz, config.modelo_auxiliar, config.modelo_visao):
        if not separar_modelo(m):
            raise ValueError(f"Modelo inválido: {m}. Use o formato provedor:modelo (ex.: openai:gpt-4o).")
    _salvar(
        "banca",
        {
            "modeloAvaliadores": config.modelo_avaliadores,
            "modeloJuiz": config.modelo_juiz,
            "modeloAuxiliar": config.modelo_auxiliar,
            "modeloVisao": config.modelo_visao,
        },
    )
    return config


MIN_PERSONA = 40
MAX_PERSONA = 6000


@dataclass
class ConfigPrompts:
    """Prompts em vigor por id de agente. Vazio ou ausente = padrão de `simulador.personas`."""

    personas: dict[str, str]
    regras_saida: str

    def texto(self, agente_id: str) -> str:
        return (self.personas.get(agente_id) or "").strip() or PADRAO.get(agente_id, "")

    def editado(self, agente_id: str) -> bool:
        atual = (self.personas.get(agente_id) or "").strip()
        return bool(atual) and atual != PADRAO.get(agente_id, "").strip()


def obter_config_prompts() -> ConfigPrompts:
    def ler():
        try:
            v = _ler("prompts")
        except Exception as e:  # noqa: BLE001 (sem banco, a banca avalia com os prompts padrão)
            print(f"[config_app] não consegui ler os prompts salvos, usando o padrão: {e}")
            return ConfigPrompts(personas={}, regras_saida=REGRAS_SAIDA_AVALIADOR)
        personas = v.get("personas") if isinstance(v.get("personas"), dict) else {}
        regras = str(v.get("regrasSaida") or "").strip()
        return ConfigPrompts(
            personas={k: str(t).strip() for k, t in personas.items() if str(t).strip()},
            regras_saida=regras or REGRAS_SAIDA_AVALIADOR,
        )

    return _com_cache("prompts", ler)


def salvar_config_prompts(config: ConfigPrompts) -> ConfigPrompts:
    personas: dict[str, str] = {}
    for agente_id, texto in config.personas.items():
        if agente_id not in PADRAO:
            raise ValueError(f"Agente desconhecido: {agente_id}.")
        t = (texto or "").strip()
        if not t:
            continue  # vazio = volta ao padrão
        if len(t) < MIN_PERSONA:
            raise ValueError(f"O prompt de '{agente_id}' está curto demais (mínimo {MIN_PERSONA} caracteres).")
        if len(t) > MAX_PERSONA:
            raise ValueError(f"O prompt de '{agente_id}' passa de {MAX_PERSONA} caracteres.")
        personas[agente_id] = t
    regras = (config.regras_saida or "").strip()
    if len(regras) > MAX_PERSONA:
        raise ValueError(f"As regras de saída passam de {MAX_PERSONA} caracteres.")
    _salvar("prompts", {"personas": personas, "regrasSaida": regras})
    return obter_config_prompts()


def redefinir_prompts() -> ConfigPrompts:
    _salvar("prompts", {"personas": {}, "regrasSaida": ""})
    return obter_config_prompts()


@dataclass
class ConfigLimites:
    max_sessoes: int
    max_sessoes_por_ip: int
    max_inicios_por_hora: int
    minutos_sem_sinal: int


LIMITES_FAIXA = {
    "max_sessoes": (1, 10000),
    "max_sessoes_por_ip": (1, 1000),
    "max_inicios_por_hora": (1, 10000),
    "minutos_sem_sinal": (3, 240),
}

_CHAVES_JSON = {
    "max_sessoes": "maxSessoes",
    "max_sessoes_por_ip": "maxSessoesPorIp",
    "max_inicios_por_hora": "maxIniciosPorHora",
    "minutos_sem_sinal": "minutosSemSinal",
}


def limites_padrao() -> ConfigLimites:
    """Padrões vindos dos secrets ou fixos; o valor salvo no painel tem prioridade."""
    return ConfigLimites(
        max_sessoes=inteiro_ambiente("SIMULADOR_MAX_SESSOES", 50),
        max_sessoes_por_ip=inteiro_ambiente("SIMULADOR_MAX_SESSOES_IP", 10),
        max_inicios_por_hora=inteiro_ambiente("SIMULADOR_MAX_INICIOS_HORA", 30),
        minutos_sem_sinal=inteiro_ambiente("SIMULADOR_MINUTOS_SEM_SINAL", 15),
    )


def _dentro_da_faixa(campo: str, v) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    mn, mx = LIMITES_FAIXA[campo]
    return n if mn <= n <= mx else None


def obter_config_limites() -> ConfigLimites:
    def ler():
        padrao = limites_padrao()
        v = _ler("limites")
        return ConfigLimites(
            **{campo: _dentro_da_faixa(campo, v.get(_CHAVES_JSON[campo])) or getattr(padrao, campo) for campo in LIMITES_FAIXA}
        )

    return _com_cache("limites", ler)


def salvar_config_limites(config: ConfigLimites) -> ConfigLimites:
    for campo in LIMITES_FAIXA:
        if _dentro_da_faixa(campo, getattr(config, campo)) is None:
            raise ValueError(f"Valor fora da faixa para {campo}.")
    _salvar("limites", {_CHAVES_JSON[c]: getattr(config, c) for c in LIMITES_FAIXA})
    return config
