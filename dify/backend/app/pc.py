"""PowerContext 记忆客户端（可选层）。

分工：
- seekdb 记"事"：事件、数值、检索；
- PowerContext 记"人"：对角色的印象、关系摘要，供跨会话 prompt 注入。

设计约束：
1. **可选**：未配置 `PC_BASE_URL` 或调用失败时静默降级，不影响 seekdb 主链路；
2. 超时 3 秒，失败只记日志，不阻塞记账；
3. 一个玩家一个 Scope（`idempotency_key=inn:player:<player_id>`），scope_id 落在 seekdb 的
   `inn_pc_scope` 表里，保证重启后复用。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("inn.pc")

BASE = os.getenv("PC_BASE_URL", "").rstrip("/")
TIMEOUT = float(os.getenv("PC_TIMEOUT", "3"))
TOKEN = os.getenv("PC_TOKEN", "")


def enabled() -> bool:
    return bool(BASE)


def _post(path: str, payload: dict) -> dict | None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        log.warning("powercontext %s failed: %s", path, exc)
        return None


def create_scope(player_id: str, nickname: str = "浪客") -> str | None:
    """幂等创建玩家 Scope，返回 scope_id。"""
    data = _post(
        "/v1/scopes",
        {
            "title": f"客栈账本·{nickname}",
            "summary": f"记仇客栈中玩家 {player_id} 的记忆隔离单元：三娘对他的印象与关系。",
            "idempotency_key": f"inn:player:{player_id}",
        },
    )
    if data and data.get("scope_id"):
        return str(data["scope_id"])
    return None


def remember(scope_id: str, kind: str, text: str) -> bool:
    """写一条记忆（kind 用 PowerContext 允许的枚举：current-state / agent-note / task-outcome）。"""
    data = _post("/v1/memory/remember", {"scope_id": scope_id, "kind": kind, "text": text})
    return bool(data and data.get("changed"))


def search(scope_id: str, query: str, limit: int = 3) -> list[str]:
    """召回记忆文本，失败返回空列表（调用方按"无记忆"处理）。"""
    data = _post(
        "/v1/memory/search",
        {"scope_id": scope_id, "query": query, "limit": limit, "mode": "auto"},
    )
    if not data:
        return []
    out = []
    for hit in data.get("hits", []):
        mem = (hit or {}).get("memory", {})
        text = mem.get("text")
        if text:
            out.append(str(text))
    return out
