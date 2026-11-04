"""PowerContext-backed task state: save, restart, load, reuse."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

STATE_PREFIX = "SDD_TASK_STATE_V1 "
STATE_KIND = "sdd-task-state"
DEFAULT_URL = "http://127.0.0.1:8093"
DEFAULT_SCOPE_KEY = "sdd-context-taskhub-demo"


class PowerContextError(RuntimeError):
    """PowerContext is unavailable or rejected a request."""


class TaskStateStore:
    def __init__(
        self,
        base_url: str | None = None,
        scope_key: str | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("POWERCONTEXT_URL") or DEFAULT_URL).rstrip("/")
        self.scope_key = scope_key or os.environ.get("POWERCONTEXT_SCOPE_KEY") or DEFAULT_SCOPE_KEY
        self.timeout = timeout
        self._scope_id: str | None = None

    # ------------------------------------------------------------------ HTTP
    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise PowerContextError(f"PowerContext {method} {path} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise PowerContextError(
                f"PowerContext is not reachable at {self.base_url}: {exc.reason}. "
                "Start it with scripts/pc_server.sh start."
            ) from exc
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise PowerContextError(f"PowerContext returned non-JSON for {path}: {body[:300]}") from exc

    def health(self) -> bool:
        try:
            self._request("GET", "/health/live")
            return True
        except PowerContextError:
            return False

    def ensure_scope(self) -> str:
        if self._scope_id:
            return self._scope_id
        response = self._request(
            "POST",
            "/v1/scopes",
            {
                "title": "SDD TaskHub demo",
                "summary": "Task state for the MiniMax x OceanBase SDD context demo",
                "idempotency_key": self.scope_key,
            },
        )
        scope_id = response.get("scope_id")
        if not scope_id:
            raise PowerContextError(f"scope creation returned no scope_id: {response}")
        self._scope_id = str(scope_id)
        return self._scope_id

    # ------------------------------------------------------------------ state
    def save_state(self, state: dict[str, Any], *, reason: str = "sdd_context verification") -> dict[str, Any]:
        scope_id = self.ensure_scope()
        text = STATE_PREFIX + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode("utf-8")) > 8192:
            raise PowerContextError("task state exceeds PowerContext's 8192-byte Memory limit")
        response = self._request(
            "POST",
            "/v1/memory/remember",
            {
                "scope_id": scope_id,
                "kind": STATE_KIND,
                "text": text,
                "reason": reason[:512],
            },
        )
        record = (response.get("records") or [{}])[0]
        artifact = record.get("artifact", {})
        return {
            "scope_id": scope_id,
            "artifact_id": artifact.get("artifact_id"),
            "revision": artifact.get("revision"),
            "changed": response.get("changed"),
            "text_bytes": len(text.encode("utf-8")),
            "saved_at": state.get("saved_at"),
        }

    def list_states(self, *, limit: int = 100) -> list[dict[str, Any]]:
        scope_id = self.ensure_scope()
        response = self._request(
            "POST",
            "/v1/memory/entries/list",
            {"scope_id": scope_id, "include_inactive": True, "limit": limit},
        )
        states: list[dict[str, Any]] = []
        for entry in response.get("entries", []):
            text = entry.get("text") or ""
            if entry.get("kind") != STATE_KIND or not text.startswith(STATE_PREFIX):
                continue
            try:
                payload = json.loads(text[len(STATE_PREFIX) :])
            except json.JSONDecodeError:
                continue
            payload["_artifact_id"] = (entry.get("artifact") or {}).get("artifact_id")
            payload["_revision"] = (entry.get("artifact") or {}).get("revision")
            states.append(payload)
        return states

    def load_state(self, task_id: str) -> dict[str, Any] | None:
        states = [state for state in self.list_states() if state.get("task_id") == task_id]
        if not states:
            return None
        states.sort(
            key=lambda state: (int(state.get("saved_at_ns") or 0), str(state.get("saved_at", ""))),
            reverse=True,
        )
        return states[0]

    def scope_id(self) -> str:
        return self.ensure_scope()


def write_scope_cache(path: str | Path, scope_id: str) -> None:
    Path(path).write_text(json.dumps({"scope_id": scope_id}), encoding="utf-8")


def read_scope_cache(path: str | Path) -> str | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("scope_id")
    except (OSError, json.JSONDecodeError):
        return None
