#!/usr/bin/env bash
# 按 samples/S1..S6 逐条跑一遍，把真实输出落到 evidence/logs/
# 用法：INN_APP_ID=<app_id> bash tools/collect_evidence.sh
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=evidence/logs
mkdir -p "$OUT"
APP="${INN_APP_ID:?需要 INN_APP_ID}"
RUN="bash tools/run_app.sh"

step() { printf '\n===== %s =====\n' "$*" | tee -a "$1"; }

# ---- S1
bash db/init.sh >/dev/null 2>&1
$RUN "我来了" p_guest01 > "$OUT/S1_first_visit.log" 2>&1
mysql -h127.0.0.1 -P2881 -uroot -N -e "SELECT CONCAT('events=', COUNT(*)) FROM inn.inn_ledger WHERE player_id='p_guest01';" > "$OUT/S1_db_after.txt" 2>&1

# ---- S2
$RUN "往酒坛里兑半坛水" p_guest01 > "$OUT/S2_prank.log" 2>&1
mysql -h127.0.0.1 -P2881 -uroot -e "SELECT id,action_text,action_type,severity,grudge_after FROM inn.inn_ledger WHERE player_id='p_guest01';" > "$OUT/S2_db_ledger.txt" 2>&1

# ---- S3
$RUN "又往酒坛里兑水" p_guest01 > "$OUT/S3_old_grudge.log" 2>&1
mysql -h127.0.0.1 -P2881 -uroot -e "EXPLAIN SELECT id FROM inn.inn_ledger WHERE player_id='p_guest01' AND severity>=1 ORDER BY COSINE_SIMILARITY(embedding, (SELECT embedding FROM inn.inn_ledger WHERE player_id='p_guest01' LIMIT 1)) DESC LIMIT 3;" > "$OUT/S3_sql_hybrid.txt" 2>&1

# ---- S4（重置后测跨会话：演示玩家有 3 天历史）
bash db/init.sh >/dev/null 2>&1
$RUN "三娘，我回来了" p_demo01 > "$OUT/S4_cross_session.log" 2>&1
mysql -h127.0.0.1 -P2881 -uroot -e "SELECT player_id,grudge,visits,days_known,total_events FROM inn.inn_player WHERE player_id='p_demo01';" > "$OUT/S4_db_player.txt" 2>&1

# ---- S5（连续三次，最后一次触顶）
bash db/init.sh >/dev/null 2>&1
{ $RUN "往酒坛里兑半坛水" p_demo01
  $RUN "再往酒坛里兑水"   p_demo01
  $RUN "掀了桌子"         p_demo01
} > "$OUT/S5_expel.log" 2>&1
cp /tmp/_run.sse "$OUT/S5_last_run.sse" 2>/dev/null || true
python3 - "$OUT/S5_last_run.sse" > "$OUT/S5_nodes.txt" 2>/dev/null <<'PY'
import json,sys
try: lines=open(sys.argv[1]).read().splitlines()
except OSError: lines=[]
for line in lines:
    if not line.startswith('data:'): continue
    try: d=json.loads(line[5:].strip())
    except Exception: continue
    if d.get('event')=='node_finished':
        dd=d.get('data',{})
        print(f"{dd.get('node_type'):20s} {str(dd.get('title')):8s} {dd.get('status')} "
              f"case={((dd.get('outputs') or {}).get('selected_case_id'))}")
PY

# ---- S6
bash db/init.sh >/dev/null 2>&1
$RUN "打烊，结账" p_demo01 > "$OUT/S6_settle.log" 2>&1

echo
echo "evidence 生成完毕："
ls -lh "$OUT"
