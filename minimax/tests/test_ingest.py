from pathlib import Path

from sdd_context.ingest import parse_source

ROOT = Path(__file__).resolve().parents[1]


def test_spec_v2_has_due_before_clause_and_line_range():
    parsed = parse_source(ROOT / "demo" / "business", ROOT / "demo" / "business" / "specs" / "task-api.md", "spec")
    spec_ids = {chunk.spec_id for chunk in parsed.chunks}
    assert "SPEC-API-013" in spec_ids
    clause = next(chunk for chunk in parsed.chunks if chunk.spec_id == "SPEC-API-013")
    assert "包含截止当天" in clause.text
    assert clause.start_line < clause.end_line
    assert clause.path == "specs/task-api.md"


def test_spec_v1_has_no_due_before_clause():
    parsed = parse_source(ROOT / "demo" / "baseline", ROOT / "demo" / "baseline" / "specs" / "task-api.md", "spec")
    assert "SPEC-API-013" not in {chunk.spec_id for chunk in parsed.chunks}


def test_code_chunk_contains_list_tasks_symbol():
    parsed = parse_source(ROOT / "demo" / "business", ROOT / "demo" / "business" / "app" / "store.py", "code")
    symbols = {chunk.symbol for chunk in parsed.chunks}
    assert "list_tasks" in symbols
    chunk = next(chunk for chunk in parsed.chunks if chunk.symbol == "list_tasks")
    assert "due_before" in chunk.text


def test_test_chunks_are_extracted_with_assertions():
    parsed = parse_source(
        ROOT / "demo" / "business",
        ROOT / "demo" / "business" / "tests" / "test_due_before.py",
        "test",
    )
    symbols = {chunk.symbol for chunk in parsed.chunks}
    assert "test_due_before_includes_boundary_day" in symbols
    chunk = next(chunk for chunk in parsed.chunks if chunk.symbol == "test_due_before_includes_boundary_day")
    assert chunk.kind == "test"
    assert chunk.meta.get("assertions")
