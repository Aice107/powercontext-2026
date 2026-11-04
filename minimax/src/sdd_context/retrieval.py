"""SQL-backed lexical retrieval and category selection."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from .db import SeekdbStore
from .tokenizer import query_terms

K1 = 1.2
B = 0.75


@dataclass
class SearchHit:
    chunk_id: str
    kind: str
    path: str
    start_line: int
    end_line: int
    text: str
    symbol: str | None
    spec_id: str | None
    title: str | None
    token_count: int
    sha256: str
    score: float
    matched_terms: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_context_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "sha256": self.sha256,
            "score": round(self.score, 6),
            "text": self.text,
        }
        if self.spec_id:
            entry["spec_id"] = self.spec_id
        if self.symbol:
            entry["symbol"] = self.symbol
        if self.title:
            entry["title"] = self.title
        if self.meta:
            entry["meta"] = self.meta
        return entry


def search(store: SeekdbStore, query: str, *, limit: int = 60) -> tuple[list[SearchHit], list[str]]:
    terms = query_terms(query)
    if not terms:
        return [], terms
    placeholders = ",".join(["%s"] * len(terms))
    rows = store.query(
        f"""
        SELECT t.term, t.tf, c.chunk_id, c.kind, c.path, c.start_line, c.end_line,
               c.text, c.symbol, c.spec_id, c.title, c.token_count, c.meta_json,
               s.sha256
          FROM terms t
          JOIN chunks c ON c.chunk_id = t.chunk_id
          JOIN sources s ON s.source_id = c.source_id
         WHERE t.term IN ({placeholders})
        """,
        terms,
    )
    if not rows:
        return [], terms

    df_rows = store.query(
        f"SELECT term, COUNT(DISTINCT chunk_id) AS df FROM terms WHERE term IN ({placeholders}) GROUP BY term",
        terms,
    )
    df = {row["term"]: int(row["df"]) for row in df_rows}
    total_row = store.query_one("SELECT COUNT(*) AS n, AVG(token_count) AS avgdl FROM chunks")
    total = max(1, int(total_row["n"] or 1)) if total_row else 1
    avgdl = float(total_row["avgdl"] or 1.0) if total_row else 1.0

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        chunk_id = row["chunk_id"]
        item = grouped.get(chunk_id)
        if item is None:
            item = {
                "row": row,
                "tf": {},
                "matched": [],
            }
            grouped[chunk_id] = item
        item["tf"][row["term"]] = int(row["tf"])
        item["matched"].append(row["term"])

    hits: list[SearchHit] = []
    for chunk_id, item in grouped.items():
        row = item["row"]
        score = 0.0
        dl = max(1, int(row["token_count"] or 1))
        for term, tf in item["tf"].items():
            term_df = df.get(term, 1)
            idf = math.log(1.0 + (total - term_df + 0.5) / (term_df + 0.5))
            score += idf * (tf * (K1 + 1.0)) / (tf + K1 * (1.0 - B + B * dl / avgdl))
        haystack = " ".join(
            str(part or "") for part in (row["path"], row["symbol"], row["spec_id"], row["title"])
        ).lower()
        for term in item["matched"]:
            if term in haystack:
                score *= 1.2
                break
        try:
            meta = json.loads(row["meta_json"]) if row["meta_json"] else {}
        except json.JSONDecodeError:
            meta = {}
        hits.append(
            SearchHit(
                chunk_id=chunk_id,
                kind=row["kind"],
                path=row["path"],
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                text=row["text"],
                symbol=row["symbol"],
                spec_id=row["spec_id"],
                title=row["title"],
                token_count=dl,
                sha256=row["sha256"],
                score=score,
                matched_terms=sorted(set(item["matched"])),
                meta=meta,
            )
        )
    hits.sort(key=lambda hit: (-hit.score, hit.path, hit.start_line))
    return hits[:limit], terms


def select_categories(
    hits: list[SearchHit],
    *,
    max_specs: int = 6,
    max_code: int = 8,
    max_tests: int = 8,
) -> tuple[dict[str, list[SearchHit]], list[str]]:
    warnings: list[str] = []

    def take(kind: str, limit: int, key) -> list[SearchHit]:
        selected: list[SearchHit] = []
        seen: set[str] = set()
        for hit in hits:
            if hit.kind != kind:
                continue
            identity = key(hit)
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(hit)
            if len(selected) >= limit:
                break
        return selected

    specs = take("spec", max_specs, lambda hit: hit.spec_id or f"{hit.path}:{hit.start_line}")
    code = take("code", max_code, lambda hit: f"{hit.path}::{hit.symbol}")
    tests = take("test", max_tests, lambda hit: f"{hit.path}::{hit.symbol}")
    if not specs:
        warnings.append("no applicable specification chunk matched the task")
    if not code:
        warnings.append("no code chunk matched the task")
    if not tests:
        warnings.append("no test chunk matched the task")
    return {"spec": specs, "code": code, "test": tests}, warnings
