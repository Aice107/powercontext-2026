"""格物 Gewu 主服务：seekdb 混合检索 + PowerContext 记忆 + 组会草稿。"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT, load_settings
from .draft import build_draft
from .embedder import Embedder
from .ingest import parse_document
from .journal import Journal
from .memory import PowerContextMemory
from .seekdb_kb import KnowledgeBase

app = FastAPI(title="格物 Gewu", version="1.0.0",
              description="科研笔记管家与组会汇报助手：seekdb 混合检索 + PowerContext 记忆")

settings = load_settings()
journal = Journal(settings.log_dir)
embedder = Embedder(settings)
kb = KnowledgeBase(settings, embedder)
memory = PowerContextMemory(settings, journal)


class IngestRequest(BaseModel):
    filename: str = "粘贴笔记.md"
    content: str = Field(min_length=8)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"
    project: str | None = None
    kind: str | None = None
    since: str | None = None
    until: str | None = None
    size: int = 8
    rank_constant: int = 30


class RememberRequest(BaseModel):
    kind: str = "preference"
    text: str = Field(min_length=2)
    reason: str = ""


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"
    limit: int = 6


class DraftRequest(BaseModel):
    since: str
    until: str
    project: str | None = None
    size: int = 12


def _to_int_date(value: str | None) -> int | None:
    if not value:
        return None
    digits = value.replace("-", "").strip()
    return int(digits) if digits.isdigit() else None


@app.get("/api/health")
def health() -> dict:
    kb.open()
    return {
        "app": "gewu",
        "seekdb": kb.stats(),
        "powercontext": memory.health(),
        "embedding": {"model": embedder.model_id, "dim": embedder.dim},
    }


@app.post("/api/ingest")
def ingest(request: IngestRequest) -> dict:
    document = parse_document(request.content, fallback_name=request.filename)
    if not document["chunks"]:
        raise HTTPException(422, "没有解析出可用正文")
    chunks = document["chunks"]
    vectors = embedder.embed([c.embed_text for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
    kb.open()
    written = kb.upsert_chunks([c.to_row() for c in chunks])
    record = {"action": "ingest", "doc_id": document["doc_id"], "title": document["meta"]["title"],
              "chunks": written, "dim": embedder.dim}
    journal.append("seekdb", record)
    return record


@app.post("/api/ingest/sample")
def ingest_sample() -> dict:
    corpus = settings.corpus_dir
    results = []
    for path in sorted(corpus.glob("*.md")):
        document = parse_document(path.read_text(encoding="utf-8"), fallback_name=path.stem)
        chunks = document["chunks"]
        if not chunks:
            continue
        vectors = embedder.embed([c.embed_text for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
        kb.open()
        written = kb.upsert_chunks([c.to_row() for c in chunks])
        results.append({"doc_id": document["doc_id"], "title": document["meta"]["title"], "chunks": written})
    journal.append("seekdb", {"action": "ingest_sample", "docs": len(results),
                              "chunks": sum(r["chunks"] for r in results)})
    return {"ingested": results}


@app.get("/api/documents")
def documents() -> dict:
    kb.open()
    return {"documents": kb.doc_ids(), "stats": kb.stats()}


@app.post("/api/search")
def search(request: SearchRequest) -> dict:
    kb.open()
    started = time.perf_counter()
    outcome = kb.search(
        request.query,
        mode=request.mode,
        project=request.project or None,
        kind=request.kind or None,
        since=_to_int_date(request.since),
        until=_to_int_date(request.until),
        size=max(1, min(request.size, 30)),
        rank_constant=request.rank_constant,
    )
    payload = outcome.to_api()
    payload["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    journal.append("seekdb", {
        "action": "search", "query": request.query, "mode": request.mode,
        "hits": len(payload["hits"]), "elapsed_ms": payload["elapsed_ms"], "sql": outcome.sql,
    })
    return payload


@app.get("/api/memory/recall")
def memory_recall(q: str, mode: str = "hybrid", limit: int = 6) -> dict:
    try:
        return memory.search(q, mode=mode, limit=limit)
    except Exception as error:
        raise HTTPException(502, str(error)) from error


@app.post("/api/memory/remember")
def memory_remember(request: RememberRequest) -> dict:
    try:
        return memory.remember(request.kind, request.text, request.reason)
    except Exception as error:
        raise HTTPException(502, str(error)) from error


@app.get("/api/memory/journal")
def memory_journal(limit: int = 30) -> dict:
    return {"records": journal.tail("powercontext", limit)}


@app.get("/api/seekdb/journal")
def seekdb_journal(limit: int = 30) -> dict:
    return {"records": journal.tail("seekdb", limit)}


@app.post("/api/draft")
def draft(request: DraftRequest) -> dict:
    since = _to_int_date(request.since)
    until = _to_int_date(request.until)
    if since is None or until is None:
        raise HTTPException(422, "since/until 必须是 YYYY-MM-DD 或 YYYYMMDD")
    kb.open()
    result = build_draft(kb, memory, since=since, until=until, project=request.project or None,
                         size=request.size)
    journal.append("draft", {
        "action": "draft", "since": request.since, "until": request.until,
        "project": request.project, "preferences_applied": result.preferences_applied,
        "evidence_hits": len(result.evidence.get("hits", [])),
    })
    return {
        "markdown": result.markdown,
        "preferences_applied": result.preferences_applied,
        "memory_used": result.memory_used,
        "evidence": result.evidence,
    }


WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")


def main() -> None:
    import uvicorn

    kb.open()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
