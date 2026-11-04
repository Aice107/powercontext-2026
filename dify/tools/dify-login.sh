#!/usr/bin/env bash
# 刷新 Dify 控制台登录态（cookies.txt）。令牌 60 分钟过期，自检/取证脚本前先跑一次。
# 用法：bash tools/dify-login.sh [email] [password]
set -uo pipefail
EMAIL="${1:-${DIFY_EMAIL:-admin@inn.local}}"
PASS="${2:-${DIFY_PASS:-InnAdmin123!}}"
BASE="${DIFY_BASE:-http://127.0.0.1:5001}"
COOKIE="${DIFY_COOKIE:-/home/ice/dify/run/cookies.txt}"

mkdir -p "$(dirname "$COOKIE")"
B64=$(printf '%s' "$PASS" | base64)
CODE=$(curl -s -c "$COOKIE" -o /dev/null -w '%{http_code}' -X POST "$BASE/console/api/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$B64\",\"remember_me\":true}")

if [ "$CODE" = "200" ]; then
  echo "[login] ok -> $COOKIE"
  exit 0
fi
echo "[login] failed (HTTP $CODE)；检查 Dify 是否已 setup、账号密码是否正确" >&2
exit 1
