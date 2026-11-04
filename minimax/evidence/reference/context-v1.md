# SDD development context

- Task ID: `taskhub-due-before`
- Workspace: `/home/ice/dify-project/minimax/.runtime/demo-test-replay2/workspace`
- Context SHA-256: `7a4dc8da7baaffa7831d37c1f75c0963ccce50618906a720550cbaeffa2a6b21`
- Generated at: 2026-11-04T14:27:01+0800

## Task

### 为 TaskHub 列表接口增加 due_before 截止日期筛选

## 任务

在 TaskHub 服务中，为 `GET /tasks` 增加可选的 `due_before=YYYY-MM-DD` 截止日期上界筛选。
调用方传入该参数时，只返回截止日期不晚于该日期的任务。

## 要改什么

- 筛选是闭区间：截止日期等于 `due_before` 的任务必须包含在结果中（包含截止当天）。
- `due_date` 为空的任务在启用该筛选时必须排除。
- `due_before` 必须与既有 `status`、`priority`、`assignee` 筛选以及 `limit`/`offset` 分页按 AND 组合生效，
  `total` 返回筛选后的总数。
- 非法日期（格式错误或 2026-02-30 这类不存在的日期）返回 400，错误 `code=invalid_argument`，
  `field=due_before`。
- 不传 `due_before` 时，既有列表行为、分页元数据、错误格式与状态码完全不变。

## 哪些原有行为必须保持

- `GET /tasks` 不传筛选参数时仍返回全部 8 条种子任务，按 id 升序。
- `status`、`priority`、`assignee` 筛选与分页仍然正确。
- 创建、读取、更新、删除任务的行为与错误格式不变。
- `tests/test_tasks_regression.py` 中的所有断言必须继续通过。

## 1. Applicable specifications

### SPEC-API-030

Source: `specs/task-api.md:81-84` (sha256 `3866cad7bfc3`, score 79.800)

```text
### SPEC-API-030 回归保证

本次变更不得改变既有接口的路径、字段名、分页元数据、错误格式与状态码。
`tests/test_tasks_regression.py` 中的断言是必须保持的行为基线。
```

### SPEC-API-011

Source: `specs/task-api.md:51-60` (sha256 `3866cad7bfc3`, score 65.598)

```text
### SPEC-API-011 既有筛选

列表支持以下可选筛选参数，多个条件按 AND 组合：

- `status`：精确匹配状态；非法值返回 400。
- `priority`：精确匹配优先级；非法值返回 400。
- `assignee`：精确匹配负责人。

不传筛选参数时返回全部任务。
```

### SPEC-API-010

Source: `specs/task-api.md:41-50` (sha256 `3866cad7bfc3`, score 64.770)

```text
### SPEC-API-010 列表入口

`GET /tasks` 返回任务列表与分页元数据：

```json
{"items": [...], "total": 8, "limit": 50, "offset": 0}
```

`items` 按 `id` 升序排列。`total` 是应用筛选后的总数，不受 `limit`/`offset` 影响。
```

### SPEC-API-002

Source: `specs/task-api.md:14-24` (sha256 `3866cad7bfc3`, score 41.987)

```text
### SPEC-API-002 错误格式

错误响应统一为：

```json
{"error": {"code": "invalid_argument", "message": "...", "field": "..."}}
```

- 参数非法：400，`code=invalid_argument`。
- 资源不存在：404，`code=not_found`。
```

### SPEC-API-003

Source: `specs/task-api.md:27-38` (sha256 `3866cad7bfc3`, score 41.875)

```text
### SPEC-API-003 字段定义

任务包含 `id`、`title`、`description`、`status`、`priority`、`assignee`、`due_date`、
`created_at`、`updated_at`。

- `title`：必填，非空，最长 200 字符。
- `status`：`todo`、`in_progress`、`done` 之一，默认 `todo`。
- `priority`：`low`、`medium`、`high` 之一，默认 `medium`。
- `assignee`：可空字符串。
- `due_date`：可空，严格 `YYYY-MM-DD`；非法日期返回 400。
- 时间戳使用 UTC ISO 8601。
```

### SPEC-API-001

Source: `specs/task-api.md:9-13` (sha256 `3866cad7bfc3`, score 40.754)

```text
### SPEC-API-001 JSON 与状态码

所有接口返回 `application/json`。成功状态码为 200（查询/更新）、201（创建）或 204（删除）。
请求体必须是 JSON 对象；否则返回 400。
```

## 2. Code to change

### parse_date

Source: `app/validation.py:62-75` (sha256 `88450369442c`, score 17.944)

```python
def parse_date(value: Any, field: str = "due_date") -> str | None:
    """Parse a strict ISO date (YYYY-MM-DD) into its canonical text form."""

    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a YYYY-MM-DD string or null", field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be a valid YYYY-MM-DD date", field) from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"{field} must be a valid YYYY-MM-DD date", field)
    return parsed.isoformat()
```

### list_tasks

Source: `app/store.py:93-124` (sha256 `18fe8b40e2d2`, score 14.943)

```python
def list_tasks(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
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
```

### ValidationError

Source: `app/validation.py:9-13` (sha256 `88450369442c`, score 12.924)

```python
class ValidationError(ValueError):
    """A caller-visible invalid argument (HTTP 400)."""

    code = "invalid_argument"
```

### <module>

Source: `app/store.py:1-48` (sha256 `18fe8b40e2d2`, score 12.816)

```python
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
```

### update_task

Source: `app/store.py:155-182` (sha256 `18fe8b40e2d2`, score 12.405)

```python
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
```

### create_task

Source: `app/store.py:134-152` (sha256 `18fe8b40e2d2`, score 11.876)

```python
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
```

### create_app

Source: `app/api.py:15-95` (sha256 `83f00e65566e`, score 11.639)

```python
def create_app(db_path: str | Path | None = None, *, seed: bool = True) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path or Path(__file__).resolve().parent.parent / "taskhub.sqlite3")
    store.init_db(app.config["DB_PATH"])
    if seed:
        store.seed_tasks(app.config["DB_PATH"])

    def connection():
        return store.connect(app.config["DB_PATH"])

    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok"})

    @app.get("/tasks")
    def list_tasks() -> Any:
        status = request.args.get("status")
        priority = request.args.get("priority")
        assignee = request.args.get("assignee")
        if status is not None:
            status = parse_status(status)
        if priority is not None:
            priority = parse_priority(priority)
        limit = parse_int(request.args.get("limit"), "limit", 50, 1, 100)
        offset = parse_int(request.args.get("offset"), "offset", 0, 0, 1_000_000)
        with closing(connection()) as conn:
            result = store.list_tasks(
                conn,
                status=status,
                priority=priority,
                assignee=assignee,
                limit=limit,
                offset=offset,
            )
        return jsonify(result)

    @app.post("/tasks")
    def create_task() -> Any:
        payload = _json_body()
        with closing(connection()) as conn:
            created = store.create_task(conn, payload)
        return jsonify(created), 201

    @app.get("/tasks/<int:task_id>")
    def get_task(task_id: int) -> Any:
        with closing(connection()) as conn:
            return jsonify(store.get_task(conn, task_id))

    @app.patch("/tasks/<int:task_id>")
    def update_task(task_id: int) -> Any:
        payload = _json_body()
        with closing(connection()) as conn:
            return jsonify(store.update_task(conn, task_id, payload))

    @app.delete("/tasks/<int:task_id>")
    def delete_task(task_id: int) -> Any:
        with closing(connection()) as conn:
            store.delete_task(conn, task_id)
        return "", 204

    @app.errorhandler(ValidationError)
    def handle_validation_error(exc: ValidationError) -> Any:
        status_code = 404 if exc.code == "not_found" else 400
        return (
            jsonify(
                {
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "field": exc.field,
                    }
                }
            ),
            status_code,
        )

    @app.errorhandler(404)
    def handle_not_found(_exc: Any) -> Any:
        return jsonify({"error": {"code": "not_found", "message": "resource not found"}}), 404

    return app
```

### seed_tasks

Source: `app/store.py:63-80` (sha256 `18fe8b40e2d2`, score 10.521)

```python
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
```

## 3. Tests for functional and compatibility verification

### test_due_before_invalid_date_returns_400

Source: `tests/test_due_before.py:31-37` (sha256 `85d09bd5b5a5`, score 37.927)

```python
def test_due_before_invalid_date_returns_400(client):
    for value in ("2026-13-01", "not-a-date", "2026-02-30"):
        response = client.get(f"/tasks?due_before={value}")
        assert response.status_code == 400, value
        error = response.get_json()["error"]
        assert error["code"] == "invalid_argument"
        assert error["field"] == "due_before"
```

### test_due_before_includes_boundary_day

Source: `tests/test_due_before.py:10-16` (sha256 `85d09bd5b5a5`, score 32.097)

```python
def test_due_before_includes_boundary_day(client):
    response = client.get("/tasks?due_before=2026-01-31&limit=100")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 4
    assert [item["id"] for item in body["items"]] == [1, 2, 4, 7]
    assert all(item["due_date"] <= "2026-01-31" for item in body["items"])
```

### test_create_rejects_invalid_date

Source: `tests/test_tasks_regression.py:109-112` (sha256 `b5fa9d83f365`, score 30.087)

```python
def test_create_rejects_invalid_date(client):
    response = client.post("/tasks", json={"title": "Bad date", "due_date": "2026-02-30"})
    assert response.status_code == 400
    assert response.get_json()["error"]["field"] == "due_date"
```

### test_due_before_combines_with_status_and_pagination

Source: `tests/test_due_before.py:19-28` (sha256 `85d09bd5b5a5`, score 29.761)

```python
def test_due_before_combines_with_status_and_pagination(client):
    filtered = client.get("/tasks?due_before=2026-01-31&status=todo").get_json()
    assert filtered["total"] == 2
    assert [item["id"] for item in filtered["items"]] == [1, 2]

    page = client.get("/tasks?due_before=2026-01-31&status=todo&limit=1&offset=1").get_json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert [item["id"] for item in page["items"]] == [2]
```

### test_list_returns_seed_rows_and_pagination_metadata

Source: `tests/test_tasks_regression.py:12-21` (sha256 `b5fa9d83f365`, score 27.562)

```python
def test_list_returns_seed_rows_and_pagination_metadata(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 8
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["id"] for item in body["items"]] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert body["items"][0]["title"] == "Fix login redirect"
    assert body["items"][0]["due_date"] == "2026-01-30"
```

### test_due_before_excludes_tasks_without_due_date

Source: `tests/test_due_before.py:40-44` (sha256 `85d09bd5b5a5`, score 25.718)

```python
def test_due_before_excludes_tasks_without_due_date(client):
    body = client.get("/tasks?due_before=2026-12-31").get_json()
    assert body["total"] == 7
    assert 5 not in {item["id"] for item in body["items"]}
    assert all(item["due_date"] is not None for item in body["items"])
```

### test_create_read_update_delete

Source: `tests/test_tasks_regression.py:52-80` (sha256 `b5fa9d83f365`, score 22.530)

```python
def test_create_read_update_delete(client):
    created = client.post(
        "/tasks",
        json={
            "title": "Write release notes",
            "description": "Summarise the due_before change",
            "status": "todo",
            "priority": "medium",
            "assignee": "dana",
            "due_date": "2026-02-20",
        },
    )
    assert created.status_code == 201
    task = created.get_json()
    assert task["id"] == 9
    assert task["due_date"] == "2026-02-20"

    fetched = client.get(f"/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["title"] == "Write release notes"

    updated = client.patch(f"/tasks/{task['id']}", json={"status": "done", "priority": "high"})
    assert updated.status_code == 200
    assert updated.get_json()["status"] == "done"
    assert updated.get_json()["priority"] == "high"

    deleted = client.delete(f"/tasks/{task['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/tasks/{task['id']}").status_code == 404
```

### test_create_validation_errors_use_json_error_shape

Source: `tests/test_tasks_regression.py:83-88` (sha256 `b5fa9d83f365`, score 22.339)

```python
def test_create_validation_errors_use_json_error_shape(client):
    response = client.post("/tasks", json={"title": " ", "status": "todo"})
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "invalid_argument"
    assert error["field"] == "title"
```

## 4. Current progress

- No saved state loaded (fresh context).
