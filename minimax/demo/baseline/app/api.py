"""Flask HTTP layer for TaskHub."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from . import store
from .validation import ValidationError, parse_int, parse_priority, parse_status


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


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    return payload
