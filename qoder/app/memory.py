"""PowerContext HTTP 客户端封装：跨会话记住用户偏好、约束与进度。

每次请求与响应都落到 JSONL 证据日志，供评审核对"记忆确实被写入并在后续使用中复用"。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass
class MemoryCall:
    endpoint: str
    request: dict
    response: dict
    status: int
    elapsed_ms: float

    def as_record(self) -> dict:
        return {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "endpoint": self.endpoint,
            "request": self.request,
            "response": self.response,
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


class PowerContextMemory:
    def __init__(self, settings: Settings, journal=None) -> None:
        self.settings = settings
        self.journal = journal
        self._client = httpx.Client(base_url=settings.pc_base_url, timeout=20.0)
        headers = {}
        if settings.pc_token:
            headers["Authorization"] = f"Bearer {settings.pc_token}"
        self._headers = headers
        self._scope_id: str | None = None

    # ---------- 基础 ----------

    def _call(self, endpoint: str, payload: dict) -> MemoryCall:
        started = time.perf_counter()
        response = self._client.post(endpoint, json=payload, headers=self._headers)
        elapsed = (time.perf_counter() - started) * 1000
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:2000]}
        call = MemoryCall(endpoint, payload, body, response.status_code, elapsed)
        if self.journal is not None:
            self.journal.append("powercontext", call.as_record())
        return call

    def health(self) -> dict:
        started = time.perf_counter()
        try:
            response = self._client.get("/health/ready", headers=self._headers)
            return {"ok": response.status_code == 200, "status": response.status_code,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
        except Exception as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    # ---------- scope ----------

    @property
    def scope_id(self) -> str:
        return self._scope_id or f"gewu-{self.settings.scope_owner}"

    def ensure_scope(self) -> str:
        if self._scope_id is not None:
            return self._scope_id
        payload = {
            "title": f"格物 · {self.settings.scope_owner}",
            "summary": "科研笔记管家与组会汇报助手的用户记忆空间：写作偏好、课题约束与进行中的事项。",
            "idempotency_key": f"gewu-owner-{self.settings.scope_owner}-{uuid.uuid5(uuid.NAMESPACE_URL, self.scope_id).hex[:12]}",
        }
        call = self._call("/v1/scopes", payload)
        body = call.response
        scope_id = (
            body.get("scope", {}).get("id")
            or body.get("id")
            or body.get("scope_id")
            or self.scope_id
        )
        self._scope_id = str(scope_id)
        return self._scope_id

    # ---------- 记忆读写 ----------

    def remember(self, kind: str, text: str, reason: str = "") -> dict:
        self.ensure_scope()
        payload: dict = {"scope_id": self.scope_id, "kind": kind, "text": text}
        if reason:
            payload["reason"] = reason
        call = self._call("/v1/memory/remember", payload)
        if call.status >= 400:
            raise RuntimeError(f"PowerContext remember 失败({call.status}): {json.dumps(call.response, ensure_ascii=False)[:300]}")
        return {"ok": True, "endpoint": "/v1/memory/remember", "request": payload,
                "response": call.response, "elapsed_ms": call.elapsed_ms}

    def search(self, query: str, *, mode: str = "hybrid", limit: int = 6) -> dict:
        self.ensure_scope()
        payload = {"scope_id": self.scope_id, "query": query, "mode": mode, "limit": limit}
        call = self._call("/v1/memory/search", payload)
        if call.status >= 400:
            raise RuntimeError(f"PowerContext search 失败({call.status}): {json.dumps(call.response, ensure_ascii=False)[:300]}")
        hits = _extract_hits(call.response)
        return {"query": query, "mode": mode, "hits": hits,
                "endpoint": "/v1/memory/search", "request": payload,
                "elapsed_ms": call.elapsed_ms}

    def prepare(self, query: str, max_bytes: int = 2500) -> dict:
        self.ensure_scope()
        payload = {"scope_id": self.scope_id, "query": query, "max_bytes": max_bytes}
        call = self._call("/v1/context/prepare", payload)
        if call.status >= 400:
            raise RuntimeError(f"PowerContext prepare 失败({call.status}): {json.dumps(call.response, ensure_ascii=False)[:300]}")
        body = call.response
        return {"status": body.get("status"), "context": body.get("context") or body,
                "endpoint": "/v1/context/prepare", "request": payload, "elapsed_ms": call.elapsed_ms}


def _extract_hits(body: dict) -> list[dict]:
    """PowerContext 的响应里命中列表的字段名有多个变体，这里统一兼容。"""
    for key in ("hits", "memories", "items", "results"):
        value = body.get(key)
        if isinstance(value, list):
            return value
    inner = body.get("memory_search") or body.get("result") or {}
    if isinstance(inner, dict):
        for key in ("hits", "memories", "items"):
            if isinstance(inner.get(key), list):
                return inner[key]
    return []
