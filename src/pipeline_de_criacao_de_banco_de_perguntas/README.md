# Montagem de banco de perguntas

**De uma lista de links do YouTube a um `banco_estruturado.json` pronto para o
simulador, num notebook só.**

> **Proveniência desta pasta.** Copiada de `~/projetos/tcc/montagem de banco de perguntas/`.
> O pipeline teve duas versões:
>
> - **Versão 1**, espalhada em `~/projetos/tcc/src/`: notebooks `00_local_transcricao_diarizacao`,
>   `01_atribuicao_papel`, `02_banco_perguntas` e `03_recuperar_blocos`, seguidos de
>   `estruturar_banco.py` e `montar_banco_final.py`. Foi ela que gerou as **292 questões** do
>   MPMG (10 provas, 2022-2024) que estão em `banco de questoes finais/` e alimentam o simulador.
> - **Versão 2**, esta: as mesmas etapas consolidadas em `pipeline.ipynb` e generalizadas para
>   qualquer concurso de prova oral. `rodar_tudo.py` executa as células do notebook em ordem,
>   sem supervisão, e `supervisor.sh` o religa se cair.
>
> Os scripts de pós-processamento citados em "Depois" (`deduplicar.py`, `finalizar_banco.py`,
> `juntar_banco_v1.py`) ficaram na pasta original: eles tratam a rodada multi-concurso da versão 2,
> que não entrou no simulador. As chaves de API foram retiradas do notebook nesta cópia.

```
videos.csv  →  baixar  →  transcrever  →  diarizar  →  alinhar  →  papel
            →  pares P/R  →  estruturar  →  revisar  →  corrigir  →  JSON final
```

Serve para montar banco de **qualquer concurso de prova oral**: banca, cargo e
taxonomia de matérias são parâmetros, não estão escritos no código.

---

## Uso

### Instalação

```bash
bash instalar_ambiente.sh          # cria o conda env `qbanco` e registra o kernel
conda activate qbanco
```

O pipeline usa **ambiente próprio**, separado do `tcc` que roda o simulador, por
duas razões:

1. **Isolamento.** O `pyannote.audio` traz ~28 pacotes, entre eles `torchaudio` e
   `torchcodec`. O `tcc` está funcionando; não há razão de arriscá-lo por uma
   dependência que só o pipeline usa.
2. **CUDA 12.** No `tcc` o torch trouxe CUDA 13, e o CTranslate2, backend do
   faster-whisper, procura `libcublas.so.12`. Foi o que obrigou o simulador a usar
   STT por API. Aqui o torch é fixado no build `cu124`, então **a transcrição roda na
   GPU de verdade**.

Consequência da segunda: o `pyannote.audio` fica na série 3.x, porque a 4.x exige
torch ≥ 2.8 e o build mais recente com CUDA 12 é o torch 2.6. O notebook trata as
duas APIs, então não há perda.

**Chaves.** Vêm de variáveis de ambiente, nunca do código, porque este notebook está num
repositório público:

```bash
export OPENAI_API_KEY=...   # etapas 6 a 9
export HF_TOKEN=...         # etapa 4, diarização
```

O `HF_TOKEN` só funciona depois de aceitar as condições nas **duas** páginas do pyannote:
`hf.co/pyannote/segmentation-3.0` e `hf.co/pyannote/speaker-diarization-3.1`.

> Nota: a cópia original do notebook, fora deste repositório, tinha as duas chaves escritas
> na célula de configuração. Nesta cópia elas foram removidas.

1. Preencha `videos.csv`: só a coluna `url` é obrigatória
2. Abra `pipeline.ipynb` e rode as células em ordem
3. A saída fica em `dados/saida/banco_estruturado.json`

`exemplo_mpmg.csv` traz os 10 vídeos do MPMG já preenchidos, como modelo de formato.

### O CSV de entrada

| coluna | o que é |
|---|---|
| `url` | link do YouTube (**obrigatória**) |
| `banca` | "Ministério Público de Minas Gerais", entra nos prompts |
| `cargo` | "Promotor de Justiça", entra nos prompts |
| `edicao`, `ano`, `grupo_tematico` | metadados que viajam até o JSON final |
| `colocacao` | colocação do candidato; **calibrador de qualidade, não veredito** |

---

## O que o pipeline produz

```
dados/
  audio/          video_N.wav            16 kHz mono 16-bit
  transcricoes/   *_bruto.json           segmentos + palavras com tempo e confiança
                  *_falantes.json        diarização crua (SPEAKER_XX)
                  *_palavras.json        palavras alinhadas ao falante
                  *_papeis.json          decisão examinador/candidato por sentença
                  *_final.json           turnos finais com papel
  banco/          pares_brutos.json      saída crua da extração de pares
                  banco_perguntas.json   pares validados índice a índice
  cache/          p1_*.json p2_*.json p3_*.json
  saida/          banco_estruturado.json   ← o consolidado, cru
                  UF/BANCA_cargo/PROVA_ID/q0001.json   p.ex. MT/TJMT_juiz-de-direito-substituto/MT_TJMT_JDS_2025_01
                  UF/BANCA_cargo/PROVA_ID/_prova.json  metadados e índice da prova
                  por_concurso/*.json      as questões de cada concurso
                  indice_concursos.json    provas e matérias por concurso
                  revisao_manual.csv       fila de revisão humana, priorizada
                  auditoria_citacoes.json  proveniência de cada dispositivo
  dedup/          duplicatas.json, pares.csv   (deduplicar.py)
  banco_completo_revisado/   tudo, com _meta.duplicata  (finalizar_banco.py)
  banco_melhores/            a seleção, mesma árvore   (finalizar_banco.py)
```

Ids: `prova_id = {UF}_{banca}_{cargo}_{ano}_{seq}`, com a sigla da banca pelo tipo de
órgão + UF (`TJMT`, `MPBA`, `PCSP`, `DPMG`, `TRT2`, exceções como `MPDFT` em
`nomes.py`) e o cargo por função (`PJ`, `PJS`, `PJA`, `JDS`, `JTS`, `DEL`, `DEF`).
Ano que o CSV não confirma vira `sd`: nunca um ano inventado.

O schema de `banco_estruturado.json` é **superconjunto** do que o simulador já
consome: tem todos os campos de `src/saida/`, mais `auditoria_citacoes` no `_meta` e
`origem_verificada` em cada fundamento legal.

---

## As três regras que atravessam o pipeline

**1. O modelo devolve índice, nunca texto.** Nas etapas de atribuição de papel e de
extração de pares, o LLM recebe falas numeradas e responde com números. A
transcrição jamais é reescrita. Se ele pudesse devolver texto, uma paráfrase da
resposta do candidato entraria no dataset sem deixar rastro: contaminação
irrecuperável. A validação recusa qualquer par cujo texto não venha literalmente
dos turnos de origem.

**2. A resposta gravada é gabarito, não a fala do candidato.** A transcrição é
âncora do *recorte*: indica qual doutrina e quais dispositivos o examinador queria
ouvir. O conteúdo correto vem do modelo. Onde a fala estiver errada ou incompleta, o
gabarito traz o certo, sem comentar o erro e sem mencionar o candidato.

**3. Toda etapa é cacheada em disco.** Rodar de novo continua de onde parou. Não é
conveniência: a transcrição leva horas de GPU e a estruturação gasta dinheiro de API.

---

## As cinco camadas anti-alucinação

| # | camada | onde |
|---|---|---|
| 1 | abstenção explícita permitida | `gabarito_status` pode ser "abstido" |
| 2 | proveniência por dispositivo | `origem_verificada`, conferida contra a transcrição |
| 3 | extrator determinístico de citações | tuplas canônicas, sem LLM |
| 4 | revisor cego | recebe só pergunta+resposta, **sem** a fonte |
| 5 | regeneração dirigida | reescreve só o que o revisor reprovou |

A camada 3 é a que não depende de modelo nenhum: cada citação vira uma tupla
canônica, de modo que "art. 5º da Lei 7.347/1985" e "artigo 5º da Lei da Ação Civil
Pública" colidam, e "art. 25 do Código Penal" e "art. 25 do Código Penal **português**"
não colidam.

---

## Para rodar em outro concurso

Três coisas mudam, todas no notebook:

1. **`MATERIAS`**: a taxonomia do edital. É fechada de propósito: texto livre
   produziria "Processual Penal", "Direito Processual Penal" e "Proc. Penal" como
   três categorias.
2. **`banca` e `cargo` no CSV**: entram nos prompts de todas as etapas com LLM.
3. **`PROMPT_JURIDICO`**: o vocabulário que enviesa o Whisper. Concurso de outra
   área precisa do vocabulário dela.

O resto (diarização, alinhamento palavra a palavra, atribuição de papel, blocos de
arguição, as três passadas e a auditoria) vale para qualquer prova oral com uma
banca e um candidato.

---

## Custo e tempo, por vídeo de ~90 min

| etapa | ordem de grandeza |
|---|---|
| download | 1-3 min |
| transcrição (GPU) | 10-20 min |
| diarização (GPU) | 3-5 min |
| atribuição de papel | ~20 chamadas de API |
| pares pergunta/resposta | ~30 chamadas |
| estruturar + revisar + corrigir | ~30 chamadas |

Poucos dólares por vídeo com `gpt-4o`. Tudo cacheado: reexecutar não paga de novo.

---

## Depois

**Deduplicar e selecionar as melhores**: em transmissões de dia inteiro a banca
repete a mesma pergunta para vários candidatos. Dois passos:

```bash
python deduplicar.py      # embedding acha pares candidatos; gpt-5.6-sol (Batch, 50% off) julga
python finalizar_banco.py # corrige ids, marca duplicatas, seleciona as melhores
```

`finalizar_banco.py` aplica o critério de `src/montar_banco_final.py` (elegibilidade,
score, seleção por cadeia de arguição, ordem real da prova), por prova, e de cada
grupo de pergunta repetida mantém só a cópia de maior score, cortando a cadeia da
cópia perdedora a partir dela, porque os desdobramentos seguintes dependiam dela.
Motivo de cada descarte em `banco_melhores/descartadas.csv`.

**Juntar o banco v1 do MPMG**: `python juntar_banco_v1.py`, sempre logo depois de
`finalizar_banco.py`. Acrescenta ao concurso `MG_MPMG_PJ` as 292 questões de
`src/banco de questoes finais/` e tira das novas as que já estavam lá (mesmo trecho de
áudio, mesma pergunta a outro candidato ou sobreposição parcial), conforme
`dados/dedup_vs_v1/mpmg_novo_vs_banco_v1.csv`. Resultado: 292 do v1 + 182 novas = 474.
Proveniência em `_selecao.banco_origem`; as provas do v1 guardam `prova_id_v1` e `url`.

**Carregar no simulador**: `scripts/importar_banco.py` importa e vetoriza.

**Antes de usar as questões, leia `revisao_manual.csv`.** A fila vem priorizada:
`regenerado_conferir` e `revisor_grave` primeiro, `confianca_baixa` por último. Em
rodadas anteriores ~21% das questões caíram nessa fila: é trabalho humano real, e é
o que separa um banco utilizável de um banco confiante e errado.
