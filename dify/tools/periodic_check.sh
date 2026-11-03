#!/usr/bin/env bash
# 每 30 分钟巡检：依赖健康 + 赛题合规自检 + 追加进度日志
# 由 tools/compliance_check.py 提供判定，本脚本只做环境体检与汇总。
set -uo pipefail
cd "$(dirname "$0")/.."

echo "===== 巡检 $(date '+%Y-%m-%d %H:%M:%S') ====="

# 1. 依赖端口
for pair in "seekdb:2891" "inn-api:8010" "dify-api:5001" "dify-web:3000"; do
  name="${pair%%:*}"; port="${pair##*:}"
  if ss -lnt 2>/dev/null | grep -q ":${port} "; then
    printf '  [up]   %-9s :%s\n' "$name" "$port"
  else
    printf '  [DOWN] %-9s :%s\n' "$name" "$port"
  fi
done

# 2. 合规自检（含 seekdb 数据、混合检索、应用运行、文档与样例完整性）
echo
python3 tools/compliance_check.py --log
rc=$?

echo
echo "===== 巡检结束（合规 rc=${rc}）====="
exit $rc
