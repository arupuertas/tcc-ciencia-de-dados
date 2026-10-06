"""Modelos de linguagem disponíveis. Preços em US$ por 1M tokens, só para estimar custos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .chaves import ChaveId

ProvedorLlm = Literal["maritaca", "openai"]


@dataclass(frozen=True)
class ModeloLlm:
    id: str  # `provedor:modelo`
    provedor: ProvedorLlm
    modelo: str
    nome: str
    descricao: str
    preco_entrada: float
    preco_saida: float


PROVEDORES_LLM: dict[str, dict[str, str]] = {
    "maritaca": {"nome": "Maritaca AI", "chave": "MARITACA_API_KEY"},
    "openai": {"nome": "OpenAI", "chave": "OPENAI_API_KEY"},
}


def _m(provedor: ProvedorLlm, modelo: str, nome: str, descricao: str, pe: float, ps: float) -> ModeloLlm:
    return ModeloLlm(f"{provedor}:{modelo}", provedor, modelo, nome, descricao, pe, ps)


# A Maritaca cobra em reais: convertido por esta cotação.
COTACAO_USD_BRL = 5.50


def _brl(reais: float) -> float:
    return round(reais / COTACAO_USD_BRL, 4)


MODELOS: list[ModeloLlm] = [
    _m("maritaca", "sabiazinho-4", "Sabiazinho 4", "Rápido e barato; bom para os avaliadores e o turno. R$ 1 / R$ 4 por 1M tokens.", _brl(1), _brl(4)),
    _m("maritaca", "sabia-4", "Sabiá 4", "Modelo geral da Maritaca; bom para o juiz. R$ 5 / R$ 20 por 1M tokens.", _brl(5), _brl(20)),
    _m("maritaca", "sabia-4-thinking", "Sabiá 4 Thinking", "Raciocínio; mais lento e caro. R$ 5 / R$ 40 por 1M tokens.", _brl(5), _brl(40)),
    _m("openai", "gpt-4o-mini", "GPT-4o mini", "Rápido e barato; bom para os avaliadores.", 0.15, 0.6),
    _m("openai", "gpt-4o", "GPT-4o", "Equilíbrio entre qualidade e custo.", 2.5, 10),
    _m("openai", "gpt-4.1-mini", "GPT-4.1 mini", "Sucessor do 4o mini, mais preciso.", 0.4, 1.6),
    _m("openai", "gpt-4.1", "GPT-4.1", "Forte em instruções longas.", 2, 8),
    _m("openai", "gpt-5-mini", "GPT-5 mini", "Raciocínio bom a baixo custo.", 0.25, 2),
    _m("openai", "gpt-5", "GPT-5", "Raciocínio forte; ótimo para o juiz.", 1.25, 10),
]

# Postura fica na OpenAI: os modelos Sabiá não interpretam imagem.
MODELO_PADRAO_AVALIADORES = "maritaca:sabiazinho-4"
MODELO_PADRAO_JUIZ = "maritaca:sabia-4"
MODELO_PADRAO_AUXILIAR = "maritaca:sabiazinho-4"   # classificador de turno
MODELO_PADRAO_VISAO = "openai:gpt-4o"              # leitor de postura (precisa enxergar imagem)


def separar_modelo(id: str) -> tuple[ProvedorLlm, str] | None:
    """Aceita `provedor:modelo` (inclusive IDs fora do catálogo)."""
    if not isinstance(id, str):
        return None
    i = id.find(":")
    if i <= 0:
        return None
    provedor, modelo = id[:i], id[i + 1 :].strip()
    if provedor in PROVEDORES_LLM and modelo:
        return provedor, modelo  # type: ignore[return-value]
    return None


def buscar_modelo(id: str) -> ModeloLlm | None:
    return next((m for m in MODELOS if m.id == id), None)


def nome_modelo(id: str) -> str:
    m = buscar_modelo(id)
    if m:
        return m.nome
    partes = separar_modelo(id)
    return partes[1] if partes else id


def chave_do_provedor(provedor: str) -> ChaveId:
    return PROVEDORES_LLM[provedor]["chave"]  # type: ignore[return-value]
