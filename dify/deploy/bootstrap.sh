#!/usr/bin/env bash
# 一键启动依赖（seekdb + inn-api）并自检；需要已安装 seekdb 客户端与 mysql
# 用法：SEEKDB_BIN=/path/to/seekdb bash deploy/bootstrap.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

SEEKDB_BIN="${SEEKDB_BIN:-./seekdb}"
SEEKDB_DATA="${SEEKDB_DATA:-$ROOT/.seekdb-data}"
SEEKDB_PORT="${SEEKDB_PORT:-2891}"
API_PORT="${INN_API_PORT:-8010}"

echo "[1/4] seekdb"
if ! (command -v ss >/dev/null && ss -lnt | grep -q ":${SEEKDB_PORT} "); then
  mkdir -p "$SEEKDB_DATA"
  nohup "$SEEKDB_BIN" --base-dir "$SEEKDB_DATA" --port "$SEEKDB_PORT" --nodaemon \
    --parameter memory_budget=2G --parameter log_disk_size=2G > "$SEEKDB_DATA/seekdb.out" 2>&1 &
  echo "  启动中，等待 60s…"
  for i in $(seq 1 30); do
    ss -lnt | grep -q ":${SEEKDB_PORT} " && break
    sleep 2
  done
fi
ss -lnt | grep -q ":${SEEKDB_PORT} " && echo "  seekdb up :${SEEKDB_PORT}" || { echo "  seekdb 启动失败"; exit 1; }

echo "[2/4] 初始化数据"
SEEKDB_PORT="$SEEKDB_PORT" bash db/init.sh

echo "[3/4] inn-api"
cd backend
[ -d .venv ] || { uv venv .venv --python 3.12 && uv pip install -r requirements.txt; }
[ -f .env ] || cp .env.example .env
if ! (command -v ss >/dev/null && ss -lnt | grep -q ":${API_PORT} "); then
  nohup bash run.sh > ../evidence/logs/inn-api.log 2>&1 &
  sleep 6
fi
cd ..

echo "[4/4] 自检"
curl -s "http://127.0.0.1:${API_PORT}/healthz" || { echo "  inn-api 未就绪"; exit 1; }
echo
echo "完成。下一步：在 Dify 导入 dsl/01_inn_chatflow.yml，并把 HTTP 节点地址改成 http://<host>:${API_PORT}"
