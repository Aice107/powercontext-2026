#!/usr/bin/env bash
# 把演示环境恢复到"评审第一次打开"的状态：
#   1) seekdb：重建表 + 重灌台词/传闻/演示玩家
#   2) PowerContext：清空记忆库并重启（否则 PC 里还留着上一轮的"仇值 100"印象，与账本矛盾）
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PC_DIR="$ROOT/../.pc"
PC_ENV="$PC_DIR/pc.env"

echo "[1/3] 重建 seekdb 数据"
bash db/init.sh

echo "[2/3] 清空 PowerContext 记忆"
if [ -f "$PC_ENV" ]; then
  # 按端口杀（进程 exec 后命令行是 "powercontext serve"，按名字匹配不可靠）
  PIDS=$(ss -lntp 2>/dev/null | awk '/:8090 /{print $NF}' | grep -oE "pid=[0-9]+" | cut -d= -f2)
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  for i in $(seq 1 10); do
    ss -lnt 2>/dev/null | grep -q ":8090 " || break
    sleep 1
  done
  rm -f "$PC_DIR"/pc.db "$PC_DIR"/pc.db-* 2>/dev/null
  ( cd "$PC_DIR" && PATH="$HOME/.local/bin:$PATH" nohup powercontext server run \
      --host 127.0.0.1 --port 8090 --env-file "$PC_ENV" > pc.log 2>&1 & )
  for i in $(seq 1 20); do
    curl -sf -m 2 http://127.0.0.1:8090/health/ready >/dev/null 2>&1 && break
    sleep 2
  done
  echo "[3/3] PowerContext 已重启"
else
  echo "[3/3] 未找到 $PC_ENV，跳过记忆重置"
fi

echo
echo "恢复完成。演示玩家：p_demo01（仇值 62 / T3 / 7 条旧账）"
