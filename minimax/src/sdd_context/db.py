"""Embedded seekdb storage for engineering sources, chunks and terms.

``pylibseekdb`` starts an in-process seekdb instance and exposes a unix socket
through ``connection_options()``.  We talk to that socket with PyMySQL so all
statements are parameterised and ordinary SQL can be inspected/logged.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import pymysql
import pylibseekdb

DATABASE = "sdd"

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sources (
      source_id   VARCHAR(64) PRIMARY KEY,
      kind        VARCHAR(16) NOT NULL,
      path        VARCHAR(512) NOT NULL,
      title       VARCHAR(256),
      sha256      CHAR(64) NOT NULL,
      imported_at VARCHAR(40) NOT NULL,
      UNIQUE KEY uk_sources_path (path)
    ) CHARACTER SET utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
      chunk_id    VARCHAR(64) PRIMARY KEY,
      source_id   VARCHAR(64) NOT NULL,
      ordinal     INT NOT NULL,
      kind        VARCHAR(16) NOT NULL,
      path        VARCHAR(512) NOT NULL,
      start_line  INT NOT NULL,
      end_line    INT NOT NULL,
      text        MEDIUMTEXT NOT NULL,
      symbol      VARCHAR(256),
      spec_id     VARCHAR(64),
      title       VARCHAR(256),
      token_count INT NOT NULL DEFAULT 0,
      meta_json   MEDIUMTEXT,
      KEY idx_chunks_source (source_id),
      KEY idx_chunks_kind (kind),
      KEY idx_chunks_spec (spec_id)
    ) CHARACTER SET utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS terms (
      term     VARCHAR(64) NOT NULL,
      chunk_id VARCHAR(64) NOT NULL,
      tf       INT NOT NULL,
      KEY idx_terms_term (term),
      KEY idx_terms_chunk (chunk_id)
    ) CHARACTER SET utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS import_events (
      event_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
      path       VARCHAR(512) NOT NULL,
      sha256     CHAR(64) NOT NULL,
      action     VARCHAR(16) NOT NULL,
      imported_at VARCHAR(40) NOT NULL,
      KEY idx_import_path (path)
    ) CHARACTER SET utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS task_runs (
      run_id       VARCHAR(64) PRIMARY KEY,
      task_id      VARCHAR(64) NOT NULL,
      phase        VARCHAR(32) NOT NULL,
      status       VARCHAR(16) NOT NULL,
      started_at   VARCHAR(40) NOT NULL,
      finished_at  VARCHAR(40),
      summary_json MEDIUMTEXT,
      KEY idx_runs_task (task_id)
    ) CHARACTER SET utf8mb4
    """,
]


class SeekdbStore:
    """Own one embedded seekdb instance and one PyMySQL connection."""

    def __init__(self, db_dir: str | Path, query_log: str | Path | None = None) -> None:
        self.db_dir = Path(db_dir).resolve()
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.query_log = Path(query_log).resolve() if query_log else None
        if self.query_log:
            self.query_log.parent.mkdir(parents=True, exist_ok=True)
        self._instance = pylibseekdb.open(str(self.db_dir))
        options = pylibseekdb.connection_options()
        self._conn = pymysql.connect(
            user=options.get("user", "root"),
            unix_socket=options["unix_socket"],
            database="test",
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._init_database()

    # ------------------------------------------------------------------ basics
    def _init_database(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {DATABASE} CHARACTER SET utf8mb4"
            )
        self._conn.select_db(DATABASE)
        for statement in SCHEMA:
            with self._conn.cursor() as cur:
                cur.execute(statement)
        self._log_sql("SCHEMA", (), 0, 0.0)

    def _log_sql(
        self,
        sql: str,
        params: Sequence[Any] | None,
        rowcount: int,
        duration_ms: float,
    ) -> None:
        if not self.query_log:
            return
        record = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "sql": " ".join(sql.split())[:600],
            "params": _safe_params(params),
            "rowcount": rowcount,
            "duration_ms": round(duration_ms, 3),
        }
        with self.query_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        started = time.perf_counter()
        with self._conn.cursor() as cur:
            rowcount = cur.execute(sql, tuple(params) if params is not None else None)
        self._log_sql(sql, params, int(rowcount or 0), (time.perf_counter() - started) * 1000)
        return int(rowcount or 0)

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        started = time.perf_counter()
        with self._conn.cursor() as cur:
            rowcount = cur.executemany(sql, rows)
        self._log_sql(sql, (f"<{len(rows)} rows>",), int(rowcount or 0), (time.perf_counter() - started) * 1000)
        return int(rowcount or 0)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        started = time.perf_counter()
        with self._conn.cursor() as cur:
            cur.execute(sql, tuple(params) if params is not None else None)
            rows = list(cur.fetchall())
        self._log_sql(sql, params, len(rows), (time.perf_counter() - started) * 1000)
        return rows

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        try:
            self._conn.close()
        finally:
            self._instance.close()

    def __enter__(self) -> "SeekdbStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ domain
    def get_source(self, path: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM sources WHERE path = %s", (path,))

    def delete_source(self, path: str) -> None:
        source = self.get_source(path)
        if not source:
            return
        chunk_ids = [
            row["chunk_id"]
            for row in self.query("SELECT chunk_id FROM chunks WHERE source_id = %s", (source["source_id"],))
        ]
        if chunk_ids:
            placeholders = ",".join(["%s"] * len(chunk_ids))
            self.execute(f"DELETE FROM terms WHERE chunk_id IN ({placeholders})", chunk_ids)
        self.execute("DELETE FROM chunks WHERE source_id = %s", (source["source_id"],))
        self.execute("DELETE FROM sources WHERE source_id = %s", (source["source_id"],))

    def stats(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("sources", "chunks", "terms", "import_events", "task_runs"):
            row = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")
            result[table] = int(row["n"]) if row else 0
        return result


def _safe_params(params: Sequence[Any] | None) -> list[Any] | None:
    if params is None:
        return None
    safe: list[Any] = []
    for value in params:
        if isinstance(value, str) and len(value) > 300:
            safe.append(value[:300] + f"...<{len(value)} chars>")
        elif isinstance(value, bytes):
            safe.append(f"<{len(value)} bytes>")
        else:
            safe.append(value)
    return safe


def default_db_dir(workspace: str | Path) -> Path:
    """Keep the embedded database out of the indexed workspace."""

    return Path(workspace).resolve().parent / ".runtime" / "seekdb"


def env_or(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default
