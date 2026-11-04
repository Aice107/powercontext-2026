"""MiniMax code-edit loop: prompt, call, extract, apply, record."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import render_markdown

SYSTEM_PROMPT = """You are MiniMax, a careful senior software engineer working in a Spec-Driven Development loop.

You receive a task, the applicable specification clauses, the current code, the tests and any saved progress.
Produce the smallest correct code change.

Hard requirements:
1. Return exactly one unified diff fenced with ```diff ... ``` and no prose outside it.
2. The diff must use paths relative to the workspace root (for example `app/store.py`).
3. Only modify files under `app/`. Never modify `tests/` or `specs/`.
4. Do not delete, skip or weaken tests. Do not change expected values.
5. Implement every clause in SPEC-API-013, including the inclusive boundary and invalid-date handling.
6. Preserve all existing behaviour described by the regression specification and tests.
"""


class MiniMaxUnavailable(RuntimeError):
    """No usable MiniMax credentials were configured."""


class MiniMaxError(RuntimeError):
    """MiniMax returned an unusable response."""


@dataclass
class MiniMaxConfig:
    api_key: str | None
    base_url: str
    model: str
    style: str
    timeout: float

    @classmethod
    def from_env(cls) -> "MiniMaxConfig":
        return cls(
            api_key=os.environ.get("MINIMAX_API_KEY") or None,
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1").rstrip("/"),
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.1"),
            style=os.environ.get("MINIMAX_API_STYLE", "openai").lower(),
            timeout=float(os.environ.get("MINIMAX_TIMEOUT", "120")),
        )

    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions") or self.base_url.endswith("/text/chatcompletion_v2"):
            return self.base_url
        if self.style == "native":
            return self.base_url + "/text/chatcompletion_v2"
        return self.base_url + "/chat/completions"


def build_prompt(context: dict[str, Any]) -> tuple[str, str]:
    task = context["task"]
    user = "\n".join(
        [
            f"# Task: {task['title']}",
            "",
            task["description"].strip(),
            "",
            "## Source-cited development context",
            "",
            render_markdown(context),
            "",
            "## Output contract",
            "",
            "Return only the unified diff. The change must make the target tests in",
            "`tests/test_due_before.py` pass while keeping `tests/test_tasks_regression.py` green.",
            "Do not touch tests or specifications.",
        ]
    )
    return SYSTEM_PROMPT, user


def call_minimax(system: str, user: str, config: MiniMaxConfig) -> dict[str, Any]:
    if not config.api_key:
        raise MiniMaxUnavailable(
            "MINIMAX_API_KEY is not set. Export a real MiniMax token plan key before running the "
            "MiniMax step; replaying a recorded patch is not evidence of MiniMax participation."
        )
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "stream": False,
    }
    request = urllib.request.Request(
        config.endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise MiniMaxError(f"MiniMax HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MiniMaxError(f"MiniMax transport error: {exc.reason}") from exc
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise MiniMaxError(f"MiniMax returned non-JSON: {body[:500]}") from exc
    if data.get("base_resp", {}).get("status_code") not in (None, 0):
        raise MiniMaxError(f"MiniMax base_resp error: {data.get('base_resp')}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MiniMaxError(f"MiniMax response has no choices[0].message.content: {body[:800]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise MiniMaxError("MiniMax returned an empty completion")
    return {
        "content": content,
        "usage": data.get("usage") or {},
        "latency_ms": latency_ms,
        "model": data.get("model") or config.model,
        "endpoint": config.endpoint(),
        "raw_id": data.get("id"),
    }


def extract_patch(content: str) -> str:
    fenced = re.search(r"```(?:diff|patch)\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip() + "\n"
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- a/"):
            return "\n".join(lines[index:]).strip() + "\n"
    raise MiniMaxError("response did not contain a unified diff")


def validate_patch_paths(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0].strip()
        if raw == "/dev/null":
            continue
        if raw.startswith("a/") or raw.startswith("b/"):
            raw = raw[2:]
        if raw.startswith("/") or ".." in Path(raw).parts:
            raise MiniMaxError(f"patch contains an unsafe path: {raw}")
        if not raw.startswith("app/"):
            raise MiniMaxError(f"patch may only modify app/, got {raw}")
        if raw not in files:
            files.append(raw)
    if not files:
        raise MiniMaxError("patch does not modify any app/ file")
    return files


def apply_patch(workspace: str | Path, patch_text: str) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    files = validate_patch_paths(patch_text)
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as handle:
        handle.write(patch_text)
        patch_path = Path(handle.name)
    try:
        check = _run(["git", "apply", "--check", str(patch_path)], workspace)
        if check["exit_code"] != 0:
            check = _run(["patch", "-p1", "--dry-run", "-i", str(patch_path)], workspace)
        if check["exit_code"] != 0:
            raise MiniMaxError(f"patch does not apply: {check['stderr'] or check['stdout']}")
        applied = _run(["git", "apply", str(patch_path)], workspace)
        if applied["exit_code"] != 0:
            applied = _run(["patch", "-p1", "-i", str(patch_path)], workspace)
        if applied["exit_code"] != 0:
            raise MiniMaxError(f"patch application failed: {applied['stderr'] or applied['stdout']}")
    finally:
        patch_path.unlink(missing_ok=True)
    return {"applied": True, "files": files, "check_stdout": check["stdout"], "apply_stdout": applied["stdout"]}


def _run(command: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def generate_and_apply(
    context: dict[str, Any],
    workspace: str | Path,
    evidence_dir: str | Path,
) -> dict[str, Any]:
    evidence_dir = Path(evidence_dir).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    config = MiniMaxConfig.from_env()
    system, user = build_prompt(context)
    prompt_sha = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
    (evidence_dir / "prompt.md").write_text(system + "\n\n" + user, encoding="utf-8")
    if not config.api_key:
        blocked = {
            "status": "BLOCKED",
            "reason": "MINIMAX_API_KEY is not set",
            "task_id": context["task"]["id"],
            "context_sha256": context["context_sha256"],
            "model": config.model,
            "endpoint": config.endpoint(),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        (evidence_dir / "BLOCKED.json").write_text(json.dumps(blocked, indent=2), encoding="utf-8")
        raise MiniMaxUnavailable(blocked["reason"])

    record_path = evidence_dir / "dev-record.jsonl"
    last_error: str | None = None
    for attempt in range(1, 3):
        prompt = user if last_error is None else user + "\n\n## Previous patch failed to apply\n\n" + last_error
        started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        result = call_minimax(system, prompt, config)
        content = result["content"]
        (evidence_dir / f"response-{attempt}.txt").write_text(content, encoding="utf-8")
        try:
            patch_text = extract_patch(content)
            files = validate_patch_paths(patch_text)
            application = apply_patch(workspace, patch_text)
        except MiniMaxError as exc:
            last_error = str(exc)
            _append_record(
                record_path,
                {
                    "attempt": attempt,
                    "mode": "minimax",
                    "task_id": context["task"]["id"],
                    "model": result["model"],
                    "endpoint": result["endpoint"],
                    "started_at": started,
                    "latency_ms": result["latency_ms"],
                    "context_sha256": context["context_sha256"],
                    "prompt_sha256": prompt_sha,
                    "usage": result["usage"],
                    "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "patch_sha256": None,
                    "applied": False,
                    "error": last_error,
                },
            )
            continue
        patch_sha = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
        (evidence_dir / "generated.patch").write_text(patch_text, encoding="utf-8")
        record = {
            "attempt": attempt,
            "mode": "minimax",
            "task_id": context["task"]["id"],
            "model": result["model"],
            "endpoint": result["endpoint"],
            "started_at": started,
            "latency_ms": result["latency_ms"],
            "context_sha256": context["context_sha256"],
            "prompt_sha256": prompt_sha,
            "usage": result["usage"],
            "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "patch_sha256": patch_sha,
            "applied": application["applied"],
            "files": files,
            "error": None,
        }
        _append_record(record_path, record)
        return {
            **record,
            "patch_text": patch_text,
            "application": application,
            "prompt": {"system": system, "user": prompt},
        }
    raise MiniMaxError(f"MiniMax did not produce an applicable patch after 2 attempts: {last_error}")


def replay_patch(
    patch_file: str | Path,
    context: dict[str, Any],
    workspace: str | Path,
    evidence_dir: str | Path,
) -> dict[str, Any]:
    evidence_dir = Path(evidence_dir).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    patch_text = Path(patch_file).read_text(encoding="utf-8")
    application = apply_patch(workspace, patch_text)
    record = {
        "attempt": 0,
        "mode": "replay",
        "task_id": context["task"]["id"],
        "model": None,
        "endpoint": None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "latency_ms": 0,
        "context_sha256": context["context_sha256"],
        "prompt_sha256": None,
        "usage": None,
        "response_sha256": None,
        "patch_sha256": hashlib.sha256(patch_text.encode("utf-8")).hexdigest(),
        "applied": application["applied"],
        "files": application["files"],
        "error": None,
        "source_patch": str(Path(patch_file).resolve()),
    }
    _append_record(evidence_dir / "dev-record.jsonl", record)
    return {**record, "patch_text": patch_text, "application": application}


def _append_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
