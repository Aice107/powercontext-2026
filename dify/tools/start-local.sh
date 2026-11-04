#!/usr/bin/env bash
# 本机一键恢复：Dify 栈 + seekdb + inn-api + PowerContext + 登录态
# 适用场景：机器重启 / 进程被 OOM 杀掉后，把演示环境拉回可用状态。
# 说明：这是"本机开发态"脚本（依赖 ~/dify 下的 Dify 部署与 ~/dify-shot），不作为赛题提交材料。
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LOCAL="$ROOT/tools/.local.env"

port_up() { ss -lnt 2>/dev/null | grep -q ":$1 "; }
say() { printf '[start-local] %s\n' "$*"; }

# 0. 读取本机配置（INN_APP_ID 等）
[ -f "$LOCAL" ] && set -a && . "$LOCAL" && set +a

# 1. Dify 栈（MySQL/Redis/daemon/API/worker/Web）
if [ -x "$HOME/dify/start-all.sh" ]; then
  say "Dify 栈"
  # 不要用管道接 tail：start-all 会留下常驻子进程，管道会让 tail 永远等下去
  bash "$HOME/dify/start-all.sh" > /tmp/start-all.log 2>&1
  tail -8 /tmp/start-all.log
else
  say "未找到 ~/dify/start-all.sh（请先完成 Dify 安装）"
fi

# 2. PowerContext（可选记忆层）
if [ -x "$HOME/.local/bin/powercontext" ]; then
  if ! port_up 8090; then
    say "PowerContext :8090"
    ( cd "$HOME/dify-project/.pc" && PATH="$HOME/.local/bin:$PATH" \
        nohup powercontext server run --host 127.0.0.1 --port 8090 \
        --env-file "$HOME/dify-project/.pc/pc.env" > pc.log 2>&1 & )
  else
    say "PowerContext 已在运行"
  fi
fi

# 3. seekdb + inn-api（看门狗，单实例）
if ! pgrep -f "tools/watchdog.sh" >/dev/null 2>&1; then
  say "启动看门狗（seekdb :2891 + inn-api :8010）"
  ( nohup bash "$ROOT/tools/watchdog.sh" > /dev/null 2>&1 & )
else
  say "看门狗已在运行"
fi

# 4. 等待依赖就绪
say "等待 seekdb / inn-api 就绪（最多 150 秒）"
for i in $(seq 1 30); do
  if port_up 2891 && curl -sf -m 2 http://127.0.0.1:8010/healthz >/dev/null 2>&1; then break; fi
  sleep 5
done

# 5. Dify 登录态（tools/*.sh 需要 cookies.txt）
if port_up 5001; then
  COOKIE="$HOME/dify/run/cookies.txt"
  mkdir -p "$(dirname "$COOKIE")"
  B64=$(printf 'InnAdmin123!' | base64)
  if curl -s -c "$COOKIE" -X POST http://127.0.0.1:5001/console/api/login \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"admin@inn.local\",\"password\":\"$B64\",\"remember_me\":true}" \
      -o /dev/null -w '%{http_code}' | grep -q 200; then
    say "Dify 登录成功，cookie 已写入 $COOKIE"
  else
    say "Dify 登录失败（应用是否已 setup？）"
  fi
fi

# 6. 状态汇总
echo
for pair in "seekdb:2891" "inn-api:8010" "powercontext:8090" "dify-api:5001" "dify-web:3000"; do
  name="${pair%%:*}"; port="${pair##*:}"
  printf '  %-14s :%-5s %s\n' "$name" "$port" "$(port_up "$port" && echo up || echo DOWN)"
done
curl -s -m 3 http://127.0.0.1:8010/healthz || true
echo
say "完成。合规自检：INN_APP_ID=${INN_APP_ID:-<未设置>} python3 tools/compliance_check.py"
