#!/usr/bin/env bash
# Start/stop/restart the PowerContext server used for task-state reuse.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${POWERCONTEXT_RUNTIME:-$ROOT/.runtime/pc}"
PORT="${POWERCONTEXT_PORT:-8093}"
ENV_FILE="$RUNTIME/pc.env"
PID_FILE="$RUNTIME/pc.pid"
LOG_FILE="$RUNTIME/pc.log"

ensure_env() {
  mkdir -p "$RUNTIME"
  if [ -f "$ENV_FILE" ]; then
    return
  fi
  cat > "$ENV_FILE" <<EOF
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:///$RUNTIME/pc.db
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_MCP_ENABLED=false
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
POWERCONTEXT_SERVER_EXTERNAL_SKILLS={}
EOF
}

is_up() {
  curl -fsS "http://127.0.0.1:$PORT/health/live" >/dev/null 2>&1
}

wait_up() {
  local i
  for i in $(seq 1 60); do
    if is_up; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start() {
  ensure_env
  if is_up; then
    echo "PowerContext already running on 127.0.0.1:$PORT"
    return 0
  fi
  if ! command -v powercontext >/dev/null 2>&1; then
    echo "powercontext CLI not found. Install with:" >&2
    echo "  uv tool install --force 'powercontext[cli,server]==1.4.1'" >&2
    return 1
  fi
  nohup powercontext server run --host 127.0.0.1 --port "$PORT" --env-file "$ENV_FILE" \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  if wait_up; then
    echo "PowerContext started on 127.0.0.1:$PORT (pid $(cat "$PID_FILE"))"
    return 0
  fi
  echo "PowerContext failed to start; last log lines:" >&2
  tail -40 "$LOG_FILE" >&2 || true
  return 1
}

stop() {
  if [ ! -f "$PID_FILE" ]; then
    echo "PowerContext not managed here (no pid file)"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    local i
    for i in $(seq 1 20); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "PowerContext stopped (pid $pid)"
  else
    echo "PowerContext pid $pid is not running"
  fi
  rm -f "$PID_FILE"
}

status() {
  if is_up; then
    echo "PowerContext: up on 127.0.0.1:$PORT"
    [ -f "$PID_FILE" ] && echo "pid: $(cat "$PID_FILE")"
  else
    echo "PowerContext: down on 127.0.0.1:$PORT"
    return 1
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
