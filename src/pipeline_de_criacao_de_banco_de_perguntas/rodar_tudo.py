"""Pipeline completo, sem supervisão (`bash supervisor.sh` religa sozinho se cair).

Cada vídeo despacha seu lote para a Batch API assim que é alinhado, enquanto a GPU segue no
próximo. Tudo é gravado ao chegar e os ids dos lotes ficam em batch/estado.json: retomável.
"""

import json
import os
import pathlib
import sys
import time
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
CELULAS = [("".join(c["source"]), c["cell_type"])
           for c in json.load(open("pipeline.ipynb", encoding="utf-8"))["cells"]]
code = {i: s for i, (s, t) in enumerate(CELULAS) if t == "code"}
ns = {"__name__": "__main__"}

# indices das celulas do notebook
C_CONFIG, C_CSV = 2, 4
C_BAIXAR, C_TRANSCREVER, C_DIARIZAR, C_ALINHAR = 6, 8, 10, 12
C_PAPEL, C_PARES, C_VALIDAR, C_EXTRATOR = 14, 16, 18, 20
C_PROMPTS, C_P1, C_MONTAR, C_P2P3, C_ESCREVER, C_CONFERIR = 22, 23, 25, 27, 29, 31

t_ini = time.time()


def passo(i, nome):
    t0 = time.time()
    print(f"\n{'='*72}\n### {nome}   [{time.strftime('%H:%M:%S')}]\n{'='*72}", flush=True)
    exec(compile(code[i], f"<cell {i}>", "exec"), ns)
    print(f"--- {nome}: {time.time()-t0:.0f}s "
          f"(total {(time.time()-t_ini)/60:.0f} min)", flush=True)


try:
    passo(C_CONFIG, "config")
    passo(C_CSV, "CSV")

    # Roda as células 6-12 com VIDEOS reduzido a um vídeo e acumula: processamento por vídeo
    # sem reescrever as células. A célula do papel só é executada inteira na etapa 5.
    marca = "# sentencas de todos os videos"
    assert marca in code[C_PAPEL], "a celula do papel mudou de forma"
    exec(compile(code[C_PAPEL].split(marca)[0], "<cell 14 defs>", "exec"), ns)

    # Vídeos longos são transmissões com vários candidatos: cada pedaço vira uma prova
    # própria (e transcrever 6,7 h de uma vez estourava a memória).
    LIMITE_MIN = 60          # video_4, de 70 min, passou; 60 da margem

    def duracao_min(caminho):
        import wave
        with wave.open(str(caminho)) as w:
            return w.getnframes() / w.getframerate() / 60

    def fatiar(v):
        """Lista de vídeos que substitui `v` (ele mesmo ou seus pedaços)."""
        wav = pathlib.Path(ns["DIR_AUDIO"]) / f"{v['video_id']}.wav"
        if not wav.exists():
            return [v]
        dur = duracao_min(wav)
        if dur <= LIMITE_MIN:
            return [v]
        n_partes = int(dur // LIMITE_MIN) + (1 if dur % LIMITE_MIN > 5 else 0)
        ffmpeg = str(pathlib.Path(ns["FFMPEG_DIR"]) / "ffmpeg")
        partes = []
        for k in range(n_partes):
            vid = f"{v['video_id']}_p{k+1:02d}"
            alvo = pathlib.Path(ns["DIR_AUDIO"]) / f"{vid}.wav"
            if not alvo.exists():
                subprocess.run([ffmpeg, "-v", "error", "-y",
                                "-ss", str(k * LIMITE_MIN * 60),
                                "-t", str(LIMITE_MIN * 60), "-i", str(wav),
                                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                                str(alvo)], check=True)
            if alvo.exists() and duracao_min(alvo) >= 2:      # descarta sobra minuscula
                novo = dict(v)
                novo["video_id"] = vid
                novo["audio"] = str(alvo)
                novo["observacao"] = (v.get("observacao", "") +
                                      f" | parte {k+1}/{n_partes} de {v['video_id']}")
                partes.append(novo)
        print(f"    {v['video_id']}: {dur:.0f} min -> {len(partes)} partes de "
              f"~{LIMITE_MIN} min", flush=True)
        return partes

    print(f"\n{'='*72}\n### fase 0: baixar e fatiar\n{'='*72}", flush=True)
    import subprocess
    ORIGINAIS = ns["VIDEOS"]
    EXPANDIDO = []
    for n_, v in enumerate(ORIGINAIS, 1):
        ns["VIDEOS"] = [v]
        try:
            exec(compile(code[C_BAIXAR], f"<cell {C_BAIXAR}>", "exec"), ns)
        except Exception as e:
            print(f"    PULANDO {v['video_id']} no download: {str(e)[:120]}", flush=True)
            continue
        EXPANDIDO += fatiar(ns["VIDEOS"][0])
    ns["VIDEOS"] = EXPANDIDO
    print(f"\n{len(ORIGINAIS)} videos do CSV -> {len(EXPANDIDO)} unidades de "
          f"processamento", flush=True)

    TODOS = ns["VIDEOS"]
    acum = {"brutos": {}, "falantes": {}, "alinhadas": {}, "turnados": {}}
    enviados = 0

    print(f"\n{'='*72}\n### etapas 1-4, video a video "
          f"({len(TODOS)} videos)\n{'='*72}", flush=True)

    # Marca o vídeo em curso antes de processá-lo: se o processo morrer, o próximo
    # religamento pula o culpado em vez de repetir o erro.
    F_EM_CURSO = pathlib.Path(ns["BASE"]) / "em_curso.txt"
    F_PULADOS = pathlib.Path(ns["BASE"]) / "pulados.json"

    # boot_id igual: o processo morreu com a máquina ligada (OOM, driver) e o vídeo é pulado.
    # boot_id diferente: a máquina desligou e o vídeo só precisa ser tentado de novo.
    BOOT_ID = pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()

    pulados = set(json.loads(F_PULADOS.read_text())) if F_PULADOS.exists() else set()
    if F_EM_CURSO.exists():
        conteudo = F_EM_CURSO.read_text().strip().split("|")
        culpado = conteudo[0]
        boot_marca = conteudo[1] if len(conteudo) > 1 else ""
        if culpado and boot_marca == BOOT_ID:
            pulados.add(culpado)
            F_PULADOS.write_text(json.dumps(sorted(pulados), ensure_ascii=False))
            print(f"\n!!! {culpado} derrubou o processo com a maquina ligada, "
                  f"entrou na lista de pulados", flush=True)
        elif culpado:
            print(f"\n    {culpado} estava em curso quando a maquina desligou, "
                  f"sera tentado de novo", flush=True)
        F_EM_CURSO.unlink()
    if pulados:
        print(f"    pulando {len(pulados)}: {sorted(pulados)}", flush=True)

    for n, v in enumerate(TODOS, 1):
        vid = v["video_id"]
        if vid in pulados or vid.split("_p")[0] in pulados:
            print(f"\n--- [{n}/{len(TODOS)}] {vid}: PULADO", flush=True)
            continue
        F_EM_CURSO.write_text(f"{vid}|{BOOT_ID}")
        t0 = time.time()
        print(f"\n--- [{n}/{len(TODOS)}] {vid} · {v['uf']} · {v['cargo'][:34]} "
              f"[{time.strftime('%H:%M:%S')}]", flush=True)
        ns["VIDEOS"] = [v]
        try:
            for c in (C_TRANSCREVER, C_DIARIZAR, C_ALINHAR):
                exec(compile(code[c], f"<cell {c}>", "exec"), ns)
        except Exception as e:
            # um video indisponivel ou corrompido nao pode derrubar os outros 24
            print(f"    PULANDO {vid}: {type(e).__name__}: {str(e)[:160]}", flush=True)
            F_EM_CURSO.unlink(missing_ok=True)
            continue

        for k in acum:
            acum[k].update(ns.get(k, {}))

        # despacha o lote deste video e segue, nao espera a OpenAI
        try:
            sents = ns["segmentar"](ns["alinhadas"][vid])
            reqs = ns["reqs_papel"](v, sents)
            enviados += ns["submeter_lote"](reqs, f"papel_{vid}", max_tokens=16000)
        except Exception as e:
            print(f"    envio adiado ({type(e).__name__}: {str(e)[:120]})", flush=True)

        F_EM_CURSO.unlink(missing_ok=True)      # sobreviveu: nao e o culpado
        print(f"    {vid} pronto em {time.time()-t0:.0f}s "
              f"(total {(time.time()-t_ini)/60:.0f} min)", flush=True)

    ns["VIDEOS"] = [v for v in TODOS if v["video_id"] in acum["turnados"]]
    for k, d in acum.items():
        ns[k] = d
    print(f"\n=== {len(ns['VIDEOS'])}/{len(TODOS)} videos prontos | "
          f"{enviados} requisicoes de papel ja na fila da OpenAI ===", flush=True)

    # recolhe os lotes despachados nas etapas 1-4; o que falhou é reenviado na célula seguinte
    ns["coletar_lotes"]("papel_")
    passo(C_PAPEL, "5 papel [coleta os lotes]")
    passo(C_PARES, "6 pares [LOTE]")
    passo(C_VALIDAR, "6.1 validar")
    passo(C_EXTRATOR, "8 extrator")
    passo(C_PROMPTS, "prompts")
    passo(C_P1, "p1 estruturar [LOTE]")
    passo(C_MONTAR, "9.1 montar")
    passo(C_P2P3, "p2 + p3 [LOTE]")
    passo(C_ESCREVER, "10 escrever")
    passo(C_CONFERIR, "11 conferir")

    print(f"\nPIPELINE COMPLETO em {(time.time()-t_ini)/60:.0f} min", flush=True)
    sys.exit(0)

except Exception:
    traceback.print_exc()
    print(f"\n!!! FALHOU apos {(time.time()-t_ini)/60:.0f} min", flush=True)
    print("O cache guarda tudo o que ja deu certo; o supervisor religa sozinho.",
          flush=True)
    sys.exit(1)
