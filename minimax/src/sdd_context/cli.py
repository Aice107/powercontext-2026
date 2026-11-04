"""Command-line entry point for the SDD context module."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .context import build_context, load_task_file, write_context
from .db import SeekdbUnavailable
from .ingest import ingest_workspace
from .minimax import MiniMaxError, MiniMaxUnavailable, apply_patch, generate_and_apply, replay_patch
from .state import PowerContextError, TaskStateStore
from .testrunner import run_pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = PROJECT_ROOT / ".runtime"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdd-context", description="Spec-driven development context module")
    parser.add_argument("--seekdb-host", default=None, help="seekdb host (default: SEEKDB_HOST or 127.0.0.1)")
    parser.add_argument("--seekdb-port", default=None, help="seekdb port (default: SEEKDB_PORT or 2893)")
    parser.add_argument("--seekdb-db", default=None, help="seekdb database (default: SEEKDB_DATABASE or sdd)")
    parser.add_argument("--query-log", default=None, help="SQL query log path (default: .runtime/db-queries.log)")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="import and index a workspace")
    index.add_argument("--workspace", required=True)
    index.add_argument("--force", action="store_true")

    context = sub.add_parser("context", help="build a source-cited development context")
    context.add_argument("--workspace", required=True)
    context.add_argument("--task-file", required=True)
    context.add_argument("--task-id", default=None)
    context.add_argument("--out", default=None)
    context.add_argument("--md", default=None)
    context.add_argument("--resume", action="store_true", help="load saved state from PowerContext")
    context.add_argument("--max-specs", type=int, default=6)
    context.add_argument("--max-code", type=int, default=8)
    context.add_argument("--max-tests", type=int, default=8)

    state_save = sub.add_parser("state-save", help="save a task state to PowerContext")
    state_save.add_argument("--state-file", required=True)
    state_save.add_argument("--reason", default="sdd_context verification")

    state_load = sub.add_parser("state-load", help="load the latest task state from PowerContext")
    state_load.add_argument("--task-id", required=True)

    status = sub.add_parser("status", help="print saved progress for a task")
    status.add_argument("--task-id", required=True)

    test = sub.add_parser("test", help="run pytest with a reproducible log")
    test.add_argument("--workspace", required=True)
    test.add_argument("--target", action="append", required=True)
    test.add_argument("--log", required=True)
    test.add_argument("--label", required=True)

    minimax = sub.add_parser("minimax", help="generate/apply a MiniMax patch, or replay a recorded one")
    minimax.add_argument("--workspace", required=True)
    minimax.add_argument("--context", required=True)
    minimax.add_argument("--patch-out", default=None)
    minimax.add_argument("--evidence-dir", default=None)
    minimax.add_argument("--patch-file", default=None, help="replay a recorded patch (mode=replay)")

    apply = sub.add_parser("apply-patch", help="apply a unified diff to a workspace")
    apply.add_argument("--workspace", required=True)
    apply.add_argument("--patch", required=True)

    stats = sub.add_parser("db-stats", help="print seekdb table counts")
    version = sub.add_parser("db-version", help="print the seekdb server version")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    host = args.seekdb_host
    port = int(args.seekdb_port) if args.seekdb_port else None
    database = args.seekdb_db
    query_log = Path(args.query_log) if args.query_log else DEFAULT_RUNTIME / "db-queries.log"

    try:
        if args.command == "index":
            return _index(args, host, port, database, query_log)
        if args.command == "context":
            return _context(args, host, port, database, query_log)
        if args.command == "state-save":
            return _state_save(args)
        if args.command == "state-load":
            return _state_load(args)
        if args.command == "status":
            return _status(args)
        if args.command == "test":
            return _test(args)
        if args.command == "minimax":
            return _minimax(args)
        if args.command == "apply-patch":
            return _apply(args)
        if args.command == "db-stats":
            return _db_stats(host, port, database, query_log)
        if args.command == "db-version":
            return _db_version(host, port, database, query_log)
    except (PowerContextError, SeekdbUnavailable, MiniMaxError, MiniMaxUnavailable) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"unknown command {args.command}", file=sys.stderr)
    return 2


def _open_store(host: str | None, port: int | None, database: str | None, query_log: Path):
    from .db import SeekdbStore

    return SeekdbStore(host, port, database, query_log)


def _index(args: argparse.Namespace, host: str | None, port: int | None, database: str | None, query_log: Path) -> int:
    with _open_store(host, port, database, query_log) as store:
        summary = ingest_workspace(store, args.workspace, force=args.force)
        summary["db"] = store.stats()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _context(args: argparse.Namespace, host: str | None, port: int | None, database: str | None, query_log: Path) -> int:
    title, description = load_task_file(args.task_file)
    task_id = args.task_id or Path(args.task_file).stem
    resume_state = None
    if args.resume:
        resume_state = TaskStateStore().load_state(task_id)
    with _open_store(host, port, database, query_log) as store:
        context = build_context(
            store,
            args.workspace,
            task_id=task_id,
            title=title,
            description=description,
            resume_state=resume_state,
            max_specs=args.max_specs,
            max_code=args.max_code,
            max_tests=args.max_tests,
        )
    out = Path(args.out) if args.out else DEFAULT_RUNTIME / "context.json"
    md = Path(args.md) if args.md else out.with_suffix(".md")
    write_context(context, out, md)
    print(
        json.dumps(
            {
                "context": str(out),
                "markdown": str(md),
                "task_id": task_id,
                "context_sha256": context["context_sha256"],
                "specs": [item.get("spec_id") for item in context["specs"]],
                "code": [f"{item['path']}::{item.get('symbol')}" for item in context["code"]],
                "tests": [f"{item['path']}::{item.get('symbol')}" for item in context["tests"]],
                "warnings": context["warnings"],
                "resumed": bool(resume_state),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _state_save(args: argparse.Namespace) -> int:
    state = json.loads(Path(args.state_file).read_text(encoding="utf-8"))
    if "saved_at" not in state:
        import time

        state["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    result = TaskStateStore().save_state(state, reason=args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _state_load(args: argparse.Namespace) -> int:
    state = TaskStateStore().load_state(args.task_id)
    if state is None:
        print(json.dumps({"found": False, "task_id": args.task_id}, ensure_ascii=False))
        return 1
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def _status(args: argparse.Namespace) -> int:
    state = TaskStateStore().load_state(args.task_id)
    if state is None:
        print(f"no saved state for task {args.task_id}", file=sys.stderr)
        return 1
    print(f"task: {state.get('task_id')}")
    print(f"status: {state.get('status')}")
    print(f"saved_at: {state.get('saved_at')}")
    print("done:")
    for item in state.get("done", []):
        print(f"  - {item}")
    print("todo:")
    for item in state.get("todo", []):
        print(f"  - {item}")
    print("verifications:")
    for item in state.get("verifications", []):
        if isinstance(item, dict):
            print(f"  - {item.get('name')}: exit={item.get('exit_code')} {item.get('summary', '')}")
        else:
            print(f"  - {item}")
    print(f"next_step: {state.get('next_step')}")
    return 0


def _test(args: argparse.Namespace) -> int:
    result = run_pytest(args.workspace, args.target, args.log, label=args.label)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _minimax(args: argparse.Namespace) -> int:
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else DEFAULT_RUNTIME / "minimax"
    if args.patch_file:
        result = replay_patch(args.patch_file, context, args.workspace, evidence_dir)
    else:
        result = generate_and_apply(context, args.workspace, evidence_dir)
    if args.patch_out:
        Path(args.patch_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.patch_out).write_text(result["patch_text"], encoding="utf-8")
    printable = {key: value for key, value in result.items() if key not in {"patch_text", "prompt", "application"}}
    printable["files"] = result["application"]["files"]
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


def _apply(args: argparse.Namespace) -> int:
    patch_text = Path(args.patch).read_text(encoding="utf-8")
    result = apply_patch(args.workspace, patch_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _db_stats(host: str | None, port: int | None, database: str | None, query_log: Path) -> int:
    with _open_store(host, port, database, query_log) as store:
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    return 0


def _db_version(host: str | None, port: int | None, database: str | None, query_log: Path) -> int:
    with _open_store(host, port, database, query_log) as store:
        print(json.dumps({"version": store.version(), "database": store.database}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
