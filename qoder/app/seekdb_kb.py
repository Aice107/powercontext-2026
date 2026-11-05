"""seekdb 知识库：一个嵌入式实例同时服务 PowerContext 的记忆表和本应用的分块表。

堆表（organization=heap）是 dbms_hybrid_search 的硬性要求；
日期过滤列用 int 的 yyyymmdd（seekdb 的 range 只接受数值常量）。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

from pylibseekdb import SeekdbError, open as seekdb_open

from .config import Settings
from .embedder import Embedder
from .sql_literal import sql_str

TABLE = "chunks"

DDL = (
    f"create table {TABLE} ("
    " chunk_id varchar(64) primary key,"
    " doc_id varchar(128),"
    " title varchar(256),"
    " kind varchar(24),"
    " project varchar(64),"
    " tags varchar(256),"
    " dd int,"
    " doc_date varchar(10),"
    " section varchar(256),"
    " content text,"
    " embedding vector({dim})"
    ") organization=heap"
)

VECTOR_INDEX = f"create vector index ix_chunks_vec on {TABLE}(embedding) with (distance=l2, type=hnsw)"
FULLTEXT_INDEX = f"create fulltext index ix_chunks_fts on {TABLE}(content) with parser ngram"

RETURN_COLUMNS = ["chunk_id", "doc_id", "title", "kind", "project", "tags", "doc_date", "dd", "section", "content"]


@dataclass
class SearchOutcome:
    hits: list[dict]
    dsl: dict
    sql: str
    elapsed_ms: float
    mode: str

    def to_api(self) -> dict:
        return {
            "hits": self.hits,
            "dsl": self.dsl,
            "sql": self.sql,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "mode": self.mode,
        }


class KnowledgeBase:
    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self.settings = settings
        self.embedder = embedder
        self._instance = None
        self._cursor = None
        self._lock = threading.Lock()

    # ---------- 生命周期 ----------

    def open(self) -> None:
        if self._cursor is not None:
            return
        self.settings.seekdb_dir.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for _ in range(3):
            try:
                self._instance = seekdb_open(db_dir=str(self.settings.seekdb_dir))
                break
            except SeekdbError as error:  # 偶发的端口/目录竞态，重试
                last_error = error
                time.sleep(1.0)
        if self._instance is None:
            raise RuntimeError(f"seekdb 启动失败: {last_error}")
        connection = self._instance.connect(database="test", autocommit=True)
        cursor = connection.cursor()
        cursor.execute(f"create database if not exists {self.settings.seekdb_database}")
        if self.settings.seekdb_database != "test":
            connection.close()
            connection = self._instance.connect(database=self.settings.seekdb_database, autocommit=True)
        self._cursor = connection.cursor()
        self._ensure_schema()

    def close(self) -> None:
        if self._instance is not None:
            self._instance.close()
            self._instance = None
            self._cursor = None

    def _execute(self, sql: str) -> list[tuple] | None:
        with self._lock:
            self._cursor.execute(sql)
            try:
                return self._cursor.fetchall()
            except Exception:
                return None

    def _ensure_schema(self) -> None:
        dim = self.embedder.dim
        ddl = DDL.format(dim=dim)
        try:
            self._execute(ddl)
        except Exception:
            pass  # 表已存在（code=1050）
        # 索引已存在时 create 会报错，忽略即可
        try:
            self._execute(VECTOR_INDEX)
        except Exception:
            pass
        try:
            self._execute(FULLTEXT_INDEX)
        except Exception:
            pass

    # ---------- 写入 ----------

    def upsert_chunks(self, chunks: list[dict]) -> int:
        if not chunks:
            return 0
        for chunk in chunks:
            embedding = chunk["embedding"]
            vector = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
            values = (
                sql_str(chunk["chunk_id"]),
                sql_str(chunk["doc_id"]),
                sql_str(chunk["title"]),
                sql_str(chunk["kind"]),
                sql_str(chunk["project"]),
                sql_str(chunk.get("tags", "")),
                str(chunk["dd"]),
                sql_str(chunk["doc_date"]),
                sql_str(chunk.get("section", "")),
                sql_str(chunk["content"]),
                sql_str(vector),
            )
            self._execute(
                f"delete from {TABLE} where chunk_id = {values[0]}"
            )
            self._execute(
                f"insert into {TABLE} (chunk_id, doc_id, title, kind, project, tags, dd, doc_date, section, content, embedding) "
                f"values ({', '.join(values)})"
            )
        return len(chunks)

    def delete_doc(self, doc_id: str) -> int:
        rows = self._execute(f"select count(*) from {TABLE} where doc_id = {sql_str(doc_id)}")
        count = int(rows[0][0]) if rows else 0
        self._execute(f"delete from {TABLE} where doc_id = {sql_str(doc_id)}")
        return count

    def doc_ids(self) -> list[dict]:
        rows = self._execute(
            f"select doc_id, title, kind, project, doc_date, count(*) from {TABLE} "
            "group by doc_id, title, kind, project, doc_date order by max(dd) desc"
        )
        return [
            {
                "doc_id": r[0],
                "title": r[1],
                "kind": r[2],
                "project": r[3],
                "doc_date": r[4],
                "chunks": int(r[5]),
            }
            for r in (rows or [])
        ]

    def stats(self) -> dict:
        rows = self._execute(f"select count(*) from {TABLE}")
        total = int(rows[0][0]) if rows else 0
        by_kind: dict[str, int] = {}
        rows = self._execute(f"select kind, count(*) from {TABLE} group by kind")
        for r in rows or []:
            by_kind[str(r[0])] = int(r[1])
        return {"chunks": total, "by_kind": by_kind, "dim": self.embedder.dim}

    # ---------- 检索 ----------

    def _filters(self, project: str | None, kind: str | None, since: int | None, until: int | None) -> list[dict]:
        conditions: list[dict] = []
        if project:
            conditions.append({"term": {"project": project}})
        if kind:
            conditions.append({"term": {"kind": kind}})
        range_clause: dict[str, int] = {}
        if since is not None:
            range_clause["gte"] = int(since)
        if until is not None:
            range_clause["lte"] = int(until)
        if range_clause:
            conditions.append({"range": {"dd": range_clause}})
        return conditions

    def _run_search(self, dsl: dict, mode: str) -> SearchOutcome:
        started = time.perf_counter()
        dsl_json = json.dumps(dsl, ensure_ascii=False)
        sql = (
            f"select dbms_hybrid_search.search({sql_str(TABLE)}, {sql_str(dsl_json)}) as result"
        )
        rows = self._execute(sql)
        elapsed = (time.perf_counter() - started) * 1000
        raw = rows[0][0] if rows and rows[0] and rows[0][0] else "[]"
        parsed = json.loads(raw)
        hits = [self._normalize_hit(item) for item in parsed]
        return SearchOutcome(hits=hits, dsl=dsl, sql=sql, elapsed_ms=elapsed, mode=mode)

    def _normalize_hit(self, item: dict) -> dict:
        hit = {key: item.get(key) for key in RETURN_COLUMNS if key in item}
        hit["_score"] = item.get("_score")
        hit["snippet"] = (item.get("content") or "")[:240]
        return hit

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        project: str | None = None,
        kind: str | None = None,
        since: int | None = None,
        until: int | None = None,
        size: int = 8,
        rank_constant: int = 30,
    ) -> SearchOutcome:
        self.open()
        filters = self._filters(project, kind, since, until)
        query_vector = json.dumps(self.embedder.embed([query], is_query=True)[0])
        knn: dict = {"field": "embedding", "k": size, "query_vector": query_vector}
        if filters:
            knn["filter"] = filters
        if mode == "vector":
            dsl: dict = {"knn": knn, "size": size}
        elif mode == "fts":
            dsl = {"query": {"match": {"content": query}}, "size": size}
            if filters:
                dsl["query"] = {"bool": {"must": [{"match": {"content": query}}], "filter": filters}}
        else:
            dsl = {
                "query": {"bool": {"must": [{"match": {"content": query}}], "filter": filters}}
                if filters
                else {"match": {"content": query}},
                "knn": knn,
                "rank": {"rrf": {"rank_constant": rank_constant}},
                "size": size,
            }
        return self._run_search(dsl, mode)
