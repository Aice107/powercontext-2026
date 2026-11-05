#!/usr/bin/env bash
# 停止 / 启动 PowerContext Server（必须从 submission/qoder 目录运行）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

stop() {
  local pids
  pids=$(pgrep -f "bin/powercontext serve[r] run" || true)
  if [ -n "$pids" ]; then
    echo "[pc] stopping: $pids"
    kill $pids 2>/dev/null || true
    sleep 3
  else
    echo "[pc] not running"
  fi
}

start() {
  cd "$ROOT"
  local log="$ROOT/.data/pc-server.log"
  mkdir -p "$ROOT/.data"
  local bin
  bin="$(dirname "$PY")/powercontext"
  [ -x "$bin" ] || bin="$PY -m powercontext.cli"
  if [ -x "$bin" ]; then
    nohup "$bin" server run --env-file deploy/powercontext.env >>"$log" 2>&1 &
  else
    nohup $bin server run --env-file deploy/powercontext.env >>"$log" 2>&1 &
  fi
  echo "[pc] starting, log: $log"
  for _ in $(seq 1 60); do
    sleep 2
    if curl -sf -m 3 http://127.0.0.1:${GEWU_PC_PORT:-8000}/health/ready >/dev/null 2>&1; then
      echo "[pc] ready"
      return 0
    fi
  done
  echo "[pc] 等待超时，请查看 $log"
  return 1
}

case "${1:-}" in
  stop) stop ;;
  start) start ;;
  restart) stop; start ;;
  *) echo "用法: $0 {start|stop|restart}" ;;
esac
