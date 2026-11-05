"""命令行入口：初始化、导入语料、检索、记忆读写、草稿、重置。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import load_settings
from .embedder import Embedder
from .ingest import parse_document
from .journal import Journal
from .memory import PowerContextMemory
from .seekdb_kb import KnowledgeBase


def _make():
    settings = load_settings()
    embedder = Embedder(settings)
    kb = KnowledgeBase(settings, embedder)
    journal = Journal(settings.log_dir)
    memory = PowerContextMemory(settings, journal)
    kb.open()
    return settings, embedder, kb, journal, memory


def cmd_doctor(_args) -> int:
    settings, embedder, kb, journal, memory = _make()
    report = {
        "seekdb_dir": str(settings.seekdb_dir),
        "seekdb_stats": kb.stats(),
        "embedding": {"model": embedder.model_id, "dim": embedder.dim,
                      "model_dir": str(settings.model_dir)},
        "powercontext_health": memory.health(),
        "pc_base_url": settings.pc_base_url,
        "scope_id": memory.ensure_scope(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_sample(_args) -> int:
    _settings, embedder, kb, journal, _memory = _make()
    total = 0
    for path in sorted(Path(_settings.corpus_dir).glob("*.md")):
        document = parse_document(path.read_text(encoding="utf-8"), fallback_name=path.stem)
        chunks = document["chunks"]
        vectors = embedder.embed([c.embed_text for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
        written = kb.upsert_chunks([c.to_row() for c in chunks])
        total += written
        print(f"[ingest] {document['meta']['title']} -> {written} chunks")
    journal.append("seekdb", {"action": "ingest_sample", "chunks": total})
    print(f"[ingest] 完成，共 {total} chunks；{json.dumps(kb.stats(), ensure_ascii=False)}")
    return 0


def cmd_search(args) -> int:
    _settings, _embedder, kb, journal, _memory = _make()
    outcome = kb.search(args.query, mode=args.mode, project=args.project, kind=args.kind,
                        since=_int_date(args.since), until=_int_date(args.until), size=args.size)
    journal.append("seekdb", {"action": "search", "query": args.query, "mode": args.mode,
                              "hits": len(outcome.hits), "sql": outcome.sql})
    print(outcome.sql)
    print("-" * 60)
    for index, hit in enumerate(outcome.hits, 1):
        print(f"{index:>2}. [{hit.get('_score'):.4f}] 《{hit.get('title')}》{hit.get('section')} "
              f"({hit.get('kind')}/{hit.get('project')}/{hit.get('doc_date')})")
        print(f"    {(hit.get('snippet') or '')[:100]}")
    return 0


def cmd_remember(args) -> int:
    _settings, _embedder, _kb, _journal, memory = _make()
    result = memory.remember(args.kind, args.text, args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_recall(args) -> int:
    _settings, _embedder, _kb, _journal, memory = _make()
    result = memory.search(args.query, mode=args.mode, limit=args.limit)
    for hit in result["hits"]:
        print(json.dumps(hit, ensure_ascii=False)[:240])
    if not result["hits"]:
        print("(没有命中)")
    return 0


def cmd_draft(args) -> int:
    from .draft import build_draft

    _settings, _embedder, kb, journal, memory = _make()
    result = build_draft(kb, memory, since=_int_date(args.since), until=_int_date(args.until),
                         project=args.project, size=args.size)
    print(result.markdown)
    journal.append("draft", {"action": "draft", "since": args.since, "until": args.until,
                             "preferences_applied": result.preferences_applied})
    return 0


def cmd_reset(args) -> int:
    settings = load_settings()
    if args.all:
        shutil.rmtree(settings.home, ignore_errors=True)
        print(f"[reset] 已删除 {settings.home}（seekdb 数据 + 模型 + 日志）")
        return 0
    kb_dir = settings.seekdb_dir
    shutil.rmtree(kb_dir, ignore_errors=True)
    print(f"[reset] 已删除 seekdb 数据 {kb_dir}；模型与日志保留")
    return 0


def _int_date(value: str | None) -> int | None:
    if not value:
        return None
    digits = value.replace("-", "").strip()
    return int(digits) if digits.isdigit() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gewu", description="格物 Gewu 命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="检查 seekdb / embedding / PowerContext 状态").set_defaults(func=cmd_doctor)
    sub.add_parser("ingest-sample", help="导入 data/corpus 全部示例语料").set_defaults(func=cmd_ingest_sample)

    p_search = sub.add_parser("search", help="seekdb 混合检索")
    p_search.add_argument("query")
    p_search.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "fts"])
    p_search.add_argument("--project")
    p_search.add_argument("--kind")
    p_search.add_argument("--since")
    p_search.add_argument("--until")
    p_search.add_argument("--size", type=int, default=8)
    p_search.set_defaults(func=cmd_search)

    p_remember = sub.add_parser("remember", help="写入一条 PowerContext 记忆")
    p_remember.add_argument("--kind", default="preference")
    p_remember.add_argument("text")
    p_remember.add_argument("--reason", default="")
    p_remember.set_defaults(func=cmd_remember)

    p_recall = sub.add_parser("recall", help="检索 PowerContext 记忆")
    p_recall.add_argument("query")
    p_recall.add_argument("--mode", default="hybrid", choices=["auto", "fts", "vector", "hybrid"])
    p_recall.add_argument("--limit", type=int, default=6)
    p_recall.set_defaults(func=cmd_recall)

    p_draft = sub.add_parser("draft", help="生成组会草稿")
    p_draft.add_argument("--since", required=True)
    p_draft.add_argument("--until", required=True)
    p_draft.add_argument("--project")
    p_draft.add_argument("--size", type=int, default=12)
    p_draft.set_defaults(func=cmd_draft)

    p_reset = sub.add_parser("reset", help="重置数据")
    p_reset.add_argument("--all", action="store_true", help="连模型与日志一起删除")
    p_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
