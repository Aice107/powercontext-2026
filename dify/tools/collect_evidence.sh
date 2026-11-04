#!/usr/bin/env bash
# 按 samples/ 逐条跑一遍，把真实输出落到 evidence/logs/
# 用法：INN_APP_ID=<app_id> bash tools/collect_evidence.sh
#
# 约定：
#   - 端口从环境读（默认 2891），绝不硬编码，避免"连 2881 被拒"的假证据
#   - 每个 DB 核验文件都必须有真实结果（不是 EXPLAIN 空壳）
#   - S5 的逐客与求原谅在同一条连续会话里跑，数值才对得上（62→76→92→68）
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=evidence/logs
mkdir -p "$OUT"
APP="${INN_APP_ID:?需要 INN_APP_ID}"
RUN="bash tools/run_app.sh"
SEEDB_PORT="${SEEKDB_PORT:-2891}"
MYSQL=(mysql -h127.0.0.1 -P"$SEEDB_PORT" -uroot)

trace_nodes() {  # trace_nodes <sse> <out.txt>
  python3 - "$1" > "$2" 2>/dev/null <<'PY'
import json, sys
for line in open(sys.argv[1]).read().splitlines():
    if not line.startswith('data:'):
        continue
    try:
        d = json.loads(line[5:].strip())
    except Exception:
        continue
    if d.get('event') == 'node_finished':
        dd = d.get('data', {})
        print(f"{str(dd.get('node_type')):20s} {str(dd.get('title')):8s} {dd.get('status')} "
              f"case={((dd.get('outputs') or {}).get('selected_case_id'))}")
PY
}


# ---- 依赖守卫：任一端口缺失就先拉起，再等；避免产出"连接被拒"的假证据
ensure_ports() {
  local missing=0
  for p in 2891 8010 8090 5001 5002; do
    ss -lnt 2>/dev/null | grep -q ":$p " || missing=1
  done
  if [ "$missing" -eq 1 ]; then
    echo "[guard] 依赖缺失，调用 start-local.sh 拉起"
    bash tools/start-local.sh > /tmp/collect_guard.log 2>&1 || true
  fi
  local i=0
  while [ $i -lt 90 ]; do
    local ok=1
    for p in 2891 8010 8090 5001 5002; do
      ss -lnt 2>/dev/null | grep -q ":$p " || ok=0
    done
    [ "$ok" -eq 1 ] && return 0
    sleep 2; i=$((i+1))
  done
  echo "[guard] FATAL: 依赖仍未就绪（2891/8010/8090/5001/5002）" >&2
  return 1
}

ensure_ports || exit 1

echo "== 0. 向量落库自检 =="
bash db/init.sh >/dev/null 2>&1
"${MYSQL[@]}" -e "SELECT
  (SELECT COUNT(*) FROM inn.inn_ledger) AS ledger_rows,
  (SELECT COUNT(*) FROM inn.inn_ledger WHERE embedding IS NOT NULL) AS with_embedding,
  (SELECT COUNT(*) FROM inn.inn_rumor  WHERE embedding IS NOT NULL) AS rumor_with_embedding;" \
  > "$OUT/S0_embeddings.txt" 2>&1
cat "$OUT/S0_embeddings.txt"

# ---- S1 首次入店
bash db/init.sh >/dev/null 2>&1
$RUN "我来了" p_guest01 > "$OUT/S1_first_visit.log" 2>&1
"${MYSQL[@]}" -N -e "SELECT CONCAT('events=', COUNT(*)) FROM inn.inn_ledger WHERE player_id='p_guest01';" \
  > "$OUT/S1_db_after.txt" 2>&1

# ---- S2 记账
$RUN "往酒坛里兑半坛水" p_guest01 > "$OUT/S2_prank.log" 2>&1
"${MYSQL[@]}" -e "SELECT id,action_text,action_type,severity,grudge_after,
  CASE WHEN embedding IS NULL THEN 'NULL' ELSE 'vector(1024)' END AS vec
  FROM inn.inn_ledger WHERE player_id='p_guest01';" > "$OUT/S2_db_ledger.txt" 2>&1

# ---- S3 翻旧账：把后端实际执行的混合检索 SQL 跑一遍，连结果一起留证
$RUN "又往酒坛里兑水" p_guest01 > "$OUT/S3_old_grudge.log" 2>&1
{
  echo "-- 后端 hybrid 查询（与 backend/app/main.py:_hybrid_similar 同构）"
  echo "-- 查询向量取该玩家第一条事件的 embedding，文本命中用本句话"
  "${MYSQL[@]}" -e "SELECT id, action_text, severity,
    ROUND(COSINE_SIMILARITY(embedding, (SELECT embedding FROM inn.inn_ledger WHERE player_id='p_guest01' ORDER BY id LIMIT 1)), 4) AS vsim,
    ROUND(MATCH(action_text) AGAINST ('又往酒坛里兑水'), 4) AS ft
  FROM inn.inn_ledger
  WHERE player_id='p_guest01' AND severity >= 1
  ORDER BY (0.7 * COSINE_SIMILARITY(embedding, (SELECT embedding FROM inn.inn_ledger WHERE player_id='p_guest01' ORDER BY id LIMIT 1))
            + 0.3 * (MATCH(action_text) AGAINST ('又往酒坛里兑水') > 0)) DESC
  LIMIT 3;"
  echo
  echo "-- 执行计划"
  "${MYSQL[@]}" -e "EXPLAIN SELECT id FROM inn.inn_ledger
    WHERE player_id='p_guest01' AND severity >= 1
    ORDER BY COSINE_SIMILARITY(embedding, (SELECT embedding FROM inn.inn_ledger WHERE player_id='p_guest01' ORDER BY id LIMIT 1)) DESC
    LIMIT 3;"
  echo
  echo "-- 索引确认"
  "${MYSQL[@]}" -e "SELECT index_name, index_type FROM information_schema.statistics
    WHERE table_schema='inn' AND table_name='inn_ledger';"
} > "$OUT/S3_sql_hybrid.txt" 2>&1
sed -n '1,12p' "$OUT/S3_sql_hybrid.txt"

# ---- S4 跨会话（演示玩家）
bash db/init.sh >/dev/null 2>&1
$RUN "三娘，我回来了" p_demo01 > "$OUT/S4_cross_session.log" 2>&1
"${MYSQL[@]}" -e "SELECT player_id,grudge,visits,days_known,total_events FROM inn.inn_player WHERE player_id='p_demo01';" \
  > "$OUT/S4_db_player.txt" 2>&1

# ---- S5 逐客 → 求原谅（同一状态连续跑，数值 62→76→92→68）
bash db/init.sh >/dev/null 2>&1
{ $RUN "往酒坛里兑半坛水" p_demo01
  $RUN "再往酒坛里兑水"   p_demo01
} > "$OUT/S5_expel.log" 2>&1
trace_nodes /tmp/_run.sse "$OUT/S5_expel_nodes.txt"
$RUN "我帮你把柴劈了，再赔你两吊钱" p_demo01 > "$OUT/S5_forgive.log" 2>&1
trace_nodes /tmp/_run.sse "$OUT/S5_forgive_nodes.txt"
"${MYSQL[@]}" -e "SELECT id,action_text,severity,grudge_after FROM inn.inn_ledger WHERE player_id='p_demo01' ORDER BY id;" \
  > "$OUT/S5_db_ledger.txt" 2>&1

# ---- S6 打烊结算
bash db/init.sh >/dev/null 2>&1
$RUN "打烊，结账" p_demo01 > "$OUT/S6_settle.log" 2>&1

# ---- S10 和解线
bash db/init.sh >/dev/null 2>&1
$RUN "我把你屋顶漏雨的地方修好了" p_demo01 > "$OUT/S10_kindness.log" 2>&1
"${MYSQL[@]}" -e "SELECT id,action_type,severity,grudge_after FROM inn.inn_ledger WHERE player_id='p_demo01' ORDER BY id DESC LIMIT 2;" \
  > "$OUT/S10_db_ledger.txt" 2>&1

# ---- 收尾：回到干净的演示状态
bash db/init.sh >/dev/null 2>&1

echo
echo "== 证据有效性校验（DB 核验文件必须真实有结果）=="
DB_FILES="S0_embeddings.txt S1_db_after.txt S2_db_ledger.txt S3_sql_hybrid.txt S4_db_player.txt S5_db_ledger.txt S10_db_ledger.txt"
bad=0
for f in $DB_FILES; do
  if grep -qE "Can't connect|ERROR 2003|Connection refused" "$OUT/$f" 2>/dev/null; then
    echo "  FATAL: $f 含连接错误" >&2; bad=1
  fi
  # 每个 DB 文件至少要有表头行
  if [ "$(wc -l < "$OUT/$f" 2>/dev/null || echo 0)" -lt 1 ]; then
    echo "  FATAL: $f 为空" >&2; bad=1
  fi
done
# 运行日志里，除 S7/S7b（故意制造故障）外不允许有连接错误
for f in "$OUT"/S[1-6]_*.log "$OUT"/S10_*.log; do
  [ -f "$f" ] || continue
  grep -qE "Can't connect|Connection refused" "$f" && { echo "  FATAL: $(basename "$f") 含连接错误" >&2; bad=1; }
done
[ "$bad" -eq 1 ] && exit 1
echo "  OK：7 个 DB 核验文件均有真实结果，S1-S6/S10 运行日志无连接错误"

echo
echo "== 产物 =="
ls -1 "$OUT" | sed 's/^/  /'
