"""Parse specifications, Python code and tests into searchable chunks."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .db import SeekdbStore
from .tokenizer import index_terms

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".runtime", ".pytest_cache",
    "node_modules", "evidence", "dist", "build", ".mypy_cache", ".ruff_cache",
}

SPEC_HEADING_RE = re.compile(r"^(#{2,4})\s+(.*)$")
SPEC_ID_RE = re.compile(r"\b(SPEC-[A-Z]+-\d+)\b")


@dataclass
class Chunk:
    kind: str
    path: str
    start_line: int
    end_line: int
    text: str
    symbol: str | None = None
    spec_id: str | None = None
    title: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        key = f"{self.path}|{self.start_line}|{self.end_line}|{self.spec_id or self.symbol or ''}"
        return "chk_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    @property
    def token_count(self) -> int:
        return len(index_terms(self.text))


@dataclass
class ParsedSource:
    path: str
    kind: str
    title: str
    sha256: str
    chunks: list[Chunk]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_id(path: str) -> str:
    return "src_" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def discover(workspace: str | Path) -> list[tuple[Path, str]]:
    workspace = Path(workspace).resolve()
    found: list[tuple[Path, str]] = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("."))
        for name in sorted(files):
            path = Path(root) / name
            rel = path.relative_to(workspace).as_posix()
            if rel.startswith("specs/") and path.suffix == ".md":
                found.append((path, "spec"))
            elif rel.startswith("app/") and path.suffix == ".py":
                found.append((path, "code"))
            elif rel.startswith("tests/") and path.suffix == ".py":
                found.append((path, "test"))
            elif rel == "README.md":
                found.append((path, "doc"))
    return found


def parse_source(workspace: Path, path: Path, kind: str) -> ParsedSource:
    rel = path.relative_to(workspace).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    if kind == "spec":
        chunks = parse_spec(text, rel)
        title = _first_heading(text) or rel
    elif kind == "code":
        chunks = parse_code(text, rel)
        title = rel
    elif kind == "test":
        chunks = parse_test(text, rel)
        title = rel
    else:
        chunks = parse_doc(text, rel)
        title = _first_heading(text) or rel
    return ParsedSource(path=rel, kind=kind, title=title, sha256=sha256_text(text), chunks=chunks)


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.*)$", line)
        if match:
            return match.group(1).strip()
    return None


def _mk_chunk(
    kind: str,
    path: str,
    lines: list[str],
    start: int,
    end: int,
    *,
    symbol: str | None = None,
    spec_id: str | None = None,
    title: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Chunk:
    body = "\n".join(lines[start - 1 : end]).strip("\n")
    return Chunk(
        kind=kind,
        path=path,
        start_line=start,
        end_line=end,
        text=body,
        symbol=symbol,
        spec_id=spec_id,
        title=title,
        meta=meta or {},
    )


def parse_spec(text: str, path: str) -> list[Chunk]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    index = 0
    while index < len(lines):
        heading = SPEC_HEADING_RE.match(lines[index])
        if heading and SPEC_ID_RE.search(heading.group(2)):
            level = len(heading.group(1))
            end = index + 1
            while end < len(lines):
                nxt = SPEC_HEADING_RE.match(lines[end])
                if nxt and len(nxt.group(1)) <= level:
                    break
                end += 1
            title = heading.group(2).strip()
            spec_id = SPEC_ID_RE.search(title)
            assert spec_id is not None
            chunks.append(
                _mk_chunk(
                    "spec",
                    path,
                    lines,
                    index + 1,
                    end,
                    spec_id=spec_id.group(1),
                    title=title,
                    meta={"heading_level": level, "version": _spec_version(text)},
                )
            )
            index = end
        else:
            index += 1
    if not chunks and text.strip():
        chunks.append(_mk_chunk("doc", path, lines, 1, max(1, len(lines)), title=_first_heading(text)))
    return chunks


def _spec_version(text: str) -> str | None:
    match = re.search(r"规格版本[:：]\s*([^\s（(]+)", text)
    return match.group(1) if match else None


def parse_code(text: str, path: str) -> list[Chunk]:
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [_mk_chunk("code", path, lines, 1, max(1, len(lines)), symbol="<syntax-error>")]
    chunks: list[Chunk] = []

    top_nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    first_top = min((getattr(node, "lineno", 1) for node in top_nodes), default=len(lines) + 1)
    if first_top > 1:
        module_end = first_top - 1
        if "\n".join(lines[:module_end]).strip():
            chunks.append(
                _mk_chunk(
                    "code", path, lines, 1, module_end, symbol="<module>",
                    meta={"imports": _imports(tree)},
                )
            )

    def start_of(node: ast.AST) -> int:
        start = getattr(node, "lineno", 1)
        for decorator in getattr(node, "decorator_list", []) or []:
            start = min(start, decorator.lineno)
        return start

    def end_of(node: ast.AST) -> int:
        return int(getattr(node, "end_lineno", getattr(node, "lineno", 1)) or 1)

    def add_function(node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> None:
        chunks.append(
            _mk_chunk(
                "code", path, lines, start_of(node), end_of(node), symbol=qualname,
                title=node.name,
                meta={
                    "args": [arg.arg for arg in node.args.args],
                    "decorators": [_expr_text(d) for d in node.decorator_list],
                    "docstring": ast.get_docstring(node) or "",
                    "returns": _expr_text(node.returns) if node.returns else None,
                },
            )
        )

    def walk_body(body: Iterable[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                qualname = f"{prefix}{node.name}"
                method_starts = [
                    start_of(child)
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                header_end = (min(method_starts) - 1) if method_starts else end_of(node)
                if header_end >= start_of(node):
                    chunks.append(
                        _mk_chunk(
                            "code", path, lines, start_of(node), header_end, symbol=qualname,
                            title=node.name,
                            meta={"decorators": [_expr_text(d) for d in node.decorator_list]},
                        )
                    )
                walk_body(node.body, qualname + ".")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_function(node, f"{prefix}{node.name}")

    walk_body(tree.body, "")
    if not chunks and text.strip():
        chunks.append(_mk_chunk("code", path, lines, 1, max(1, len(lines)), symbol="<module>"))
    return chunks


def _expr_text(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive for exotic nodes
        return type(node).__name__


def _imports(tree: ast.Module) -> list[str]:
    result: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.append(f"{node.module or ''}:{','.join(alias.name for alias in node.names)}")
    return result


def parse_test(text: str, path: str) -> list[Chunk]:
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [_mk_chunk("test", path, lines, 1, max(1, len(lines)), symbol="<syntax-error>")]
    chunks: list[Chunk] = []

    def start_of(node: ast.AST) -> int:
        start = getattr(node, "lineno", 1)
        for decorator in getattr(node, "decorator_list", []) or []:
            start = min(start, decorator.lineno)
        return start

    def walk_body(body: Iterable[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                walk_body(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{node.name}"
                if node.name.startswith("test_"):
                    chunks.append(
                        _mk_chunk(
                            "test", path, lines, start_of(node), int(node.end_lineno or node.lineno),
                            symbol=qualname, title=node.name,
                            meta={"assertions": _assertions(node), "docstring": ast.get_docstring(node) or ""},
                        )
                    )

    walk_body(tree.body, "")
    if not chunks and text.strip():
        # conftest.py and helper modules keep a file-level chunk.
        chunks.append(
            _mk_chunk("test", path, lines, 1, max(1, len(lines)), symbol="<file>", title=Path(path).name)
        )
    return chunks


def _assertions(node: ast.AST) -> list[str]:
    result: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            result.append("assert " + _expr_text(child.test)[:180])
        elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "raises":
            result.append("pytest.raises(" + _expr_text(child.args[0] if child.args else None) + ")")
        if len(result) >= 12:
            break
    return result


def parse_doc(text: str, path: str) -> list[Chunk]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    start = 1
    buffer: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.strip():
            buffer.append(line)
        elif buffer:
            chunks.append(_mk_chunk("doc", path, lines, start, index - 1, title=path))
            buffer = []
            start = index + 1
    if buffer:
        chunks.append(_mk_chunk("doc", path, lines, start, len(lines), title=path))
    return chunks


def ingest_workspace(store: SeekdbStore, workspace: str | Path, force: bool = False) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    started = time.perf_counter()
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = {
        "workspace": str(workspace),
        "files": 0,
        "indexed": 0,
        "skipped": 0,
        "chunks": 0,
        "terms": 0,
        "elapsed_ms": 0,
        "sources": [],
    }
    for path, kind in discover(workspace):
        summary["files"] += 1
        parsed = parse_source(workspace, path, kind)
        existing = store.get_source(parsed.path)
        if existing and existing["sha256"] == parsed.sha256 and not force:
            summary["skipped"] += 1
            continue
        if existing:
            store.delete_source(parsed.path)
        sid = source_id(parsed.path)
        store.execute(
            """
            INSERT INTO sources (source_id, kind, path, title, sha256, imported_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (sid, parsed.kind, parsed.path, parsed.title, parsed.sha256, now),
        )
        chunk_rows: list[tuple[Any, ...]] = []
        term_rows: list[tuple[Any, ...]] = []
        for ordinal, chunk in enumerate(parsed.chunks):
            chunk_rows.append(
                (
                    chunk.chunk_id,
                    sid,
                    ordinal,
                    chunk.kind,
                    chunk.path,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.text,
                    chunk.symbol,
                    chunk.spec_id,
                    chunk.title,
                    chunk.token_count,
                    json.dumps(chunk.meta, ensure_ascii=False),
                )
            )
            counts = Counter(index_terms(chunk.text))
            term_rows.extend((term, chunk.chunk_id, tf) for term, tf in counts.items())
        if chunk_rows:
            store.executemany(
                """
                INSERT INTO chunks
                  (chunk_id, source_id, ordinal, kind, path, start_line, end_line,
                   text, symbol, spec_id, title, token_count, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                chunk_rows,
            )
        if term_rows:
            store.executemany("INSERT INTO terms (term, chunk_id, tf) VALUES (%s, %s, %s)", term_rows)
        store.execute(
            "INSERT INTO import_events (path, sha256, action, imported_at) VALUES (%s, %s, %s, %s)",
            (parsed.path, parsed.sha256, "reindex" if existing else "insert", now),
        )
        summary["indexed"] += 1
        summary["chunks"] += len(chunk_rows)
        summary["terms"] += len(term_rows)
        summary["sources"].append(
            {
                "path": parsed.path,
                "kind": parsed.kind,
                "sha256": parsed.sha256,
                "chunks": len(chunk_rows),
            }
        )
    summary["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return summary
