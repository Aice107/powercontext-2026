#!/usr/bin/env bash
# 启动/停止本地 seekdb（server 模式，供 seekdb-js 通过 MySQL 协议访问）。
# 用法: bash scripts/seekdb_server.sh {start|stop|restart|status}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${SEEKDB_RUNTIME:-$ROOT/.seekdb}"
PORT="${SEEKDB_PORT:-2895}"
PID_FILE="$RUNTIME/seekdb.pid"
LOG_FILE="$RUNTIME/server.log"
BASE_DIR="$RUNTIME/data"

# seekdb 可执行文件探测顺序：显式环境变量 → 仓库内置 → pylibseekdb 包内二进制
find_bin() {
  if [ -n "${SEEKDB_BIN:-}" ] && [ -x "$SEEKDB_BIN" ]; then echo "$SEEKDB_BIN"; return 0; fi
  if [ -x "$ROOT/bin/seekdb" ]; then echo "$ROOT/bin/seekdb"; return 0; fi
  for candidate in \
    "$ROOT/.venv/lib/python3.12/site-packages/pylibseekdb/seekdb" \
    "$ROOT/.venv/lib/python3.13/site-packages/pylibseekdb/seekdb" \
    "$ROOT/.venv/lib/python3.14/site-packages/pylibseekdb/seekdb" \
    /home/ice/seekdb/venv/lib/python3.14/site-packages/pylibseekdb/seekdb; do
    if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  command -v seekdb 2>/dev/null && return 0
  return 1
}

is_up() {
  node -e '
    const net = require("net");
    const s = net.connect({ host: "127.0.0.1", port: Number(process.env.SEEKDB_PORT || 2895) });
    s.on("connect", () => { s.destroy(); process.exit(0); });
    s.on("error", () => process.exit(1));
    setTimeout(() => { s.destroy(); process.exit(1); }, 1500);
  ' >/dev/null 2>&1
}

wait_up() {
  for _ in $(seq 1 90); do
    if is_up; then return 0; fi
    sleep 1
  done
  return 1
}

start() {
  if is_up; then echo "seekdb 已在 127.0.0.1:$PORT 运行"; return 0; fi
  local bin
  if ! bin="$(find_bin)"; then
    echo "未找到 seekdb 可执行文件。请安装：pip install pylibseekdb==1.4.0.post2" >&2
    echo "或用 SEEKDB_BIN=/path/to/seekdb 指定，或使用 Docker: docker run -p $PORT:2881 oceanbase/seekdb" >&2
    return 1
  fi
  mkdir -p "$BASE_DIR"
  local libdir
  libdir="$(dirname "$bin")"
  echo "使用 seekdb: $bin"
  LD_LIBRARY_PATH="$libdir:${LD_LIBRARY_PATH:-}" nohup "$bin" \
    --base-dir "$BASE_DIR" --port "$PORT" --nodaemon \
    --parameter memory_budget=2G --parameter log_disk_size=2G \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  if wait_up; then
    echo "seekdb 已启动: 127.0.0.1:$PORT (pid $(cat "$PID_FILE"), base-dir $BASE_DIR)"
    return 0
  fi
  echo "seekdb 启动失败，日志尾部：" >&2
  tail -40 "$LOG_FILE" >&2 || true
  return 1
}

stop() {
  if [ ! -f "$PID_FILE" ]; then echo "没有由本脚本管理的 seekdb 进程"; return 0; fi
  local pid; pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 60); do kill -0 "$pid" >/dev/null 2>&1 || break; sleep 1; done
    kill -0 "$pid" >/dev/null 2>&1 && kill -9 "$pid" >/dev/null 2>&1 || true
    echo "seekdb 已停止 (pid $pid)"
  else
    echo "pid $pid 未在运行"
  fi
  rm -f "$PID_FILE"
}

status() {
  if is_up; then echo "seekdb: up (127.0.0.1:$PORT)"; else echo "seekdb: down"; return 1; fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "用法: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
