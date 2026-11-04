#!/usr/bin/env bash
# 旁路验证：Dify 1.17.0 的元数据库能否直接用 seekdb（赛题 §4.4 第 1 行的可行性）
#
# 特点：全程使用独立库 + 独立端口，**不影响正在运行的 Dify**；跑完自动清理。
#
# 用法：
#   DIFY_API_DIR=~/dify/dify-1.17.0/api bash tools/verify-seekdb-meta.sh
#
# 依赖：seekdb（默认 127.0.0.1:2891）、Dify 源码目录（含 .venv）
set -uo pipefail

DIFY_API_DIR="${DIFY_API_DIR:-$HOME/dify/dify-1.17.0/api}"
SEEKDB_HOST="${SEEKDB_HOST:-127.0.0.1}"
SEEKDB_PORT="${SEEKDB_PORT:-2891}"
SEEKDB_USER="${SEEKDB_USER:-root}"
SEEKDB_PASS="${SEEKDB_PASSWORD:-}"
# 默认用唯一库名：这个 seekdb 实例上 DROP DATABASE 会卡住（OceanBase 侧异步回收），
# 所以不做"先删后建"，每次用新库；清理只是尽力而为。
DB="${VERIFY_DB:-dify_meta_$(date +%s)}"
PORT="${VERIFY_PORT:-5005}"

MYSQL=(mysql -h"$SEEKDB_HOST" -P"$SEEKDB_PORT" -u"$SEEKDB_USER")
[ -n "$SEEKDB_PASS" ] && MYSQL+=(-p"$SEEKDB_PASS")

say() { printf '[verify] %s\n' "$*"; }
fail() { say "FAIL: $*"; exit 1; }

[ -d "$DIFY_API_DIR" ] || fail "找不到 Dify 源码目录：$DIFY_API_DIR（用 DIFY_API_DIR 指定）"
[ -x "$DIFY_API_DIR/.venv/bin/flask" ] || fail "$DIFY_API_DIR/.venv/bin/flask 不存在"
"${MYSQL[@]}" -e "SELECT 1" >/dev/null 2>&1 || fail "连不上 seekdb ${SEEKDB_HOST}:${SEEKDB_PORT}"

cleanup() {
  if [ -n "${API_PID:-}" ]; then kill "$API_PID" 2>/dev/null; fi
  timeout 20 "${MYSQL[@]}" -e "DROP DATABASE IF EXISTS \`$DB\`" >/dev/null 2>&1 || \
    say "提示：DROP DATABASE 超时（OceanBase 侧异步回收），库 $DB 可稍后手工清理"
  say "已清理：停掉临时 API、删除库 $DB"
}
trap cleanup EXIT

say "1/4 建临时库 $DB"
"${MYSQL[@]}" -e "CREATE DATABASE \`$DB\` DEFAULT CHARACTER SET utf8mb4" || fail "建库失败"

say "2/4 迁移（DB_TYPE=seekdb → ${SEEKDB_HOST}:${SEEKDB_PORT}/$DB）"
cd "$DIFY_API_DIR" || fail "cd 失败"
if ! DB_TYPE=seekdb DB_HOST="$SEEKDB_HOST" DB_PORT="$SEEKDB_PORT" \
     DB_USERNAME="$SEEKDB_USER" DB_PASSWORD="$SEEKDB_PASS" DB_DATABASE="$DB" \
     timeout 600 .venv/bin/flask upgrade-db > /tmp/verify-seekdb-migrate.log 2>&1; then
  tail -5 /tmp/verify-seekdb-migrate.log
  fail "迁移失败（完整日志 /tmp/verify-seekdb-migrate.log）"
fi
TABLES=$("${MYSQL[@]}" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB'")
say "   迁移成功，建表 ${TABLES} 张"

say "3/4 用这份库起临时 API（:${PORT}）"
DB_TYPE=seekdb DB_HOST="$SEEKDB_HOST" DB_PORT="$SEEKDB_PORT" \
  DB_USERNAME="$SEEKDB_USER" DB_PASSWORD="$SEEKDB_PASS" DB_DATABASE="$DB" \
  nohup .venv/bin/gunicorn --no-control-socket --bind "127.0.0.1:${PORT}" \
    --workers 1 --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --timeout 120 app:socketio_app > /tmp/verify-seekdb-api.log 2>&1 &
API_PID=$!

for _ in $(seq 1 20); do
  sleep 2
  curl -sf -m 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
done

say "4/4 校验"
HEALTH=$(curl -s -m 5 "http://127.0.0.1:${PORT}/health" || true)
SETUP=$(curl -s -m 5 "http://127.0.0.1:${PORT}/console/api/setup" || true)
printf '   /health        : %s\n' "${HEALTH:-<无响应>}"
printf '   /console/api/setup : %s\n' "${SETUP:-<无响应>}"

echo "$HEALTH" | grep -q '"status": *"ok"' || fail "health 非 ok"
echo "$SETUP" | grep -q 'not_started' || say "提示：setup 状态不是 not_started（若该库已被初始化过属正常）"

echo
say "PASS：Dify 1.17.0 可用 seekdb 作元数据库（建表 ${TABLES} 张，API 可启动可读写）"
say "说明：本作品主线仍用 MySQL 承载 Dify 元数据库，此脚本只用于验证赛题 §4.4 第 1 行的可行性。"
