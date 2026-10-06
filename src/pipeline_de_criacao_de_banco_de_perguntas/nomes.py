"""Siglas de banca e de cargo para os ids de prova e de concurso.

A sigla sai do tipo de órgão mais a UF (MPMG, TJMT, PCSP), com uma tabela para exceções;
iniciais do nome erravam ("Tribunal de Justiça de Mato Grosso" virava TJMG).
"""

import re
import unicodedata

ESTADOS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso do sul": "MS", "mato grosso": "MT",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}

# nomes proprios que a regra por tipo de orgao nao cobre
EXCECOES_BANCA = {
    "ministerio publico do distrito federal e territorios": "MPDFT",
    "ministerio publico federal": "MPF",
    "ministerio publico do trabalho": "MPT",
    "ministerio publico militar": "MPM",
    "defensoria publica da uniao": "DPU",
    "policia federal": "PF",
    "advocacia-geral da uniao": "AGU",
    "tribunal de justica do distrito federal e territorios": "TJDFT",
}

# o mais especifico primeiro: "substituto" antes do cargo base
CARGOS = [
    (r"promotor.*adjunto", "PJA"),
    (r"promotor.*substituto", "PJS"),
    (r"promotor", "PJ"),
    (r"procurador.*republica", "PR"),
    (r"procurador.*estado", "PE"),
    (r"procurador", "PROC"),
    (r"juiz.*trabalho", "JTS"),
    (r"juiz federal", "JFS"),
    (r"juiz.*substituto", "JDS"),
    (r"juiz", "JD"),
    (r"delegado", "DEL"),
    (r"defensor", "DEF"),
]


def _limpo(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def uf_do_nome(texto: str) -> str | None:
    t = _limpo(texto)
    for nome in sorted(ESTADOS, key=len, reverse=True):   # "mato grosso do sul" antes
        if nome in t:
            return ESTADOS[nome]
    return None


def sigla_banca(banca: str, uf: str | None = None) -> str:
    t = _limpo(banca)
    if t in EXCECOES_BANCA:
        return EXCECOES_BANCA[t]
    uf = uf_do_nome(banca) or uf or ""

    regiao = re.search(r"(\d+)\s*[ªa]?\s*regiao", t)
    if "tribunal regional do trabalho" in t and regiao:
        return f"TRT{regiao.group(1)}"
    if "tribunal regional federal" in t and regiao:
        return f"TRF{regiao.group(1)}"

    for prefixo, sigla in (("tribunal de justica", "TJ"), ("ministerio publico", "MP"),
                           ("defensoria publica", "DP"), ("policia civil", "PC"),
                           ("procuradoria-geral do estado", "PGE"),
                           ("procuradoria geral do estado", "PGE")):
        if t.startswith(prefixo):
            return f"{sigla}{uf}"

    # fallback: iniciais das palavras significativas
    menores = {"de", "do", "da", "dos", "das", "e", "a", "o"}
    return "".join(w[0] for w in re.split(r"[\s/-]+", t)
                   if w and w not in menores).upper()[:8] or "BANCA"


def sigla_cargo(cargo: str) -> str:
    t = _limpo(cargo)
    for padrao, sigla in CARGOS:
        if re.search(padrao, t):
            return sigla
    return "".join(w[0] for w in t.split() if len(w) > 2).upper()[:5] or "CARGO"


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _limpo(texto)).strip("-")


if __name__ == "__main__":
    for b, c in [
        ("Ministério Público de Minas Gerais", "Promotor de Justiça"),
        ("Tribunal de Justiça de Mato Grosso", "Juiz de Direito Substituto"),
        ("Ministério Público de Santa Catarina", "Promotor de Justiça Substituto"),
        ("Polícia Civil do Estado de São Paulo", "Delegado de Polícia"),
        ("Ministério Público do Distrito Federal e Territórios", "Promotor de Justiça Adjunto"),
        ("Ministério Público do Estado da Bahia", "Promotor de Justiça Substituto"),
        ("Ministério Público de São Paulo", "Promotor de Justiça"),
        ("Defensoria Pública do Estado de Minas Gerais", "Defensor Público"),
        ("Tribunal de Justiça de Santa Catarina", "Juiz de Direito Substituto"),
        ("Tribunal Regional do Trabalho da 2ª Região", "Juiz do Trabalho Substituto"),
    ]:
        print(f"{sigla_banca(b):6} {sigla_cargo(c):4}  {b} | {c}")
