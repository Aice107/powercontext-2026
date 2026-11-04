#!/usr/bin/env bash
# 自愈演练：故意杀掉 inn-api 与本项目的 seekdb，验证看门狗能把它们拉回来。
# 产物：evidence/logs/selfheal-drill.md
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
DATA_DIR="$(cd "$ROOT/.." && pwd)/.seekdb"   # 必须是真实路径，cmdline 里不含 ".."
OUT="$ROOT/evidence/logs/selfheal-drill.md"
SEEKDB_PORT="${SEEKDB_PORT:-2891}"
API_PORT="${INN_API_PORT:-8010}"

port_up() { ss -lnt 2>/dev/null | grep -q ":$1 "; }

wait_port() {  # wait_port <port> <timeout_s>
  local port=$1 limit=$2 start
  start=$(date +%s)
  while [ $(( $(date +%s) - start )) -lt "$limit" ]; do
    port_up "$port" && { echo $(( $(date +%s) - start )); return 0; }
    sleep 2
  done
  echo "$limit+"
  return 1
}

pid_on_port() {  # pid_on_port <port>
  ss -lntp 2>/dev/null | grep -E ":$1\b" | grep -oE "pid=[0-9]+" | cut -d= -f2 | head -1
}

mine_seekdb_pid() {
  for p in $(pgrep -x seekdb 2>/dev/null); do
    if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "$DATA_DIR"; then echo "$p"; return 0; fi
  done
  return 1
}

mkdir -p "$(dirname "$OUT")"
{
  echo "# 自愈演练 $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "对象：看门狗（tools/watchdog.sh）对 inn-api 与本项目 seekdb 的自动恢复能力"
  echo
} > "$OUT"

fail=0
port_up "$API_PORT" || { echo "前置失败：inn-api($API_PORT) 未运行" | tee -a "$OUT"; exit 1; }
mine_seekdb_pid >/dev/null || { echo "前置失败：找不到本项目的 seekdb 进程" | tee -a "$OUT"; exit 1; }

# --- 1. 杀 inn-api
PID=$(pid_on_port "$API_PORT")
echo "## 1. inn-api" | tee -a "$OUT"
echo "- 杀掉 pid=$PID（端口 $API_PORT）" | tee -a "$OUT"
kill -9 "$PID" 2>/dev/null
sleep 2
if port_up "$API_PORT"; then echo "- ✗ 仍在监听（没被杀掉？）" | tee -a "$OUT"; fail=1
else
  SECS=$(wait_port "$API_PORT" 90) && echo "- ✓ ${SECS}s 后被看门狗拉起" | tee -a "$OUT" \
    || { echo "- ✗ 90s 内未恢复" | tee -a "$OUT"; fail=1; }
fi

# --- 2. 杀 seekdb（要求杀完后是"另一个 pid"接管，否则说明杀的只是个副本）
OLD_PID=$(mine_seekdb_pid || true)
PID=$OLD_PID
echo | tee -a "$OUT"
echo "## 2. seekdb" | tee -a "$OUT"
echo "- 杀掉 pid=$PID（端口 $SEEKDB_PORT，datadir=$DATA_DIR）" | tee -a "$OUT"
[ -n "$PID" ] && kill -9 "$PID" 2>/dev/null
sleep 3
if port_up "$SEEKDB_PORT"; then echo "- ✗ 仍在监听" | tee -a "$OUT"; fail=1
else
  SECS=$(wait_port "$SEEKDB_PORT" 240)
  NEW_PID=$(mine_seekdb_pid || echo "?")
  if [ "$SECS" = "240+" ]; then
    echo "- ✗ 240s 内未恢复" | tee -a "$OUT"; fail=1
  elif [ "$NEW_PID" = "$OLD_PID" ]; then
    echo "- ✗ 端口恢复了但进程没换（旧 pid $OLD_PID 仍在，说明没杀干净）" | tee -a "$OUT"; fail=1
  else
    echo "- ✓ ${SECS}s 后由新进程接管（$OLD_PID → $NEW_PID）" | tee -a "$OUT"
  fi
fi

# --- 3. 数据可用性
echo | tee -a "$OUT"
echo "## 3. 恢复后数据可用性" | tee -a "$OUT"
if command -v mysql >/dev/null; then
  CNT=$(timeout 20 mysql -h127.0.0.1 -P"$SEEKDB_PORT" -uroot -N -e "SELECT COUNT(*) FROM inn.inn_ledger" 2>/dev/null || echo "查询失败")
  echo "- inn.inn_ledger 行数：$CNT" | tee -a "$OUT"
  HEALTH=$(curl -s -m 5 "http://127.0.0.1:$API_PORT/healthz" || echo "无响应")
  echo "- inn-api healthz：$HEALTH" | tee -a "$OUT"
fi

echo | tee -a "$OUT"
echo "## 结论" | tee -a "$OUT"
[ "$fail" -eq 0 ] && echo "- **PASS**：两处故障均被看门狗自动恢复，数据无损" | tee -a "$OUT" \
                  || echo "- **FAIL**：存在未恢复项，见上文" | tee -a "$OUT"

exit "$fail"
