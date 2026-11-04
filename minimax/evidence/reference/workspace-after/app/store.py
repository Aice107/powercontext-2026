"""SQLite persistence and query building for TaskHub."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import (
    NotFoundError,
    parse_date,
    parse_optional_text,
    parse_priority,
    parse_status,
    require_title,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL,
    priority    TEXT NOT NULL,
    assignee    TEXT,
    due_date    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
"""

SEED_TASKS = [
    ("Fix login redirect", "Redirect loops after SSO login", "todo", "high", "alice", "2026-01-30"),
    ("Add audit log", "Record who changed each task", "todo", "medium", "bob", "2026-01-31"),
    ("Update docs", "Document the filter parameters", "done", "low", "alice", "2026-02-01"),
    ("Tune query", "Reduce the list endpoint latency", "in_progress", "high", "carol", "2026-01-15"),
    ("Refactor store", "Split the store into smaller modules", "todo", "medium", "alice", None),
    ("Add metrics", "Expose request counters", "in_progress", "low", "bob", "2026-02-10"),
    ("Upgrade Flask", "Move to the current Flask release", "done", "medium", "carol", "2026-01-31"),
    ("Fix timezone", "Render due dates in the user zone", "todo", "high", "alice", "2026-03-01"),
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def seed_tasks(db_path: str | Path) -> int:
    """Insert the deterministic demo rows once. Returns the number inserted."""

    init_db(db_path)
    now = _now()
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count:
            return 0
        conn.executemany(
            """
            INSERT INTO tasks
                (title, description, status, priority, assignee, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, now, now) for row in SEED_TASKS],
        )
        return len(SEED_TASKS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["id"] = int(data["id"])
    return data


def list_tasks(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    due_before: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if priority is not None:
        where.append("priority = ?")
        params.append(priority)
    if assignee is not None:
        where.append("assignee = ?")
        params.append(assignee)
    if due_before is not None:
        where.append("due_date IS NOT NULL AND due_date <= ?")
        params.append(due_before)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM tasks{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM tasks{clause} ORDER BY id ASC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "items": [_row(row) for row in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def get_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"task {task_id} not found", "id")
    return _row(row)


def create_task(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    title = require_title(payload)
    description = parse_optional_text(payload.get("description"), "description", 2000) or ""
    status = parse_status(payload.get("status", "todo"))
    priority = parse_priority(payload.get("priority", "medium"))
    assignee = parse_optional_text(payload.get("assignee"), "assignee")
    due_date = parse_date(payload.get("due_date"), "due_date")
    now = _now()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks
                (title, description, status, priority, assignee, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, status, priority, assignee, due_date, now, now),
        )
        task_id = int(cursor.lastrowid)
    return get_task(conn, task_id)


def update_task(conn: sqlite3.Connection, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_task(conn, task_id)
    title = require_title(payload) if "title" in payload else current["title"]
    description = (
        parse_optional_text(payload.get("description"), "description", 2000) or ""
        if "description" in payload
        else current["description"]
    )
    status = parse_status(payload["status"]) if "status" in payload else current["status"]
    priority = parse_priority(payload["priority"]) if "priority" in payload else current["priority"]
    assignee = (
        parse_optional_text(payload.get("assignee"), "assignee")
        if "assignee" in payload
        else current["assignee"]
    )
    due_date = parse_date(payload.get("due_date"), "due_date") if "due_date" in payload else current["due_date"]
    now = _now()
    with conn:
        conn.execute(
            """
            UPDATE tasks
               SET title = ?, description = ?, status = ?, priority = ?,
                   assignee = ?, due_date = ?, updated_at = ?
             WHERE id = ?
            """,
            (title, description, status, priority, assignee, due_date, now, task_id),
        )
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: int) -> None:
    get_task(conn, task_id)
    with conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
