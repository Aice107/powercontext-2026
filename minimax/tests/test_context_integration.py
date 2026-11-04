import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sdd_context.context import build_context, load_task_file
from sdd_context.db import SeekdbStore, SeekdbUnavailable
from sdd_context.ingest import ingest_workspace
from sdd_context.state import PowerContextError, TaskStateStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path):
    database = f"sdd_test_{os.getpid()}"
    try:
        handle = SeekdbStore(
            host="127.0.0.1",
            port=int(os.environ.get("SEEKDB_PORT", "2893")),
            database=database,
            query_log=tmp_path / "queries.log",
        )
    except SeekdbUnavailable as exc:
        pytest.skip(f"seekdb server not available: {exc}")
    try:
        yield handle
    finally:
        try:
            handle.execute("USE test")
            handle.execute(f"DROP DATABASE IF EXISTS {database}")
        finally:
            handle.close()


def _context(store, workspace):
    title, description = load_task_file(ROOT / "validation" / "task.md")
    return build_context(
        store,
        workspace,
        task_id="taskhub-due-before",
        title=title,
        description=description,
    )


def test_context_contains_required_real_sources(store):
    ingest_workspace(store, ROOT / "demo" / "business")
    context = _context(store, ROOT / "demo" / "business")
    spec_ids = {item.get("spec_id") for item in context["specs"]}
    code = {f"{item['path']}::{item.get('symbol')}" for item in context["code"]}
    tests = {f"{item['path']}::{item.get('symbol')}" for item in context["tests"]}
    assert "SPEC-API-013" in spec_ids
    assert "app/store.py::list_tasks" in code
    assert "tests/test_due_before.py::test_due_before_includes_boundary_day" in tests
    assert context["context_sha256"]
    for item in context["required_sources"]:
        assert item["path"]
        assert item["sha256"]


def test_spec_update_is_visible_after_reimport(store, tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "demo" / "baseline", workspace)
    ingest_workspace(store, workspace)
    before = _context(store, workspace)
    assert "SPEC-API-013" not in {item.get("spec_id") for item in before["specs"]}

    subprocess.run(
        ["patch", "-p1", "-i", str(ROOT / "patches" / "0002-spec-due-before.patch")],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = ingest_workspace(store, workspace)
    assert summary["indexed"] == 1
    after = _context(store, workspace)
    assert "SPEC-API-013" in {item.get("spec_id") for item in after["specs"]}
    spec = next(item for item in after["specs"] if item.get("spec_id") == "SPEC-API-013")
    assert "包含截止当天" in spec["text"]


def test_powercontext_state_roundtrip():
    state_store = TaskStateStore(scope_key=f"sdd-test-{os.getpid()}")
    try:
        if not state_store.health():
            pytest.skip("PowerContext server not available")
        state = {
            "schema": "sdd-task-state/v1",
            "task_id": "test-state-roundtrip",
            "status": "implemented",
            "done": ["a", "b"],
            "todo": ["c"],
            "verifications": [{"name": "target", "exit_code": 0, "summary": "5 passed"}],
            "next_step": "done",
            "saved_at": "2026-11-04T00:00:00+00:00",
            "saved_at_ns": 1,
        }
        saved = state_store.save_state(state, reason="unit test")
        assert saved["artifact_id"]
        loaded = state_store.load_state("test-state-roundtrip")
        assert loaded is not None
        assert loaded["done"] == ["a", "b"]
        assert loaded["verifications"] == state["verifications"]
    except PowerContextError as exc:
        pytest.skip(f"PowerContext server not available: {exc}")
