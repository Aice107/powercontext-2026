#!/usr/bin/env bash
# 启动 inn-api（前台）
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
exec .venv/bin/uvicorn app.main:app \
  --host "${INN_API_HOST:-0.0.0.0}" \
  --port "${INN_API_PORT:-8010}" \
  --log-level info
