"""Remove do banco de questões os dados pessoais dos candidatos.

Saem a fala transcrita, a referência ao vídeo, a colocação e a reação do examinador; `bloco_id`
vira um identificador opaco, preservando as cadeias.

Uso:
  python db/anonimizar_banco.py            # só mostra o diagnóstico
  python db/anonimizar_banco.py --aplicar  # reescreve os arquivos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "banco de questoes finais"

REMOVER = {
    "pergunta_transcrita",
    "resposta_transcrita",
    "resumo_resposta",
    "resumo_resposta_real",
    "video_id",
    "pergunta_id",
    "inicio",
    "fim",
    "colocacao",
    "colocacao_candidato",
    "reacao_examinador",
    "prob_media_resposta",
}
OPACOS = {"bloco_id", "bloco_origem", "cadeia"}


def opaco(valor: str) -> str:
    return "cadeia_" + hashlib.sha256(f"cadeia:{valor}".encode()).hexdigest()[:10]


def limpar(o, contagem: dict[str, int]):
    if isinstance(o, dict):
        saida = {}
        for k, v in o.items():
            if k in REMOVER:
                contagem[k] = contagem.get(k, 0) + 1
                continue
            if k in OPACOS and isinstance(v, str) and v and not v.startswith("cadeia_"):
                contagem[k] = contagem.get(k, 0) + 1
                saida[k] = opaco(v)
                continue
            saida[k] = limpar(v, contagem)
        return saida
    if isinstance(o, list):
        return [limpar(v, contagem) for v in o]
    return o


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="reescreve os arquivos (sem isso, só mostra o diagnóstico)")
    args = p.parse_args()

    arquivos = sorted(PASTA.rglob("*.json"))
    if not arquivos:
        sys.exit(f"Nenhum JSON em {PASTA}")

    contagem: dict[str, int] = {}
    alterados = 0
    for f in arquivos:
        original = f.read_text(encoding="utf-8")
        dados = json.loads(original)
        limpo = json.dumps(limpar(dados, contagem), ensure_ascii=False, indent=2) + "\n"
        if limpo != original:
            alterados += 1
            if args.aplicar:
                f.write_text(limpo, encoding="utf-8")

    print(f"{len(arquivos)} arquivos lidos, {alterados} com dado pessoal.")
    for campo, n in sorted(contagem.items(), key=lambda x: -x[1]):
        acao = "opaco" if campo in OPACOS else "removido"
        print(f"  {campo:22} {n:5} ocorrências ({acao})")
    print("\nArquivos reescritos." if args.aplicar else "\nNada alterado. Rode com --aplicar.")


if __name__ == "__main__":
    main()
