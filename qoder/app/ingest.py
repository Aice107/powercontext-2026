"""把 markdown 语料解析成分块。front matter 提供结构化字段，正文按二级标题分块。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
KV = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
HEADING = re.compile(r"^##+\s+")
MAX_CHARS = 700


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    kind: str
    project: str
    tags: str
    doc_date: str
    section: str
    content: str
    embedding: list[float] = field(default_factory=list)

    @property
    def dd(self) -> int:
        return int(self.doc_date.replace("-", ""))

    @property
    def embed_text(self) -> str:
        """向量化的文本：标题与小节拼在正文前面（标题是该段最好的摘要）。"""
        return f"{self.title} · {self.section}\n{self.content}"

    def to_row(self) -> dict:
        row = self.__dict__.copy()
        row["dd"] = self.dd
        return row


def parse_document(text: str, *, fallback_name: str = "") -> dict:
    """解析 front matter 与正文，返回文档元数据 + 分块列表（不含向量）。"""
    meta: dict = {"title": fallback_name, "kind": "note", "project": "misc", "date": "", "tags": [], "origin": ""}
    body = text
    match = FRONT_MATTER.match(text)
    if match:
        body = text[match.end():]
        for line in match.group(1).splitlines():
            pair = KV.match(line.strip())
            if not pair:
                continue
            key, value = pair.group(1).lower(), pair.group(2).strip()
            if key == "tags":
                meta["tags"] = [t.strip() for t in re.split(r"[,\[\]]", value) if t.strip()]
            elif key in meta:
                meta[key] = value
    if not meta["title"] or meta["title"] == fallback_name:
        first_line = next((l.lstrip("# ").strip() for l in body.splitlines() if l.strip()), fallback_name)
        meta["title"] = first_line or fallback_name
    meta["date"] = meta.get("date") or "2026-01-01"
    doc_id = _stable_id(f"{meta['title']}|{meta['date']}")
    chunks: list[Chunk] = []
    current_section = "开头"
    buffer: list[str] = []

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if not content:
            return
        pieces = _split_long(content)
        for index, piece in enumerate(pieces):
            suffix = f"（{index + 1}/{len(pieces)}）" if len(pieces) > 1 else ""
            section = current_section + suffix
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}-{len(chunks):03d}",
                    doc_id=doc_id,
                    title=meta["title"],
                    kind=meta["kind"],
                    project=meta["project"],
                    tags=",".join(meta["tags"]),
                    doc_date=meta["date"],
                    section=section,
                    content=piece,
                )
            )
        buffer.clear()

    for line in body.splitlines():
        if HEADING.match(line):
            flush()
            current_section = HEADING.sub("", line).strip() or "小节"
        else:
            buffer.append(line)
    flush()
    return {"meta": meta, "doc_id": doc_id, "chunks": chunks}


def _split_long(content: str) -> list[str]:
    if len(content) <= MAX_CHARS:
        return [content]
    paragraphs = [p for p in re.split(r"\n\s*\n", content) if p.strip()]
    if len(paragraphs) <= 1:
        return [content[i:i + MAX_CHARS] for i in range(0, len(content), MAX_CHARS)]
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if size + len(paragraph) > MAX_CHARS and current:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def _stable_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
