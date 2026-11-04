"""Assemble a source-cited development context from retrieval results."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .db import SeekdbStore
from .retrieval import SearchHit, search, select_categories

SCHEMA = "sdd-context/v1"


def build_context(
    store: SeekdbStore,
    workspace: str | Path,
    *,
    task_id: str,
    title: str,
    description: str,
    resume_state: dict[str, Any] | None = None,
    max_specs: int = 6,
    max_code: int = 8,
    max_tests: int = 8,
) -> dict[str, Any]:
    query = f"{title}\n{description}"
    hits, terms = search(store, query)
    categories, warnings = select_categories(
        hits, max_specs=max_specs, max_code=max_code, max_tests=max_tests
    )
    specs = [hit.to_context_entry() for hit in categories["spec"]]
    code = [hit.to_context_entry() for hit in categories["code"]]
    tests = [hit.to_context_entry() for hit in categories["test"]]
    sources = _collect_sources(categories)
    context: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "task": {
            "id": task_id,
            "title": title,
            "description": description,
            "workspace": str(Path(workspace).resolve()),
        },
        "query_terms": terms,
        "specs": specs,
        "code": code,
        "tests": tests,
        "progress": _progress_payload(resume_state),
        "sources": sources,
        "required_sources": _required_sources(categories),
        "warnings": warnings,
    }
    context["context_sha256"] = _context_hash(context)
    return context


def _progress_payload(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"done": [], "todo": [], "verifications": [], "resumed_from_powercontext": False}
    return {
        "task_id": state.get("task_id"),
        "status": state.get("status"),
        "done": state.get("done", []),
        "todo": state.get("todo", []),
        "verifications": state.get("verifications", []),
        "next_step": state.get("next_step"),
        "saved_at": state.get("saved_at"),
        "resumed_from_powercontext": True,
    }


def _collect_sources(categories: dict[str, list[SearchHit]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for kind in ("spec", "code", "test"):
        for hit in categories[kind]:
            if hit.path in seen:
                continue
            seen.add(hit.path)
            result.append({"kind": kind, "path": hit.path, "sha256": hit.sha256})
    return result


def _required_sources(categories: dict[str, list[SearchHit]]) -> list[dict[str, Any]]:
    required: list[dict[str, Any]] = []
    for hit in categories["spec"]:
        item = {"kind": "spec", "path": hit.path, "start_line": hit.start_line, "sha256": hit.sha256}
        if hit.spec_id:
            item["spec_id"] = hit.spec_id
        required.append(item)
    for kind in ("code", "test"):
        for hit in categories[kind]:
            item = {
                "kind": kind,
                "path": hit.path,
                "start_line": hit.start_line,
                "sha256": hit.sha256,
            }
            if hit.symbol:
                item["symbol"] = hit.symbol
            required.append(item)
    return required


def _context_hash(context: dict[str, Any]) -> str:
    payload = {
        "task": context["task"],
        "specs": context["specs"],
        "code": context["code"],
        "tests": context["tests"],
        "progress": context["progress"],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_markdown(context: dict[str, Any]) -> str:
    task = context["task"]
    lines: list[str] = [
        "# SDD development context",
        "",
        f"- Task ID: `{task['id']}`",
        f"- Workspace: `{task['workspace']}`",
        f"- Context SHA-256: `{context['context_sha256']}`",
        f"- Generated at: {context['generated_at']}",
        "",
        "## Task",
        "",
        f"### {task['title']}",
        "",
        task["description"].strip(),
        "",
        "## 1. Applicable specifications",
        "",
    ]
    if not context["specs"]:
        lines.append("_No specification chunk matched._")
    for item in context["specs"]:
        lines.extend(_entry_header(item, item.get("spec_id", item.get("title", "spec"))))
        lines.extend(["```text", item["text"].rstrip(), "```", ""])
    lines.extend(["## 2. Code to change", ""])
    if not context["code"]:
        lines.append("_No code chunk matched._")
    for item in context["code"]:
        lines.extend(_entry_header(item, item.get("symbol", item["path"])))
        lines.extend(["```python", item["text"].rstrip(), "```", ""])
    lines.extend(["## 3. Tests for functional and compatibility verification", ""])
    if not context["tests"]:
        lines.append("_No test chunk matched._")
    for item in context["tests"]:
        lines.extend(_entry_header(item, item.get("symbol", item["path"])))
        lines.extend(["```python", item["text"].rstrip(), "```", ""])
    progress = context.get("progress", {})
    lines.extend(["## 4. Current progress", ""])
    if progress.get("resumed_from_powercontext"):
        lines.extend(
            [
                f"- Resumed from PowerContext: `{progress.get('saved_at')}`",
                f"- Status: `{progress.get('status')}`",
                f"- Done: {_inline(progress.get('done'))}",
                f"- Todo: {_inline(progress.get('todo'))}",
                f"- Verifications: {_inline(progress.get('verifications'))}",
                f"- Next step: {progress.get('next_step') or '-'}",
            ]
        )
    else:
        lines.append("- No saved state loaded (fresh context).")
    if context.get("warnings"):
        lines.extend(["", "## Warnings", "", *[f"- {warning}" for warning in context["warnings"]]])
    lines.append("")
    return "\n".join(lines)


def _entry_header(item: dict[str, Any], label: str) -> list[str]:
    return [
        f"### {label}",
        "",
        f"Source: `{item['path']}:{item['start_line']}-{item['end_line']}` "
        f"(sha256 `{item['sha256'][:12]}`, score {item['score']:.3f})",
        "",
    ]


def _inline(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, list):
        rendered = []
        for item in value:
            if isinstance(item, dict):
                rendered.append(
                    f"{item.get('name', item.get('command', 'item'))}: exit={item.get('exit_code')} "
                    f"({item.get('summary', '')})"
                )
            else:
                rendered.append(str(item))
        return "; ".join(rendered)
    return str(value)


def write_context(context: dict[str, Any], json_path: str | Path, markdown_path: str | Path | None = None) -> None:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path = Path(markdown_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(context), encoding="utf-8")


def load_task_file(path: str | Path) -> tuple[str, str]:
    """Read a task markdown file.

    The first level-1 heading is the title; the remaining text is the description.
    """

    text = Path(path).read_text(encoding="utf-8")
    title = Path(path).stem
    body = text.strip()
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            body = text.replace(line, "", 1).strip()
            break
    return title, body
