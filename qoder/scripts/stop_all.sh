#!/usr/bin/env bash
# 停止全部服务
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
[ -x "$ROOT/../.venv-app/bin/python" ] && PYTHON="$ROOT/../.venv-app/bin/python"
bash "$(dirname "$0")/pc_service.sh" stop || true
pkill -f "app.embed_serve[r]" 2>/dev/null && echo "[embed] stopped" || echo "[embed] not running"
pkill -f "app.serve[r]" 2>/dev/null && echo "[app] stopped" || echo "[app] not running"
exit 0
