#!/usr/bin/env bash
# Start/stop/restart the local seekdb server used as the engineering index.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${SEEKDB_RUNTIME:-$ROOT/.runtime/seekdb}"
PORT="${SEEKDB_PORT:-2893}"
PID_FILE="$RUNTIME/seekdb.pid"
LOG_FILE="$RUNTIME/server.log"
BIN="$ROOT/.venv/lib/python3.12/site-packages/pylibseekdb/seekdb"
LIBDIR="$ROOT/.venv/lib/python3.12/site-packages/pylibseekdb"

is_up() {
  SEEKDB_PORT="$PORT" "$ROOT/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import os
import pymysql
pymysql.connect(host="127.0.0.1", port=int(os.environ["SEEKDB_PORT"]), user="root", connect_timeout=2).close()
PY
}

wait_up() {
  local i
  for i in $(seq 1 90); do
    if is_up; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start() {
  if is_up; then
    echo "seekdb already running on 127.0.0.1:$PORT"
    return 0
  fi
  if [ ! -x "$BIN" ]; then
    echo "seekdb binary not found at $BIN; run scripts/bootstrap.sh" >&2
    return 1
  fi
  mkdir -p "$RUNTIME"
  LD_LIBRARY_PATH="$LIBDIR:${LD_LIBRARY_PATH:-}" nohup "$BIN" \
    --base-dir "$RUNTIME" --port "$PORT" --nodaemon \
    --parameter memory_budget=2G --parameter log_disk_size=2G \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  if wait_up; then
    echo "seekdb started on 127.0.0.1:$PORT (pid $(cat "$PID_FILE"))"
    return 0
  fi
  echo "seekdb failed to start; last log lines:" >&2
  tail -40 "$LOG_FILE" >&2 || true
  return 1
}

stop() {
  if [ ! -f "$PID_FILE" ]; then
    echo "seekdb not managed here (no pid file)"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    local i
    for i in $(seq 1 60); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "seekdb stopped (pid $pid)"
  else
    echo "seekdb pid $pid is not running"
  fi
  rm -f "$PID_FILE"
}

reset() {
  stop
  case "$RUNTIME" in
    "$ROOT"/.runtime/*) rm -rf "$RUNTIME" ;;
    *) echo "refusing to remove unexpected path: $RUNTIME" >&2; exit 1 ;;
  esac
  start
}

status() {
  if is_up; then
    echo "seekdb: up on 127.0.0.1:$PORT"
    [ -f "$PID_FILE" ] && echo "pid: $(cat "$PID_FILE")"
  else
    echo "seekdb: down on 127.0.0.1:$PORT"
    return 1
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 2; start ;;
  reset) reset ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|reset|status}" >&2; exit 2 ;;
esac
