#!/usr/bin/env bash
# Cria o ambiente conda do pipeline de montagem de banco de perguntas.
#
#   bash instalar_ambiente.sh
#
# Ambiente separado: o pyannote traz muitas dependências, e o faster-whisper (CTranslate2)
# exige CUDA 12, por isso o torch fica fixado no build cu124. O pyannote fica na série 3.x
# porque a 4.x exige torch >= 2.8, sem build para CUDA 12.

set -euo pipefail

ENV_NOME="${1:-qbanco}"
TORCH_CUDA="https://download.pytorch.org/whl/cu124"

echo "==> ambiente: ${ENV_NOME}"

eval "$(conda shell.bash hook)"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NOME}"; then
    echo "    já existe; reaproveitando"
else
    conda create -y -n "${ENV_NOME}" python=3.12
fi
conda activate "${ENV_NOME}"

echo "==> torch + torchaudio com CUDA 12 (o que o CTranslate2 procura)"
pip install --quiet torch==2.6.0 torchaudio==2.6.0 --index-url "${TORCH_CUDA}"

echo "==> diarização (pyannote 3.x, compatível com torch 2.6)"
pip install --quiet "pyannote.audio>=3.3,<4"

# O pyannote 3.x passa `use_auth_token`, removido no huggingface_hub 1.x: daí o pino.
pip install --quiet "huggingface_hub<1.0"

echo "==> transcrição, download, LLM e notebook"
pip install --quiet \
    faster-whisper \
    openai \
    yt-dlp \
    imageio-ffmpeg \
    pandas \
    tqdm \
    jupyterlab \
    ipykernel

echo "==> registrando o kernel para o Jupyter/VS Code"
python -m ipykernel install --user --name "${ENV_NOME}" \
       --display-name "Python (${ENV_NOME})"

echo
echo "==> conferindo"
python - <<'PY'
import importlib.metadata as md
import importlib.util as u

for pkg, mod in [("torch", "torch"), ("torchaudio", "torchaudio"),
                 ("pyannote.audio", "pyannote"), ("faster-whisper", "faster_whisper"),
                 ("openai", "openai"), ("yt-dlp", "yt_dlp"),
                 ("imageio-ffmpeg", "imageio_ffmpeg"), ("jupyterlab", "jupyterlab")]:
    ok = u.find_spec(mod) is not None
    try:
        v = md.version(pkg)
    except Exception:
        v = "-"
    print(f"  {'OK   ' if ok else 'FALTA'} {pkg:16} {v}")

import torch
print(f"\n  CUDA disponível : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  GPU             : {torch.cuda.get_device_name(0)}")
print(f"  torch compilado com CUDA {torch.version.cuda}")

# o teste que importa: o CTranslate2 acha a libcublas?
try:
    from faster_whisper import WhisperModel
    WhisperModel("tiny", device="cuda", compute_type="float16")
    print("  faster-whisper na GPU: OK")
except Exception as e:
    print(f"  faster-whisper na GPU: FALHOU: {str(e)[:120]}")
PY

echo
echo "Pronto. Para usar:"
echo "    conda activate ${ENV_NOME}"
echo "    cd \"\$(dirname \"\$0\")\" && jupyter lab pipeline.ipynb"
echo "No VS Code, escolha o kernel \"Python (${ENV_NOME})\"."
