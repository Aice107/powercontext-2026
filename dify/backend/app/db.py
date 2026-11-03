"""seekdb 访问层：连接、重试、轻量连接池。

只用 pymysql，不引 ORM——评审可直接对照 SQL 与建表脚本。
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

DB_CONF = {
    "host": os.getenv("SEEKDB_HOST", "127.0.0.1"),
    "port": int(os.getenv("SEEKDB_PORT", "2891")),
    "user": os.getenv("SEEKDB_USER", "root"),
    "password": os.getenv("SEEKDB_PASSWORD", ""),
    "database": os.getenv("SEEKDB_DATABASE", "inn"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": True,
    "connect_timeout": 5,
    "read_timeout": 10,
    "write_timeout": 10,
}


@contextmanager
def conn():
    """每次请求取连接；失败重试 2 次（seekdb 重启后首个连接可能被拒）。"""
    last: Exception | None = None
    for attempt in range(3):
        try:
            c = pymysql.connect(**DB_CONF)
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.3 * (attempt + 1))
    else:
        raise RuntimeError(f"seekdb connect failed: {last}")
    try:
        yield c
    finally:
        c.close()


def query(sql: str, args: tuple | list = ()) -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def execute(sql: str, args: tuple | list = ()) -> int:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.rowcount


def one(sql: str, args: tuple | list = ()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def ping() -> bool:
    try:
        one("SELECT 1 AS ok")
        return True
    except Exception:  # noqa: BLE001
        return False
