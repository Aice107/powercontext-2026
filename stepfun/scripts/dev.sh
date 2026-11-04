#!/usr/bin/env bash
# 一键启动：seekdb（本地 server）→ API 服务 → Vite 开发服务器
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export SEEKDB_PORT="${SEEKDB_PORT:-2895}"
export PORT="${PORT:-5177}"

echo "== 1/3 启动 seekdb =="
bash scripts/seekdb_server.sh start || {
  echo "seekdb 启动失败：请先安装 pylibseekdb 或设置 SEEKDB_BIN" >&2
  exit 1
}

echo "== 2/3 启动 API 服务 (:$PORT) =="
node server/index.mjs &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 40); do
  if curl -s "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

echo "== 3/3 启动前端 (http://127.0.0.1:5178) =="
node scripts/prepare_ort.mjs
npx vite --config web/vite.config.ts
