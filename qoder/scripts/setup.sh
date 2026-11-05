#!/usr/bin/env bash
# 环境准备：python 依赖 + 本地向量模型（从 hf-mirror 下载，无需任何 API Key）
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV=../.venv-app

echo "== 1/2 python 依赖 =="
if [ ! -x "$VENV/bin/python" ]; then
  command -v uv >/dev/null && uv venv --python 3.12 "$VENV"
  "$VENV/bin/python" -m ensurepip 2>/dev/null || true
fi
if command -v uv >/dev/null; then
  uv pip install --python "$VENV/bin/python" \
    "powercontext[server,client,cli,seekdb]==1.5.0" \
    pylibseekdb==1.4.0.post2 pyobvector pymysql \
    "fastapi>=0.115" "uvicorn>=0.30" httpx onnxruntime tokenizers numpy
else
  "$VENV/bin/pip" install \
    "powercontext[server,client,cli,seekdb]==1.5.0" \
    pylibseekdb==1.4.0.post2 pyobvector pymysql \
    "fastapi>=0.115" "uvicorn>=0.30" httpx onnxruntime tokenizers numpy
fi

echo "== 2/2 本地向量模型 =="
MODEL_DIR="$ROOT/.data/models/bge-small-zh-v1.5-onnx"
mkdir -p "$MODEL_DIR"
BASE="${HF_ENDPOINT:-https://hf-mirror.com}/Xenova/bge-small-zh-v1.5/resolve/main"
for f in model.onnx tokenizer.json tokenizer_config.json config.json; do
  if [ ! -s "$MODEL_DIR/$f" ]; then
    echo "下载 $f ..."
    curl -fL --retry 3 -o "$MODEL_DIR/$f" "$BASE/onnx/$f" 2>/dev/null || curl -fL --retry 3 -o "$MODEL_DIR/$f" "$BASE/$f"
  fi
done
ls -la "$MODEL_DIR"

echo "依赖与模型就绪。下一步：bash scripts/run_all.sh"
