#!/usr/bin/env bash
# 直接调用 Dify 应用的 draft 工作流跑一轮对话（调试/取证用）
# 用法：bash tools/run_app.sh "玩家说的话" [player_id] [app_id]
set -euo pipefail
Q="${1:?query required}"
PID="${2:-p_demo01}"
# 本机开发态配置（gitignored）：INN_APP_ID 等
[ -f "$(dirname "$0")/.local.env" ] && set -a && . "$(dirname "$0")/.local.env" && set +a
APP="${3:-${INN_APP_ID:-}}"
COOKIE="${DIFY_COOKIE:-/home/ice/dify/run/cookies.txt}"
BASE="${DIFY_BASE:-http://127.0.0.1:5001}"
[ -z "$APP" ] && { echo "app_id required (env INN_APP_ID)"; exit 1; }

CSRF=$(awk '$6=="csrf_token"{print $7}' "$COOKIE")
python3 - "$Q" "$PID" > /tmp/_run_payload.json <<'PY'
import json,sys
print(json.dumps({"inputs":{"player_id":sys.argv[2]},"files":[],"query":sys.argv[1]}, ensure_ascii=False))
PY
curl -s -N --max-time 240 -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -X POST "$BASE/console/api/apps/$APP/advanced-chat/workflows/draft/run" \
  --data-binary @/tmp/_run_payload.json -o /tmp/_run.sse -w "http=%{http_code}\n"

python3 - <<'PY'
import json
seen=[]
for line in open('/tmp/_run.sse'):
    line=line.strip()
    if not line.startswith('data:'): continue
    try: d=json.loads(line[5:].strip())
    except Exception: continue
    ev=d.get('event'); dd=d.get('data',{})
    if ev=='node_finished' and dd.get('node_type')=='http-request':
        seen.append(("HTTP:"+str(dd.get('title')), str((dd.get('outputs') or {}).get('body'))[:200]))
    if ev=='node_finished' and dd.get('node_type')=='llm':
        seen.append(("LLM:"+str(dd.get('title')), str((dd.get('outputs') or {}).get('text'))))
    if ev=='workflow_finished' and dd.get('status')!='succeeded':
        seen.append(("WF-FAIL", str(dd.get('error'))[:300]))
for k,v in seen:
    print(f"--- {k} ---")
    print(v[:1200])
PY
