"""SQL 字面量转义与语料分块的单元测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import parse_document
from app.sql_literal import sql_ident, sql_str


def test_sql_str_roundtrip_quotes_and_backslashes():
    nasty = "他说：'混合检索' \\ 好用\n第二行\t带\"引号\"结束\x1a"
    literal = sql_str(nasty)
    assert literal.startswith("'") and literal.endswith("'")
    # 单引号与反斜杠都必须被转义，不能出现裸引号截断
    inner = literal[1:-1]
    assert "\\'" in inner
    assert "\\\\" in inner
    assert "\\n" in inner
    assert "\\t" in inner
    assert "\\Z" in inner


def test_sql_str_none_bool_numbers():
    assert sql_str(None) == "NULL"
    assert sql_str(True) == "TRUE"
    assert sql_str(3) == "3"
    assert sql_str(0.5) == "0.5"


def test_sql_ident_rejects_injection():
    assert sql_ident("chunks") == "`chunks`"
    for bad in ["chunks; drop table x", "ch`unks", ""]:
        try:
            sql_ident(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad!r}")


SAMPLE = """---
title: 测试文档
kind: experiment
project: vec-search
date: 2026-10-30
tags: [a, b]
---

开头段。

## 设置

设置内容，数字 0.93。

## 结论

结论内容。


超长内容分块前的最后一段。
"""


def test_parse_document_front_matter_and_chunks():
    doc = parse_document(SAMPLE, fallback_name="f.md")
    meta = doc["meta"]
    assert meta["title"] == "测试文档"
    assert meta["kind"] == "experiment"
    assert meta["project"] == "vec-search"
    assert meta["date"] == "2026-10-30"
    assert meta["tags"] == ["a", "b"]
    assert len(doc["chunks"]) == 3
    sections = [c.section for c in doc["chunks"]]
    assert sections[0] == "开头"
    assert "设置" in sections[1]
    # 正文不含「标题 · 小节」前缀
    assert doc["chunks"][1].content.startswith("设置内容")
    # 向量化文本带标题前缀
    assert doc["chunks"][1].embed_text.startswith("测试文档 · 设置")
    assert doc["chunks"][0].dd == 20261030


def test_parse_document_without_front_matter():
    doc = parse_document("## 小节\n正文", fallback_name="g.md")
    assert doc["meta"]["kind"] == "note"
    assert doc["chunks"][0].section == "小节"
