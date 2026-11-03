#!/usr/bin/env python3
"""给 seed 进库的历史事件补向量。

背景：`04_seed_demo.sql` 只写结构化字段（SQL 里算不了哈希向量），
补一遍 embedding 之后，"翻旧账"的相似度分数才是真实的向量分数，
而不是 0（只有全文命中）。

用法：backend/.venv/bin/python tools/seed_embeddings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import db, embedding  # noqa: E402


def main() -> int:
    rows = db.query("SELECT id, action_text FROM inn_ledger WHERE embedding IS NULL")
    for r in rows:
        db.execute(
            "UPDATE inn_ledger SET embedding=%s WHERE id=%s",
            (embedding.to_literal(embedding.embed(r["action_text"])), r["id"]),
        )
    rumors = db.query("SELECT id, rumor_text FROM inn_rumor WHERE embedding IS NULL")
    for r in rumors:
        db.execute(
            "UPDATE inn_rumor SET embedding=%s WHERE id=%s",
            (embedding.to_literal(embedding.embed(r["rumor_text"])), r["id"]),
        )
    print(f"embedded ledger={len(rows)} rumor={len(rumors)} (mode={embedding.MODE}, dim={embedding.DIM})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
