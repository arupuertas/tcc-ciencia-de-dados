#!/usr/bin/env bash
# Religa o pipeline se ele cair (OOM, queda de internet, sessão encerrada). Como tudo é
# retomável, rodar de novo continua de onde parou, sem repagar.
#
#   nohup bash supervisor.sh > supervisor.log 2>&1 &

set -u
cd "$(dirname "$0")"

PY="/home/aruapc/miniforge3/envs/qbanco/bin/python"
MAX_TENTATIVAS=200          # teto de seguranca contra laco infinito
ESPERA_INICIAL=30           # s; dobra a cada falha, ate o teto
ESPERA_MAX=600

tentativa=1
espera=$ESPERA_INICIAL

while [ "$tentativa" -le "$MAX_TENTATIVAS" ]; do
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  tentativa $tentativa  |  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "════════════════════════════════════════════════════════════════"

    # espera a internet voltar para não queimar tentativas
    for _ in $(seq 1 60); do
        if curl -s --max-time 10 -o /dev/null https://api.openai.com/v1/models; then
            break
        fi
        echo "  [$(date '+%H:%M:%S')] sem internet; nova checagem em 30s"
        sleep 30
    done

    "$PY" -u rodar_tudo.py
    codigo=$?

    if [ "$codigo" -eq 0 ]; then
        echo ""
        echo "PIPELINE CONCLUIDO em $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Saida em dados/saida/"
        exit 0
    fi

    echo "  saiu com codigo $codigo; religando em ${espera}s"
    sleep "$espera"
    espera=$(( espera * 2 ))
    [ "$espera" -gt "$ESPERA_MAX" ] && espera=$ESPERA_MAX
    tentativa=$(( tentativa + 1 ))
done

echo "FALHOU apos $MAX_TENTATIVAS tentativas: algo estrutural esta errado."
exit 1
