"""Lógica pura do núcleo: sequência da arguição, vícios, cifra e conversão do banco de questões."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Chave fora do secrets.toml, que o Streamlit exporta para o ambiente.
os.environ.setdefault("CHAVES_CRIPTO_SECRET", "segredo-de-teste")

from simulador.banco_questoes import converter_banco_questoes  # noqa: E402
from simulador.ia import eco_do_prompt  # noqa: E402
from simulador.segredos import cifrar, decifrar  # noqa: E402
from simulador.simulacao import montar_sequencia, resumir_postura  # noqa: E402
from simulador.vicios import detectar_vicios, ranquear_vicios, resumir_vicios, somar_vicios  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _perguntas():
    spec = [("inicio", None), ("inicio", "a"), ("inicio", "a"), ("meio", None), ("meio", "b"), ("meio", "b"), ("meio", None), ("fim", None), ("fim", None)]
    return [{"id": str(i), "sequencia": s, "ordem": i, "cadeia": c} for i, (s, c) in enumerate(spec)]


def test_sequencia_respeita_momentos_e_cadeias():
    ids = [p["id"] for p in montar_sequencia(_perguntas(), 5)]
    assert ids == ["0", "3", "4", "5", "7"]
    assert [p["id"] for p in montar_sequencia(_perguntas(), 2)] == ["0", "7"]
    assert len(montar_sequencia(_perguntas(), 30)) == 9
    assert montar_sequencia([], 5) == []


def test_vicios():
    c = detectar_vicios("Então, né, tipo assim, eu acho que, na verdade, ok, então... éééé")
    assert c == {"então": 2, "né": 1, "tipo": 1, "na verdade": 1, "ok": 1, "é... / hum": 1}
    total = somar_vicios([c, {"né": 3}, None])
    assert total["né"] == 4
    assert ranquear_vicios(total)[0]["termo"] == "né"
    assert "vícios de linguagem" in resumir_vicios(total)
    assert resumir_vicios({}) is None


def test_vicios_hesitacao_e_palavras_comuns():
    # Transcrição real de um teste: o Whisper escreve a hesitação como "é...".
    fala = "É... é... é... aham... então, né... é... eu acho que é pela... é... resultado morte."
    assert detectar_vicios(fala) == {"é... / hum": 6, "então": 1, "né": 1}
    assert detectar_vicios("É, é, é culpado.") == {"é... / hum": 2}
    assert detectar_vicios("Ah... hum, eh, hmm, uhum. Ah, sim.") == {"é... / hum": 5}
    assert detectar_vicios("O tipo penal é claro, bom dia, é certo que ele sabe.") == {}
    assert detectar_vicios("Né? Bom, tipo, certo? Entendeu?") == {"né": 1, "bom...": 1, "tipo": 1, "certo?": 1, "entende?": 1}
    assert detectar_vicios("Eu, deixa eu ver, talvez eu analisaria") == {"deixa eu ver": 1}


def test_eco_do_prompt_da_transcricao():
    # sem fala, o Whisper pode devolver pedaços do prompt de hesitações
    assert eco_do_prompt("É... é... eu acho que...")
    assert not eco_do_prompt("É... é... sim, adotaria.")
    assert not eco_do_prompt("")


def test_cifra_ida_e_volta():
    c = cifrar("sk-abc")
    assert c.startswith("v1:") and decifrar(c) == "sk-abc"


def test_postura_resumo():
    assert resumir_postura([]) is None
    txt = resumir_postura([{"nervosismo": 8, "confianca": 3, "lendo": True}, {"nervosismo": 7, "confianca": 2, "lendo": False}])
    assert "nervosismo acentuado" in txt and "Faltou confiança" in txt and "1 de 2" in txt


def test_converte_banco_real():
    raw = json.loads((RAIZ / "banco de questoes finais" / "banco_final.json").read_text(encoding="utf-8"))
    itens, resumo = converter_banco_questoes(raw)
    assert resumo.total == 292 and len(resumo.grupos) == 10 and not resumo.ignoradas
    assert resumo.momentos == {"inicio": 70, "meio": 147, "fim": 75}
    assert itens[0].grupo == 1 and itens[0].sequencia == "inicio" and itens[0].pontos_chave
