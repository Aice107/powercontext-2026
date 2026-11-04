"""MiniMax code-edit loop: prompt, call, extract, apply, record."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
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
    group_id: str | None = None

    @classmethod
    def from_env(cls) -> "MiniMaxConfig":
        return cls(
            api_key=os.environ.get("MINIMAX_API_KEY") or None,
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/"),
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M3"),
            style=os.environ.get("MINIMAX_API_STYLE", "openai").lower(),
            timeout=float(os.environ.get("MINIMAX_TIMEOUT", "120")),
            group_id=os.environ.get("MINIMAX_GROUP_ID") or None,
        )

    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions") or self.base_url.endswith("/text/chatcompletion_v2"):
            url = self.base_url
        elif self.style == "native":
            url = self.base_url + "/text/chatcompletion_v2"
        else:
            url = self.base_url + "/chat/completions"
        if self.style == "native" and self.group_id and "GroupId=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}GroupId={self.group_id}"
        return url


def build_prompt(context: dict[str, Any], workspace: str | Path | None = None) -> tuple[str, str]:
    task = context["task"]
    parts = [
        f"# Task: {task['title']}",
        "",
        task["description"].strip(),
        "",
        "## Source-cited development context",
        "",
        render_markdown(context),
        "",
    ]
    full_files = _full_files(context, workspace)
    if full_files:
        parts.extend(
            [
                "## Full files (authoritative)",
                "",
                "Use these exact file contents for imports, line numbers and hunk context.",
                "Do not guess an import block that is not present here.",
                "",
                full_files,
                "",
            ]
        )
    parts.extend(
        [
            "## Output contract",
            "",
            "Return only the unified diff fenced with ```diff. Do not include a <think> block,",
            "prose, or a draft diff before the final answer.",
            "The change must make the target tests in `tests/test_due_before.py` pass while keeping",
            "`tests/test_tasks_regression.py` green. Do not touch tests or specifications.",
        ]
    )
    return SYSTEM_PROMPT, "\n".join(parts)


def _full_files(context: dict[str, Any], workspace: str | Path | None, max_chars: int = 60000) -> str:
    if not workspace:
        return ""
    workspace = Path(workspace).resolve()
    seen: set[str] = set()
    blocks: list[str] = []
    total = 0
    for item in context.get("code", []):
        rel = item.get("path")
        if not rel or rel in seen:
            continue
        path = workspace / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if total + len(text) > max_chars:
            continue
        seen.add(rel)
        total += len(text)
        blocks.append(f"### {rel}\n\n```python\n{text.rstrip()}\n```\n")
    return "\n".join(blocks)


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
        "max_tokens": int(os.environ.get("MINIMAX_MAX_TOKENS", "8192")),
        "stream": False,
    }
    request = urllib.request.Request(
        config.endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
        method="POST",
    )
    started = time.perf_counter()
    body: str | None = None
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            raise MiniMaxError(f"MiniMax HTTP {exc.code}: {detail}") from exc
        except (http.client.IncompleteRead, urllib.error.URLError, ConnectionError) as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(3 * attempt)
                continue
            raise MiniMaxError(f"MiniMax transport error after {attempt} attempts: {exc}") from exc
    if body is None:
        raise MiniMaxError(f"MiniMax returned no body: {last_error}")
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise MiniMaxError(f"MiniMax returned non-JSON: {body[:500]}") from exc
    if data.get("base_resp", {}).get("status_code") not in (None, 0):
        raise MiniMaxError(f"MiniMax base_resp error: {data.get('base_resp')}")
    content: str | None = None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        # The native v2 endpoint has historically returned ``reply``.
        reply = data.get("reply")
        if isinstance(reply, str):
            content = reply
    if not isinstance(content, str) or not content.strip():
        raise MiniMaxError(f"MiniMax response has no usable completion: {body[:800]}")
    return {
        "content": content,
        "usage": data.get("usage") or {},
        "latency_ms": latency_ms,
        "model": data.get("model") or config.model,
        "endpoint": config.endpoint(),
        "raw_id": data.get("id"),
    }


def extract_patch(content: str) -> str:
    # Reasoning models may put a draft diff inside <think> blocks.  Remove those
    # before looking for the final fenced answer.
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
    matches = re.findall(r"```(?:diff|patch)\s*\n(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if matches:
        patch = matches[-1]
    else:
        lines = cleaned.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.startswith("diff --git ") or line.startswith("--- a/"):
                start = index
        if start is None:
            raise MiniMaxError("response did not contain a unified diff")
        patch = "\n".join(lines[start:])
    return normalize_patch(patch.strip() + "\n")


def normalize_patch(patch_text: str) -> str:
    """Repair LLM hunk headers whose old/new line counts are wrong."""

    lines = patch_text.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$", lines[index])
        if not match:
            out.append(lines[index])
            index += 1
            continue
        old_start, _old_count, new_start, _new_count, tail = match.groups()
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if line.startswith("@@ ") or line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("+++ "):
                break
            body.append(line)
            cursor += 1
        old_count = sum(1 for line in body if line.startswith(" ") or line.startswith("-"))
        new_count = sum(1 for line in body if line.startswith(" ") or line.startswith("+"))
        out.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{tail}")
        out.extend(body)
        index = cursor
    return "\n".join(out) + "\n"


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



def _parse_unified_hunks(patch_text: str) -> dict[str, list[tuple[list[str], list[str]]]]:
    """Parse a unified diff into path -> [(before_lines, after_lines)].

    Line numbers are deliberately ignored: LLM diffs frequently have a correct
    body but an off-by-N hunk header.  The applier below matches the body.
    """

    lines = patch_text.splitlines()
    files: dict[str, list[tuple[list[str], list[str]]]] = {}
    current: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            parts = line.split()
            candidate = parts[-1] if parts else ""
            if candidate.startswith("b/"):
                candidate = candidate[2:]
            current = candidate or None
            index += 1
            continue
        if line.startswith("--- "):
            candidate = line[4:].split("\t", 1)[0].strip()
            if candidate.startswith("a/"):
                candidate = candidate[2:]
            if candidate and candidate != "/dev/null":
                current = candidate
            index += 1
            continue
        if line.startswith("+++ "):
            candidate = line[4:].split("\t", 1)[0].strip()
            if candidate.startswith("b/"):
                candidate = candidate[2:]
            if candidate and candidate != "/dev/null":
                current = candidate
            index += 1
            continue
        if line.startswith("@@ "):
            before: list[str] = []
            after: list[str] = []
            index += 1
            while index < len(lines):
                body_line = lines[index]
                if (
                    body_line.startswith("@@ ")
                    or body_line.startswith("diff --git ")
                    or body_line.startswith("--- ")
                    or body_line.startswith("+++ ")
                ):
                    break
                if body_line.startswith("\\"):
                    index += 1
                    continue
                if body_line.startswith(" "):
                    before.append(body_line[1:])
                    after.append(body_line[1:])
                elif body_line.startswith("-"):
                    before.append(body_line[1:])
                elif body_line.startswith("+"):
                    after.append(body_line[1:])
                elif body_line == "":
                    before.append("")
                    after.append("")
                index += 1
            if current:
                files.setdefault(current, []).append((before, after))
            continue
        index += 1
    return files


def _apply_hunks_to_lines(lines: list[str], hunks: list[tuple[list[str], list[str]]]) -> list[str]:
    for before, after in hunks:
        if before == after:
            continue
        if not before:
            raise MiniMaxError("cannot apply a hunk with no context or removed lines")
        if before not in lines and after in lines:
            continue  # already applied
        position = _find_subsequence(lines, before)
        if position is None:
            raise MiniMaxError("hunk context not found in the target file")
        lines[position : position + len(before)] = after
    return lines


def _find_subsequence(lines: list[str], needle: list[str]) -> int | None:
    if len(needle) > len(lines):
        return None
    for start in range(len(lines) - len(needle) + 1):
        if lines[start : start + len(needle)] == needle:
            return start
    return None


def _apply_unified_python(workspace: Path, patch_text: str) -> dict[str, Any] | None:
    files = _parse_unified_hunks(patch_text)
    if not files:
        return None
    originals: dict[str, list[str]] = {}
    for rel, hunks in files.items():
        path = workspace / rel
        if not path.is_file():
            raise MiniMaxError(f"patch target does not exist: {rel}")
        raw = path.read_text(encoding="utf-8")
        originals[rel] = raw.splitlines()
    updated: dict[str, str] = {}
    for rel, hunks in files.items():
        lines = list(originals[rel])
        lines = _apply_hunks_to_lines(lines, hunks)
        if lines == originals[rel]:
            raise MiniMaxError(f"patch produced no change for {rel}")
        updated[rel] = "\n".join(lines) + ("\n" if originals[rel] and originals[rel][-1] != "" else "")
    for rel, content in updated.items():
        (workspace / rel).write_text(content, encoding="utf-8")
    return {"applied": True, "files": sorted(files), "check_stdout": "python-context-applier", "apply_stdout": "python-context-applier"}


def apply_patch(workspace: str | Path, patch_text: str) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    files = validate_patch_paths(patch_text)
    try:
        python_result = _apply_unified_python(workspace, patch_text)
        if python_result is not None:
            return python_result
    except MiniMaxError:
        # Fall through to GNU patch, which may understand formats the
        # context applier does not; the dry-run keeps it atomic.
        pass
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as handle:
        handle.write(patch_text)
        patch_path = Path(handle.name)
    try:
        # GNU patch is the primary applier: git apply silently ignores paths
        # that resolve outside the current directory when the workspace is
        # nested inside another Git repository.
        check = _run(["patch", "-p1", "--batch", "--fuzz=3", "--dry-run", "-i", str(patch_path)], workspace)
        if check["exit_code"] != 0:
            check = _run(["git", "apply", "--check", str(patch_path)], workspace)
        if check["exit_code"] != 0:
            raise MiniMaxError(f"patch does not apply: {check['stderr'] or check['stdout']}")
        applied = _run(["patch", "-p1", "--batch", "--fuzz=3", "-i", str(patch_path)], workspace)
        if applied["exit_code"] != 0:
            applied = _run(["git", "apply", str(patch_path)], workspace)
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
    system, user = build_prompt(context, workspace)
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
        try:
            result = call_minimax(system, prompt, config)
        except MiniMaxError as first_error:
            if config.style != "openai":
                raise
            # Some deployments only expose the native v2 path.  Try it once
            # before giving up, while keeping the original error in the log.
            native_config = replace(config, style="native")
            try:
                result = call_minimax(system, prompt, native_config)
            except MiniMaxError as native_error:
                raise MiniMaxError(
                    f"OpenAI-compatible call failed ({first_error}); native fallback also failed ({native_error})"
                ) from native_error
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
