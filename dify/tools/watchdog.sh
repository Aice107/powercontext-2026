#!/usr/bin/env bash
# 依赖看门狗：seekdb / inn-api 掉线自动拉起
# 注意：
#  1) seekdb 启动需要约 40-60 秒，启动中靠"进程存在"判断，避免重复拉起抢同一 datadir；
#  2) 用 pgrep -x（进程名精确匹配），避免匹配到本脚本自身的命令行。
set -uo pipefail
D=/home/ice/dify-project
SEEKDB_BIN=/home/ice/seekdb-submit/build_release/src/observer/seekdb
LOG=$D/.run/watchdog.log
mkdir -p "$D/.run"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

# 只认"本项目的" seekdb（按 base-dir 判断）：本机还有 obtest_* 的实例占着别的端口
mine_running() {
  for p in $(pgrep -x seekdb 2>/dev/null); do
    if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "$D/.seekdb"; then
      return 0
    fi
  done
  return 1
}

# 单实例保护：两个看门狗同时拉 seekdb 会抢同一 datadir
# 注意：子进程必须 9>&- 关闭这个 fd，否则 uvicorn/seekdb 会一直持有锁，
# 之后任何新看门狗都会误判"已有实例在跑"。参考 2026-11-04 的踩坑记录。
exec 9>"$D/.run/watchdog.lock"
if ! flock -n 9; then
  echo "另一个 watchdog 已在运行，退出" >&2
  exit 1
fi

boot_guard=0   # 上次拉起 seekdb 的时间戳，90 秒内不再重复拉起

while true; do
  now=$(date +%s)

  # --- seekdb
  if ! mine_running; then
    if [ $((now - boot_guard)) -gt 90 ]; then
      log "seekdb not running -> start"
      nohup "$SEEKDB_BIN" --base-dir "$D/.seekdb" --port 2891 --nodaemon \
        --parameter memory_budget=2G --parameter log_disk_size=2G \
        >> "$D/.seekdb/seekdb.out" 2>&1 9>&- &
      disown || true
      boot_guard=$now
    fi
  fi

  # --- inn-api
  if ! ss -lnt 2>/dev/null | grep -q ':8010 '; then
    log "inn-api down -> start"
    ( cd "$D/dify/backend" && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 \
        >> "$D/.run/inn-api.log" 2>&1 9>&- & )
    disown || true
  fi

  sleep 15
done
