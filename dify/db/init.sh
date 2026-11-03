#!/usr/bin/env bash
# 初始化 seekdb：建库建表 + 灌入台词库与演示数据
# 用法：bash db/init.sh [seekdb_host] [port] [user] [password]
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${1:-${SEEKDB_HOST:-127.0.0.1}}"
PORT="${2:-${SEEKDB_PORT:-2891}}"
USER="${3:-${SEEKDB_USER:-root}}"
PASS="${4:-${SEEKDB_PASSWORD:-}}"

MYSQL="mysql -h${HOST} -P${PORT} -u${USER}"
[ -n "${PASS}" ] && MYSQL="${MYSQL} -p${PASS}"

echo "[1/4] 建库建表（含向量索引与全文索引）"
${MYSQL} < db/01_schema.sql

echo "[2/4] 台词库 seed"
${MYSQL} < db/02_seed_lines.sql

echo "[3/4] 演示玩家 seed（p_demo01，仇值 62 / T3）"
${MYSQL} < db/04_seed_demo.sql

echo "[3.5/4] 补向量（seed 的 SQL 只有结构化字段）"
if [ -x backend/.venv/bin/python ]; then
  backend/.venv/bin/python tools/seed_embeddings.py || echo "  跳过：向量补写失败（不影响结构化数据）"
else
  echo "  跳过：backend/.venv 不存在"
fi

echo "[4/4] 校验"
${MYSQL} -e "USE inn;
SELECT 'inn_player' AS t, COUNT(*) AS rows_ FROM inn_player
UNION ALL SELECT 'inn_ledger', COUNT(*) FROM inn_ledger
UNION ALL SELECT 'inn_rumor',  COUNT(*) FROM inn_rumor
UNION ALL SELECT 'inn_line',   COUNT(*) FROM inn_line;"

echo "done. 提示：演示玩家 player_id=p_demo01"
