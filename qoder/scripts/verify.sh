#!/usr/bin/env bash
# 验证样例：按 docs/VERIFICATION.md 的步骤自动跑一遍，输出落到 evidence/
# 前置：bash scripts/run_all.sh 已把三个服务拉起
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
[ -x "../.venv-app/bin/python" ] && PYTHON="../.venv-app/bin/python"
export PYTHONPATH="$ROOT"
APP=http://127.0.0.1:8712
mkdir -p evidence/logs

step() { echo; echo "==== $1 ===="; }

step "S0. 健康检查（三个服务 + 数据统计）"
curl -sf "$APP/api/health" | tee evidence/logs/S0_health.json

step "S1. 导入示例语料（16 篇 -> seekdb 分块 + 本地向量化）"
curl -sf -X POST "$APP/api/ingest/sample" | tee evidence/logs/S1_ingest.json

step "S2. 混合检索：语义问题（向量一路为主）"
curl -sf -X POST "$APP/api/search" -H 'Content-Type: application/json' \
  -d '{"query":"怎么提升召回率","mode":"hybrid","size":5}' \
  | tee evidence/logs/S2_search_semantic.json

step "S3. 混合检索：精确参数名（全文一路为主）"
curl -sf -X POST "$APP/api/search" -H 'Content-Type: application/json' \
  -d '{"query":"ef_search","mode":"hybrid","size":5}' \
  | tee evidence/logs/S3_search_exact.json

step "S4. 三种模式对照（失败样本互补）"
for m in hybrid vector fts; do
  curl -sf -X POST "$APP/api/search" -H 'Content-Type: application/json' \
    -d "{\"query\":\"量化会不会掉点\",\"mode\":\"$m\",\"size\":4}" \
    | tee "evidence/logs/S4_mode_$m.json" | "$PYTHON" -c "import json,sys;d=json.load(sys.stdin);print(f'$m ->', [h['title'] for h in d['hits']])"
done

step "S5. 结构化过滤：上周窗口 + 课题标签（coursework 应被排除）"
curl -sf -X POST "$APP/api/search" -H 'Content-Type: application/json' \
  -d '{"query":"多数派 确认 日志","mode":"fts","since":"2026-10-26","until":"2026-11-01","project":"vec-search"}' \
  | tee evidence/logs/S5_filter_window.json

step "S6. 写入记忆（4 条偏好/约束 -> PowerContext）"
i=0
while IFS='|' read -r kind text; do
  i=$((i+1))
  curl -sf -X POST "$APP/api/memory/remember" -H 'Content-Type: application/json' \
    -d "{\"kind\":\"$kind\",\"text\":\"$text\"}" \
    | tee "evidence/logs/S6_remember_$i.json" > /dev/null
  echo "已写入 [$kind] $text"
done <<'EOF'
preference|组会材料要结论先行
preference|关键数据放在进展前面，先给数据再讲故事
preference|每个结论都要挂出处
constraint|组会材料必须提前一天发给导师
EOF

step "S7. 召回记忆（跨会话语义召回，matched_by 应含 vector）"
curl -sf -G "$APP/api/memory/recall" --data-urlencode "q=导师对材料的要求" \
  --data-urlencode "mode=hybrid" --data-urlencode "limit=4" \
  | tee evidence/logs/S7_recall.json

step "S8. 生成组会草稿（记忆改变版式；附录含证据链与 SQL）"
curl -sf -X POST "$APP/api/draft" -H 'Content-Type: application/json' \
  -d '{"since":"2026-10-26","until":"2026-11-01"}' \
  | tee evidence/logs/S8_draft.json | "$PYTHON" -c "import json,sys;print(json.load(sys.stdin)['markdown'])" \
  > evidence/logs/S8_draft.md

step "S9. 记忆读写日志（JSONL 证据）"
curl -sf "$APP/api/memory/journal?limit=50" > evidence/logs/S9_memory_journal.json
grep -c "memory/remember" evidence/logs/S9_memory_journal.json || true

step "完成：全部输出已保存到 qoder/evidence/logs/"
