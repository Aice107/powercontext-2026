"""《记仇客栈》配套后端 inn-api。

职责边界（与 Dify 的分工，见运行说明 §分工）：
- 本服务只做 seekdb 的存储、检索、聚合；
- 不做"是不是恶作剧"的判定、不算档位、不生成台词——这些都在 Dify 的节点里。

接口：
  GET  /healthz
  GET  /inn/session   拉取/创建玩家档案（含最近旧账，供开场翻旧账）
  POST /inn/ledger    记一笔账（写 seekdb + 混合检索相似旧账）
  GET  /inn/ledger    查询账本（样例与排障用）
  POST /inn/rumor     落一条传闻
  GET  /inn/rumor     检索传闻（向量 + 全文）
  GET  /inn/line      台词库检索（按档位 + 全文）
  POST /inn/settle    打烊结算聚合
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from . import db, embedding, pc, rules

app = FastAPI(title="inn-api", version="0.1.0", description="记仇客栈 seekdb 数据层")

SCHEMA_VERSION = "2026-11-03"


# ---------------------------------------------------------------- 模型


class LedgerIn(BaseModel):
    player_id: str = Field("", max_length=64)
    session_id: str = Field("", max_length=64)
    turn: int = Field(0, ge=0, le=10000)
    action_text: str = Field(..., min_length=1, max_length=512)
    action_type: str = Field("other", max_length=32)
    severity: int = Field(0, ge=-3, le=5)
    target: str = Field("", max_length=64)
    scene: str = Field("大堂", max_length=32)
    conversation_id: str = Field("", max_length=64)


class RumorIn(BaseModel):
    player_id: str = Field("", max_length=64)
    conversation_id: str = Field("", max_length=64)
    severity: int = Field(0, ge=-3, le=5)
    source_event_id: int = Field(0, ge=0)
    rumor_text: str = Field(..., min_length=1, max_length=512)
    scene: str = Field("地窖", max_length=32)


class SettleIn(BaseModel):
    player_id: str = Field("", max_length=64)
    conversation_id: str = Field("", max_length=64)


# ---------------------------------------------------------------- 工具


def _days_ago(ts: Any) -> int:
    if isinstance(ts, datetime):
        d = ts.date()
    elif isinstance(ts, date):
        d = ts
    else:
        return 0
    return max(0, (date.today() - d).days)


def _ensure_player(player_id: str, nickname: str, session_id: str) -> dict:
    row = db.one("SELECT * FROM inn_player WHERE player_id=%s", (player_id,))
    if row:
        # 新会话（Dify conversation_id 变化）计一次住店；跨天回访 days_known +1
        new_session = bool(session_id) and session_id != (row.get("last_session_id") or "")
        db.execute(
            """UPDATE inn_player
                  SET last_seen=NOW(),
                      days_known=days_known + IF(DATE(last_seen) < CURDATE(), 1, 0),
                      visits=visits + IF(%s, 1, 0),
                      last_session_id=IF(%s, %s, last_session_id)
                WHERE player_id=%s""",
            (new_session, new_session, session_id, player_id),
        )
        return db.one("SELECT * FROM inn_player WHERE player_id=%s", (player_id,)) or row
    db.execute(
        """INSERT INTO inn_player (player_id, nickname, grudge, visits, total_events, days_known, last_session_id, last_seen)
           VALUES (%s, %s, 0, 1, 0, 1, %s, NOW())""",
        (player_id, nickname, session_id),
    )
    return db.one("SELECT * FROM inn_player WHERE player_id=%s", (player_id,)) or {}


def _recent_events(player_id: str, limit: int = 3) -> list[dict]:
    rows = db.query(
        """SELECT id, action_text, action_type, severity, scene, created_at
             FROM inn_ledger WHERE player_id=%s
            ORDER BY id DESC LIMIT %s""",
        (player_id, limit),
    )
    return [
        {
            "event_id": r["id"],
            "text": r["action_text"],
            "type": r["action_type"],
            "severity": r["severity"],
            "scene": r["scene"],
            "days_ago": _days_ago(r["created_at"]),
        }
        for r in rows
    ]


def _hybrid_similar(player_id: str, exclude_id: int, action_text: str, limit: int = 3) -> list[dict]:
    """单条 SQL 完成"结构化过滤 + 向量相似 + 全文命中"的混合检索。

    score = 0.7 * 向量相似度 + 0.3 * 全文相关性（归一到 0~1 后加权）
    """
    vec = embedding.to_literal(embedding.embed(action_text))
    rows = db.query(
        """SELECT id, action_text, severity, scene, created_at,
                  COSINE_SIMILARITY(embedding, %s) AS vsim,
                  MATCH(action_text) AGAINST (%s) AS ft
             FROM inn_ledger
            WHERE player_id=%s AND id<>%s AND severity>=1
            ORDER BY (0.7 * COSINE_SIMILARITY(embedding, %s) + 0.3 * (MATCH(action_text) AGAINST (%s) > 0)) DESC
            LIMIT %s""",
        (vec, action_text, player_id, exclude_id, vec, action_text, limit),
    )
    out = []
    for r in rows:
        out.append(
            {
                "event_id": r["id"],
                "text": r["action_text"],
                "severity": r["severity"],
                "scene": r["scene"],
                "days_ago": _days_ago(r["created_at"]),
                "vsim": round(float(r["vsim"] or 0), 4),
                "fulltext_hit": bool(r["ft"]),
                "score": round(0.7 * float(r["vsim"] or 0) + 0.3 * (1.0 if r["ft"] else 0.0), 4),
            }
        )
    return out




def _resolve_pid(player_id: str, conversation_id: str = "") -> str:
    """玩家标识解析。

    规则（写进运行说明）：
    1. 显式传入 player_id → 直接用（跨会话记忆靠它，样例 S4 用这条）；
    2. 未传但传了 conversation_id → 取会话 ID 的稳定哈希，同一会话始终同一个玩家；
    3. 都没有 → 随机生成。
    """
    pid = (player_id or "").strip()
    if pid:
        return pid[:64]
    cid = (conversation_id or "").strip()
    if cid:
        return "p_" + hashlib.sha1(cid.encode("utf-8")).hexdigest()[:10]
    return "p_" + secrets.token_hex(4)


def _pc_scope(player_id: str, nickname: str = "浪客") -> str | None:
    """取或建玩家的 PowerContext Scope（PC 未启用时返回 None）。"""
    if not pc.enabled():
        return None
    row = db.one("SELECT scope_id FROM inn_pc_scope WHERE player_id=%s", (player_id,))
    if row and row.get("scope_id"):
        return str(row["scope_id"])
    scope_id = pc.create_scope(player_id, nickname)
    if scope_id:
        db.execute(
            "INSERT INTO inn_pc_scope (player_id, scope_id) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE scope_id=VALUES(scope_id)",
            (player_id, scope_id),
        )
    return scope_id


def _memory_block(player_id: str, nickname: str = "浪客", query: str = "三娘对这个客人的印象") -> str:
    """召回"印象"类记忆，拼成一行供 prompt 使用；无 PC 时返回空串。"""
    scope_id = _pc_scope(player_id, nickname)
    if not scope_id:
        return ""
    hits = pc.search(scope_id, query, limit=3)
    return "；".join(h.strip() for h in hits if h.strip())[:400]

def _tier(grudge: int) -> int:
    return rules.tier_of(grudge)


def _block(rows: list[tuple[str, str]]) -> Response:
    """返回给 Dify 的上下文块（text/plain）。

    设计说明：Dify 的 HTTP 节点只能拿到响应 body 文本，没有 JSON 解析节点
    （本机无代码沙箱，Code 节点不可用）。因此后端额外提供 format=block：
    把本轮需要的事实压缩成 "KEY=VALUE" 行，既可直接塞进 LLM prompt，
    也可让 Dify 用 contains 做分支判断（例如 TIER=4 触发逐客）。
    """
    text = "\n".join(f"{k}={v}" for k, v in rows)
    return Response(content=text, media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------- 接口


@app.get("/healthz")
def healthz() -> dict:
    ok = db.ping()
    return {
        "status": "ok" if ok else "degraded",
        "seekdb": ok,
        "database": os.getenv("SEEKDB_DATABASE", "inn"),
        "schema_version": SCHEMA_VERSION,
        "powercontext": bool(pc.enabled()),
        "embedding_mode": embedding.MODE,
        "embedding_dim": embedding.DIM,
    }


@app.get("/inn/session")
def session(
    player_id: str = Query("", max_length=64),
    nickname: str = Query("浪客", max_length=64),
    session_id: str = Query("", max_length=64),
    conversation_id: str = Query("", max_length=64),
    format: str = Query("json", max_length=16),
) -> dict:
    player_id = _resolve_pid(player_id, conversation_id)
    player = _ensure_player(player_id, nickname, session_id)
    events = _recent_events(player_id, 3)
    if format == "block":
        grudge = int(player.get("grudge", 0))
        recent = ";".join(f"{e['text']}({e['severity']}级,{e['days_ago']}天前)" for e in events) or "无"
        return _block([
            ("PLAYER", player_id),
            ("GRUDGE", str(grudge)),
            ("TIER", str(_tier(grudge))),
            ("VISITS", str(int(player.get("visits", 1)))),
            ("DAYS", str(int(player.get("days_known", 1)))),
            ("EVENTS", str(int(player.get("total_events", 0)))),
            ("RECENT", recent),
            ("MEMORY", _memory_block(player_id, player.get("nickname") or nickname) or "无"),
            ("LINES", "；".join(
                r["text"] for r in db.query(
                    "SELECT text FROM inn_line WHERE tier=%s ORDER BY id DESC LIMIT 2", (_tier(grudge),)
                )
            )[:300] or "无"),
        ])
    return {
        "player_id": player_id,
        "nickname": player.get("nickname", nickname),
        "grudge": int(player.get("grudge", 0)),
        "visits": int(player.get("visits", 1)),
        "days_known": int(player.get("days_known", 1)),
        "total_events": int(player.get("total_events", 0)),
        "last_seen": str(player.get("last_seen", "")),
        "recent_events": events,
        # PowerContext Scope 约定：一个玩家一个 Scope，前缀固定，便于评审核对
        "scope_hint": f"inn:player:{player_id}",
        "memory": _memory_block(player_id, player.get("nickname") or nickname) or None,
    }


@app.post("/inn/ledger")
def ledger_write(body: LedgerIn, format: str = Query("json", max_length=16)):
    body.player_id = _resolve_pid(body.player_id, body.conversation_id)

    if body.severity == 0:
        return {"recorded": False, "reason": "no event (severity=0)", "grudge": None}

    player = db.one("SELECT * FROM inn_player WHERE player_id=%s", (body.player_id,))
    if not player:
        # 容错：未先调用 /inn/session 时自动建档（评审漏步也不会 500）
        player = _ensure_player(body.player_id, "浪客", body.session_id)

    action_type = body.action_type if body.action_type in rules.ACTION_TYPES else "other"
    # 归一化：severity 为负一定是善举，避免模型把 action_type 误判成 property
    if body.severity < 0:
        action_type = "kindness"
    repeat_cnt = db.one(
        """SELECT COUNT(*) AS c FROM inn_ledger
            WHERE player_id=%s AND action_type=%s AND severity>=1""",
        (body.player_id, action_type),
    )
    repeat = int((repeat_cnt or {}).get("c", 0))

    before = int(player.get("grudge", 0))
    delta = rules.grudge_delta(body.severity, repeat)
    after = rules.clamp_grudge(before + delta)

    vec = embedding.to_literal(embedding.embed(body.action_text))
    db.execute(
        """INSERT INTO inn_ledger
             (player_id, session_id, turn, action_text, action_type, severity, target, scene, grudge_after, embedding)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            body.player_id,
            body.session_id,
            body.turn,
            body.action_text,
            action_type,
            body.severity,
            body.target,
            body.scene,
            after,
            vec,
        ),
    )
    event_id = int((db.one("SELECT MAX(id) AS id FROM inn_ledger WHERE player_id=%s", (body.player_id,)) or {}).get("id", 0))

    db.execute(
        """UPDATE inn_player
              SET grudge=%s, total_events=total_events+1, last_seen=NOW()
            WHERE player_id=%s""",
        (after, body.player_id),
    )

    # PowerContext：把"事件"提炼成"对这个人的印象"（只写摘要，不写对话原文）
    scope_id = _pc_scope(body.player_id, player.get("nickname") or "浪客")
    if scope_id:
        tier_word = {0: "和善", 1: "戒备", 2: "冷脸", 3: "报复", 4: "逐客"}[_tier(after)]
        kind = "task-outcome" if body.severity < 0 else "current-state"
        pc.remember(
            scope_id,
            kind,
            (
                f"柳三娘对{player.get('nickname') or '浪客'}（{body.player_id}）的印象：{tier_word}。"
                f"最近一次在{body.scene}{body.action_text}（{action_type}，{body.severity}级，第{repeat + 1}次），"
                f"仇值 {after}。"
            )[:800],
        )

    similar = _hybrid_similar(body.player_id, event_id, body.action_text)
    total_events = int((db.one("SELECT total_events FROM inn_player WHERE player_id=%s", (body.player_id,)) or {}).get("total_events", 0))

    if format == "block":
        sim = ";".join(f"{x['text']}({x['severity']}级,{x['days_ago']}天前)" for x in similar) or "无"
        tier_now = _tier(after)
        anchor = db.query(
            "SELECT text FROM inn_line WHERE tier=%s ORDER BY id DESC LIMIT 2",
            (tier_now,),
        )
        lines_txt = "；".join(r["text"] for r in anchor) or "无"
        return _block([
            ("EVENT", str(event_id)),
            ("TYPE", action_type),
            ("SEV", str(body.severity)),
            ("DELTA", str(delta)),
            ("REPEAT", str(repeat)),
            ("GRUDGE", str(after)),
            ("TIER", str(_tier(after))),
            ("SIM", sim),
            ("LINES", lines_txt[:300]),
        ])

    return {
        "recorded": True,
        "event_id": event_id,
        "player_id": body.player_id,
        "action_type": action_type,
        "severity": body.severity,
        "repeat_cnt": repeat,          # 同类事件历史次数（"屡教不改"依据）
        "grudge_before": before,
        "delta": delta,
        "grudge_after": after,
        "total_events": total_events,
        "similar": similar,            # 翻旧账素材（seekdb 混合检索结果）
    }


@app.get("/inn/ledger")
def ledger_list(
    player_id: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    rows = db.query(
        """SELECT id, action_text, action_type, severity, scene, grudge_after, created_at
             FROM inn_ledger WHERE player_id=%s ORDER BY id DESC LIMIT %s""",
        (player_id, limit),
    )
    return {
        "player_id": player_id,
        "count": len(rows),
        "events": [
            {
                "event_id": r["id"],
                "text": r["action_text"],
                "type": r["action_type"],
                "severity": r["severity"],
                "scene": r["scene"],
                "grudge_after": r["grudge_after"],
                "days_ago": _days_ago(r["created_at"]),
            }
            for r in rows
        ],
    }


@app.post("/inn/rumor")
def rumor_write(body: RumorIn) -> dict:
    body.player_id = _resolve_pid(body.player_id, body.conversation_id)
    if body.severity < 4:
        # 低严重度事件不成传闻：避免传闻表被灌水
        return {"created": False, "reason": "severity<4"}
    vec = embedding.to_literal(embedding.embed(body.rumor_text))
    db.execute(
        """INSERT INTO inn_rumor (player_id, source_event_id, rumor_text, spread, scene, embedding)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (body.player_id, body.source_event_id, body.rumor_text, 1, body.scene, vec),
    )
    rid = int((db.one("SELECT MAX(id) AS id FROM inn_rumor WHERE player_id=%s", (body.player_id,)) or {}).get("id", 0))
    return {"created": True, "rumor_id": rid, "player_id": body.player_id, "scene": body.scene}


@app.get("/inn/rumor")
def rumor_search(
    player_id: str = Query(..., min_length=1),
    q: str = Query("", max_length=256),
    limit: int = Query(3, ge=1, le=20),
) -> dict:
    if q:
        vec = embedding.to_literal(embedding.embed(q))
        rows = db.query(
            """SELECT id, rumor_text, scene, spread, created_at,
                      COSINE_SIMILARITY(embedding, %s) AS vsim,
                      MATCH(rumor_text) AGAINST (%s) AS ft
                 FROM inn_rumor WHERE player_id=%s
                ORDER BY (0.7 * COSINE_SIMILARITY(embedding, %s) + 0.3 * (MATCH(rumor_text) AGAINST (%s) > 0)) DESC
                LIMIT %s""",
            (vec, q, player_id, vec, q, limit),
        )
    else:
        rows = db.query(
            "SELECT id, rumor_text, scene, spread, created_at FROM inn_rumor WHERE player_id=%s ORDER BY id DESC LIMIT %s",
            (player_id, limit),
        )
    return {
        "player_id": player_id,
        "count": len(rows),
        "rumors": [
            {
                "rumor_id": r["id"],
                "text": r["rumor_text"],
                "scene": r["scene"],
                "days_ago": _days_ago(r["created_at"]),
            }
            for r in rows
        ],
    }


@app.get("/inn/line")
def line_search(
    tier: int = Query(-1, ge=-1, le=4),
    scene: str = Query("", max_length=32),
    q: str = Query("", max_length=256),
    limit: int = Query(3, ge=1, le=20),
    format: str = Query("json", max_length=16),
):
    sql = "SELECT id, npc, scene, tier, tone, text FROM inn_line WHERE 1=1"
    args: list[Any] = []
    if tier >= 0:
        sql += " AND tier=%s"
        args.append(tier)
    if scene:
        sql += " AND scene=%s"
        args.append(scene)
    if q:
        sql += " AND MATCH(text) AGAINST (%s)"
        args.append(q)
    sql += " ORDER BY id DESC LIMIT %s"
    args.append(limit)
    rows = db.query(sql, args)
    if format == "block":
        # 给 LLM 的语气锚点：同类事件的旧台词，直接拼进 prompt
        txt = "；".join(str(r.get("text", "")) for r in rows) or "无"
        return _block([("LINES", txt[:400])])
    return {"count": len(rows), "lines": rows}


@app.post("/inn/settle")
def settle(body: SettleIn | None = None, format: str = Query("json", max_length=16)):
    body = body or SettleIn()
    body.player_id = _resolve_pid(body.player_id, body.conversation_id)
    player = db.one("SELECT * FROM inn_player WHERE player_id=%s", (body.player_id,))
    if not player:
        raise HTTPException(status_code=404, detail=f"player not found: {body.player_id}")

    stats = db.one(
        """SELECT COUNT(*) AS events,
                  COALESCE(SUM(CASE WHEN severity>0 THEN severity*6 ELSE 0 END),0) AS attack,
                  COALESCE(SUM(CASE WHEN severity<0 THEN -severity*8 ELSE 0 END),0) AS repair,
                  COALESCE(MAX(severity),0) AS max_severity
             FROM inn_ledger WHERE player_id=%s""",
        (body.player_id,),
    ) or {}

    top = db.query(
        """SELECT action_text, action_type, severity, created_at
             FROM inn_ledger WHERE player_id=%s AND severity>0
            ORDER BY severity DESC, id DESC LIMIT 3""",
        (body.player_id,),
    )
    by_type = db.query(
        """SELECT action_type, COUNT(*) AS c FROM inn_ledger
            WHERE player_id=%s AND severity>0 GROUP BY action_type ORDER BY c DESC""",
        (body.player_id,),
    )
    rumors = db.query(
        "SELECT rumor_text, scene FROM inn_rumor WHERE player_id=%s ORDER BY id DESC LIMIT 2",
        (body.player_id,),
    )

    if format == "block":
        top = ";".join(f"{r['action_text']}({r['severity']}级,{_days_ago(r['created_at'])}天前)" for r in top) or "无"
        rumors_txt = ";".join(f"{r['rumor_text']}" for r in rumors) or "无"
        return _block([
            ("GRUDGE", str(int(player.get("grudge", 0)))),
            ("TIER", str(_tier(int(player.get("grudge", 0))))),
            ("EVENTS", str(int(stats.get("events", 0)))),
            ("ATTACK", str(int(stats.get("attack", 0)))),
            ("REPAIR", str(int(stats.get("repair", 0)))),
            ("VISITS", str(int(player.get("visits", 1)))),
            ("DAYS", str(int(player.get("days_known", 1)))),
            ("TOP", top),
            ("RUMORS", rumors_txt),
        ])

    return {
        "player_id": body.player_id,
        "nickname": player.get("nickname"),
        "grudge": int(player.get("grudge", 0)),
        "visits": int(player.get("visits", 1)),
        "days_known": int(player.get("days_known", 1)),
        "events": int(stats.get("events", 0)),
        "attack_total": int(stats.get("attack", 0)),
        "repair_total": int(stats.get("repair", 0)),
        "max_severity": int(stats.get("max_severity", 0)),
        "top3": [
            {
                "text": r["action_text"],
                "type": r["action_type"],
                "severity": r["severity"],
                "days_ago": _days_ago(r["created_at"]),
            }
            for r in top
        ],
        "by_type": [{"type": r["action_type"], "count": int(r["c"])} for r in by_type],
        "rumors": [{"text": r["rumor_text"], "scene": r["scene"]} for r in rumors],
    }
