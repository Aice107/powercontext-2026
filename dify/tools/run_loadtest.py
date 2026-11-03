#!/usr/bin/env python3
"""20 轮连打压测：仇值曲线 / 时延分布 / 记忆与传闻增长。

跑法：
    python3 tools/run_loadtest.py [turns] [player_id]

依赖本机开发态：
- Dify 控制台 cookie：~/dify/run/cookies.txt
- 应用 ID：tools/.local.env 里的 INN_APP_ID
- inn-api：http://127.0.0.1:8010（用于读状态）

输出：evidence/logs/run-loadtest.md（表格 + 结论）
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("INN_API", "http://127.0.0.1:8010")
DIFY = os.getenv("DIFY_BASE", "http://127.0.0.1:5001")
COOKIE = os.getenv("DIFY_COOKIE", "/home/ice/dify/run/cookies.txt")
SEEKDB = ["mysql", "-h", "127.0.0.1", "-P", os.getenv("SEEKDB_PORT", "2891"), "-uroot", "-N", "-B", "-e"]


def local_env() -> dict[str, str]:
    out: dict[str, str] = {}
    f = ROOT / "tools" / ".local.env"
    if f.is_file():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def cookie_header() -> str:
    parts = []
    for line in Path(COOKIE).read_text().splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        elif line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) >= 7:
            parts.append(f"{f[5]}={f[6]}")
    return "; ".join(parts)


def csrf() -> str:
    for line in Path(COOKIE).read_text().splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        f = line.split("\t")
        if len(f) >= 7 and f[5] == "csrf_token":
            return f[6]
    return ""


def run_turn(app_id: str, query: str, player: str) -> tuple[str, float, str]:
    payload = json.dumps({"inputs": {"player_id": player}, "files": [], "query": query}).encode()
    req = urllib.request.Request(
        f"{DIFY}/console/api/apps/{app_id}/advanced-chat/workflows/draft/run",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header(),
            "X-CSRF-Token": csrf(),
        },
    )
    t0 = time.time()
    answer, status = "", ""
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get("event") == "workflow_finished":
                d = ev.get("data", {}) or {}
                status = d.get("status", "")
                answer = str((d.get("outputs") or {}).get("answer") or "")
            if ev.get("event") == "message":
                answer = answer or str(ev.get("answer") or "")
    return status, time.time() - t0, answer


def mysql(sql: str) -> str:
    return subprocess.run(SEEKDB + [sql], capture_output=True, text=True, timeout=30).stdout.strip()


def player_state(player: str) -> tuple[int, int, int]:
    row = mysql(
        f"SELECT grudge, total_events, days_known FROM inn.inn_player WHERE player_id='{player}'"
    )
    if not row:
        return 0, 0, 0
    g, e, d = row.split("\t")
    return int(g), int(e), int(d)


PLAN = [
    ("往酒坛里兑半坛水", "drink", 2),
    ("偷吃灶上留的酱牛肉", "food", 2),
    ("在她账本上画只乌龟", "property", 3),
    ("半夜在屋顶学猫叫", "noise", 2),
    ("我把屋顶漏雨的地方修好了", "kindness", -3),
]


def main() -> int:
    turns = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    player = sys.argv[2] if len(sys.argv) > 2 else f"p_load_{int(time.time()) % 100000}"
    app_id = local_env().get("INN_APP_ID", "")
    if not app_id:
        print("tools/.local.env 缺少 INN_APP_ID")
        return 1

    # 建档
    urllib.request.urlopen(f"{API}/inn/session?player_id={player}&format=block", timeout=15).read()

    rows = []
    for i in range(turns):
        q, typ, sev = PLAN[i % len(PLAN)]
        status, dt, answer = run_turn(app_id, q, player)
        g, e, d = player_state(player)
        rows.append(
            {
                "turn": i + 1,
                "query": q,
                "type": typ,
                "sev": sev,
                "status": status,
                "latency": dt,
                "grudge": g,
                "events": e,
                "answer_len": len(answer),
            }
        )
        print(f"turn {i + 1:>2} {q[:12]:<14} status={status:<18} {dt:5.1f}s grudge={g:>3} events={e}")

    lat = sorted(r["latency"] for r in rows)
    p50 = statistics.median(lat)
    p95 = lat[max(0, int(len(lat) * 0.95) - 1)]
    grudge_seq = [r["grudge"] for r in rows]
    mem = mysql(f"SELECT COUNT(*) FROM inn.inn_pc_scope WHERE player_id='{player}'")
    rumors = mysql(f"SELECT COUNT(*) FROM inn.inn_rumor WHERE player_id='{player}'")
    events = mysql(f"SELECT COUNT(*) FROM inn.inn_ledger WHERE player_id='{player}'")

    out = ROOT / "evidence" / "logs" / "run-loadtest.md"
    lines = [
        f"# 连打压测（{turns} 轮）{time.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- 玩家：`{player}`（本轮新建）",
        f"- 序列：每 5 轮一个循环（兑水 / 偷吃 / 画乌龟 / 学猫叫 / 修屋顶行善）",
        "",
        "| 轮次 | 输入 | 类型 | 严重度 | 状态 | 时延(s) | 累计仇值 | 累计事件 |",
        "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['turn']} | {r['query']} | {r['type']} | {r['sev']} | {r['status']} | "
            f"{r['latency']:.1f} | {r['grudge']} | {r['events']} |"
        )
    lines += [
        "",
        "## 结论",
        "",
        f"- 成功轮次：{sum(1 for r in rows if r['status'] == 'succeeded')}/{len(rows)}",
        f"- 端到端时延：中位数 **{p50:.1f}s**，P95 **{p95:.1f}s**，最大 {max(lat):.1f}s（含 2 次 LLM 调用：判定 + 回应）",
        f"- 仇值曲线：{grudge_seq[0]} → 峰值 {max(grudge_seq)} → 末值 {grudge_seq[-1]}（clamp 0–100，逐客后仍可被善举拉回）",
        f"- seekdb：账本 {events} 行；PowerContext scope {mem} 个；传闻 {rumors} 条"
        f"（传闻只在判定为 `severity ≥ 4` 时产生，本序列最高 {max(r['sev'] for r in rows)}，实际产生 {rumors} 条）",
        "",
        "> 说明：每轮写 1 条账本 + 1 条 PowerContext 记忆（善举写 task-outcome）；",
        "> 判定由 LLM 完成，同一句话在不同轮次的严重度可能略有浮动（例如「学猫叫」被判 2 或 4），",
        "> 这正是把「事件事实」落在 seekdb、把「语气」交给 prompt 的原因。",
    ]
    out.write_text("\n".join(lines) + "\n")
    print(f"\n报告：{out}")
    print(f"时延 p50={p50:.1f}s p95={p95:.1f}s；账本 {events} 行；仇值峰值 {max(grudge_seq)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
