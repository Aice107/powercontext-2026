#!/usr/bin/env bash
# 全新导入演练：像一个评审那样，从零把 DSL 导成新应用、跑一轮、再删掉。
# 验证点：DSL 自足（除服务地址外无需额外配置）、导入后即可运行。
# 产物：evidence/logs/fresh-import-drill.md
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT="$ROOT/evidence/logs/fresh-import-drill.md"
DSL="$ROOT/dsl/01_inn_chatflow.yml"
BASE="${DIFY_BASE:-http://127.0.0.1:5001}"
COOKIE="${DIFY_COOKIE:-/home/ice/dify/run/cookies.txt}"

bash "$ROOT/tools/dify-login.sh" >/dev/null 2>&1 || true
CSRF=$(awk '$6=="csrf_token"{print $7}' "$COOKIE")
[ -f "$DSL" ] || { echo "缺少 DSL：$DSL" >&2; exit 1; }

mkdir -p "$(dirname "$OUT")"
{
  echo "# 全新导入演练 $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "模拟评审：把 \`dsl/01_inn_chatflow.yml\` 导入成一个新应用 → 跑一轮 → 删除。"
  echo
} > "$OUT"

fail=0
python3 - "$DSL" > /tmp/fresh_import.json <<'PY'
import json, sys
print(json.dumps({"mode": "yaml-content", "yaml_content": open(sys.argv[1]).read()}, ensure_ascii=False))
PY

echo "## 1. 导入" | tee -a "$OUT"
CODE=$(curl -s -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/console/api/apps/imports" --data-binary @/tmp/fresh_import.json \
  -o /tmp/fresh_import_resp.json -w '%{http_code}')
APP=$(python3 -c "import json;print(json.load(open('/tmp/fresh_import_resp.json')).get('app_id',''))" 2>/dev/null)
STATUS=$(python3 -c "import json;print(json.load(open('/tmp/fresh_import_resp.json')).get('status',''))" 2>/dev/null)
echo "- HTTP $CODE，status=$STATUS，app_id=$APP" | tee -a "$OUT"
case "$STATUS" in
  completed*) echo "- ✓ 导入完成" | tee -a "$OUT" ;;
  *) echo "- ✗ 导入状态异常" | tee -a "$OUT"; fail=1 ;;
esac

if [ -z "$APP" ]; then
  echo | tee -a "$OUT"
  echo "## 结论" | tee -a "$OUT"
  echo "- **FAIL**：没有拿到 app_id，后续跳过" | tee -a "$OUT"
  exit 1
fi

echo | tee -a "$OUT"
echo "## 2. 节点数量" | tee -a "$OUT"
NODES=$(curl -s -b "$COOKIE" -H "X-CSRF-Token: $CSRF" "$BASE/console/api/apps/$APP/workflows/draft" \
  | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('graph',{}).get('nodes',[])))" 2>/dev/null)
echo "- 草稿图节点数：$NODES（期望 19）" | tee -a "$OUT"
[ "$NODES" = "19" ] || { echo "- ✗ 节点数不符" | tee -a "$OUT"; fail=1; }

echo | tee -a "$OUT"
echo "## 3. 跑一轮" | tee -a "$OUT"
python3 - "$APP" "$BASE" "$COOKIE" <<'PY' 2>&1 | tee -a "$OUT"
import json, sys, urllib.request
app, base, cookie = sys.argv[1], sys.argv[2], sys.argv[3]
parts = []
for line in open(cookie).read().splitlines():
    if line.startswith("#HttpOnly_"):
        line = line[len("#HttpOnly_"):]
    elif line.startswith("#"):
        continue
    f = line.split("\t")
    if len(f) >= 7:
        parts.append(f"{f[5]}={f[6]}")
csrf = next((p.split("=", 1)[1] for p in parts if p.startswith("csrf_token=")), "")
req = urllib.request.Request(
    f"{base}/console/api/apps/{app}/advanced-chat/workflows/draft/run",
    data=json.dumps({"inputs": {"player_id": "p_fresh"}, "files": [], "query": "往酒坛里兑半坛水"}).encode(),
    headers={"Content-Type": "application/json", "Cookie": "; ".join(parts), "X-CSRF-Token": csrf},
)
status, answer = "", ""
with urllib.request.urlopen(req, timeout=180) as resp:
    for raw in resp:
        line = raw.decode("utf-8", "ignore").strip()
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except Exception:
            continue
        if ev.get("event") == "workflow_finished":
            d = ev.get("data", {}) or {}
            status = d.get("status", "")
            answer = str((d.get("outputs") or {}).get("answer") or "")
print(f"- workflow 状态：{status}")
print(f"- 回答长度：{len(answer)} 字")
print(f"- 回答节选：{answer[:120]}..." if answer else "- 无回答")
sys.exit(0 if status == "succeeded" and len(answer) >= 20 else 2)
PY
RC=$?
[ "$RC" -eq 0 ] || { echo "- ✗ 新应用跑不通" | tee -a "$OUT"; fail=1; }

echo | tee -a "$OUT"
echo "## 4. 清理" | tee -a "$OUT"
DEL=$(curl -s -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -X DELETE "$BASE/console/api/apps/$APP" -o /dev/null -w '%{http_code}')
echo "- 删除测试应用：HTTP $DEL" | tee -a "$OUT"

echo | tee -a "$OUT"
echo "## 结论" | tee -a "$OUT"
[ "$fail" -eq 0 ] && echo "- **PASS**：DSL 可被全新导入并直接运行（评审按 README §4.4 操作即可）" | tee -a "$OUT" \
                  || echo "- **FAIL**：见上文" | tee -a "$OUT"

exit "$fail"
