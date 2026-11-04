"""seekdb storage for engineering sources, chunks and terms.

The demo uses a local seekdb server (the binary shipped inside the
``pylibseekdb`` wheel) and talks to it with PyMySQL.  A server, rather than the
in-process embedding, is used because the CLI starts a new process for every
command and the data must still be visible to the next command.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import pymysql

DATABASE = "sdd"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 2893

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


class SeekdbUnavailable(RuntimeError):
    """The local seekdb server is not reachable."""


class SeekdbStore:
    """One PyMySQL connection to the local seekdb server."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        query_log: str | Path | None = None,
    ) -> None:
        self.host = host or os.environ.get("SEEKDB_HOST") or DEFAULT_HOST
        self.port = int(port or os.environ.get("SEEKDB_PORT") or DEFAULT_PORT)
        self.database = database or os.environ.get("SEEKDB_DATABASE") or DATABASE
        self.query_log = Path(query_log).resolve() if query_log else None
        if self.query_log:
            self.query_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=os.environ.get("SEEKDB_USER", "root"),
                password=os.environ.get("SEEKDB_PASSWORD", ""),
                charset="utf8mb4",
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
        except pymysql.err.OperationalError as exc:
            raise SeekdbUnavailable(
                f"seekdb is not reachable at {self.host}:{self.port}: {exc}. "
                "Start it with scripts/seekdb_server.sh start."
            ) from exc
        self._init_database()

    def _init_database(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.database):
            raise ValueError(f"invalid database name: {self.database!r}")
        with self._conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {self.database} CHARACTER SET utf8mb4")
        self._conn.select_db(self.database)
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
        self._conn.close()

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

    def version(self) -> str:
        row = self.query_one("SELECT VERSION() AS version")
        return str(row["version"]) if row else "unknown"

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
