#!/usr/bin/env bash
# 一键启动：向量服务 + PowerContext Server + 主应用
# 前置：已完成 scripts/setup.sh（依赖与模型就绪）
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [ -x "../.venv-app/bin/python" ]; then PYTHON=../.venv-app/bin/python; fi
export PYTHON

EMBED_PORT="${GEWU_EMBED_PORT:-8710}"
APP_PORT="${GEWU_PORT:-8712}"

echo "== 1/3 向量服务 (:$EMBED_PORT) =="
if curl -sf -m 2 "http://127.0.0.1:$EMBED_PORT/health" >/dev/null; then
  echo "已在运行"
else
  PYTHONPATH="$ROOT" nohup "$PYTHON" -m app.embed_server >>"$ROOT/.data/embed_server.log" 2>&1 &
  for _ in $(seq 1 30); do
    sleep 2
    curl -sf -m 2 "http://127.0.0.1:$EMBED_PORT/health" >/dev/null && break
  done
  curl -sf -m 2 "http://127.0.0.1:$EMBED_PORT/health" >/dev/null && echo "就绪" || { echo "启动失败，见 .data/embed_server.log"; exit 1; }
fi

echo "== 2/3 PowerContext Server (:8000) =="
bash scripts/pc_service.sh start

echo "== 3/3 主应用 (:$APP_PORT) =="
if curl -sf -m 2 "http://127.0.0.1:$APP_PORT/api/health" >/dev/null; then
  echo "已在运行"
else
  PYTHONPATH="$ROOT" nohup "$PYTHON" -m app.server >>"$ROOT/.data/app_server.log" 2>&1 &
  for _ in $(seq 1 30); do
    sleep 2
    curl -sf -m 2 "http://127.0.0.1:$APP_PORT/api/health" >/dev/null && break
  done
  curl -sf -m 2 "http://127.0.0.1:$APP_PORT/api/health" >/dev/null && echo "就绪" || { echo "启动失败，见 .data/app_server.log"; exit 1; }
fi

echo
echo "全部就绪："
echo "  应用界面    http://127.0.0.1:$APP_PORT/"
echo "  PowerContext http://127.0.0.1:8000/health/ready"
echo "  向量服务    http://127.0.0.1:$EMBED_PORT/health"
