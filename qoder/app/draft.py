"""组会草稿装配：seekdb 证据 + PowerContext 记忆 → markdown。

装配是确定性的：同样的语料、记忆和日期窗口，产出逐字节一致的草稿，
因此评审可以复现，并且能清楚看到"哪条记忆改变了输出的哪一段"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .memory import PowerContextMemory
from .seekdb_kb import KnowledgeBase

PREFERENCE_RULES = [
    ("结论先行", "summary_first", "检测到偏好「结论先行」：把摘要段放到最前面。"),
    ("先给数据", "data_first", "检测到偏好「先给数据」：关键数据段排到进展段之前。"),
    ("挂出处", "cite_sources", "检测到偏好「每个结论挂出处」：为每条内容标注来源。"),
    ("避免形容词", "strip_adverbs", "检测到偏好「避免形容词」：移除口语修饰词。"),
    ("提前一天", "early_submission", "检测到约束「组会材料提前一天发」：在抬头加提醒。"),
]

ADVERBS = re.compile(r"(非常|特别|十分|极其|相当|明显地|超级|真的|其实| basically)")


def _fmt(yyyymmdd: int) -> str:
    text = str(yyyymmdd)
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _fmt_range(since: int, until: int) -> str:
    return f"{_fmt(since)} ~ {_fmt(until)}"


@dataclass
class DraftResult:
    markdown: str
    preferences_applied: list[dict] = field(default_factory=list)
    memory_used: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def build_draft(
    kb: KnowledgeBase,
    memory: PowerContextMemory,
    *,
    since: int,
    until: int,
    project: str | None = None,
    size: int = 12,
) -> DraftResult:
    prefs_search = memory.search("写作偏好 汇报风格 输出格式", mode="hybrid", limit=6)
    constraint_search = memory.search("导师要求 约束 材料", mode="hybrid", limit=4)
    memory_used = [prefs_search, constraint_search]

    flags = _collect_flags(prefs_search["hits"] + constraint_search["hits"])
    applied = [{"rule": key, "note": note} for _keyword, key, note in PREFERENCE_RULES if getattr(flags, key)]

    window = kb.search(
        "实验 结果 数据",
        mode="hybrid",
        project=project,
        since=since,
        until=until,
        size=size,
        rank_constant=30,
    )
    plan_search = kb.search("待办 计划 下一步", mode="fts", size=6)

    experiments = [h for h in window.hits if h.get("kind") == "experiment"]
    meetings = [h for h in window.hits if h.get("kind") == "meeting"]
    references = [h for h in window.hits if h.get("kind") not in ("experiment", "meeting")]

    lines: list[str] = []
    title = f"# 组会汇报草稿（{_fmt(since)} ~ {_fmt(until)}）"
    if project:
        title += f" · 课题 {project}"
    lines.append(title)

    if flags.early_submission:
        lines += ["", "> 提醒：按组会惯例，本材料需提前一天发出。（来自 PowerContext 记忆约束）"]

    if flags.summary_first:
        lines += ["", "## 一句话结论", *summary_lines(experiments, flags)]

    if flags.data_first:
        lines += _data_section(experiments, flags)
        lines += _progress_section(experiments, flags)
    else:
        lines += _progress_section(experiments, flags)
        lines += _data_section(experiments, flags)

    lines += _meeting_section(meetings, flags)
    lines += _reference_section(references, flags)
    lines += _plan_section(plan_search.hits, flags)

    if not flags.summary_first:
        lines += ["", "## 一句话结论", *summary_lines(experiments, flags)]

    memory_briefs = [
        {"query": item["query"], "mode": item["mode"],
         "hits": [_memory_brief(h) for h in item["hits"]]}
        for item in memory_used
    ]
    lines += _appendix(window, memory_briefs, applied, since, until, project)
    return DraftResult(
        markdown="\n".join(lines),
        preferences_applied=applied,
        memory_used=memory_briefs,
        evidence=window.to_api(),
    )


@dataclass
class _Flags:
    summary_first: bool = False
    data_first: bool = False
    cite_sources: bool = False
    strip_adverbs: bool = False
    early_submission: bool = False


def _collect_flags(hits: list[dict]) -> _Flags:
    flags = _Flags()
    for hit in hits:
        text = _memory_text(hit)
        for keyword, attr, _note in PREFERENCE_RULES:
            if keyword in text:
                setattr(flags, attr, True)
    return flags


def _memory_text(hit: dict) -> str:
    for key in ("text", "content", "memory"):
        value = hit.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            inner = value.get("text") or value.get("content")
            if isinstance(inner, str):
                return inner
    return json_dumps(hit)


def _memory_brief(hit: dict) -> dict:
    inner = hit.get("memory") if isinstance(hit.get("memory"), dict) else {}
    text = _memory_text(hit)
    artifact = inner.get("artifact") or hit.get("artifact") or {}
    return {
        "id": artifact.get("artifact_id") or hit.get("id") or "",
        "text": text[:160],
        "kind": inner.get("kind") or hit.get("kind") or "",
        "score": hit.get("score"),
        "matched_by": hit.get("matched_by") or [],
    }


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _clean(text: str, flags: _Flags) -> str:
    text = " ".join(text.split())
    if flags.strip_adverbs:
        text = ADVERBS.sub("", text)
    return text.strip()


def _source(hit: dict) -> str:
    return f"〔{hit.get('title','?')} · {hit.get('section','?')} · {hit.get('doc_date','?')}〕"


def summary_lines(experiments: list[dict], flags: _Flags) -> list[str]:
    if not experiments:
        return ["（窗口内没有实验记录）"]
    headline = _clean(experiments[0].get("content", ""), flags).split("。")[0]
    return [f"{headline}。", f"共整理 {len(experiments)} 条实验记录。"]


def _progress_section(experiments: list[dict], flags: _Flags) -> list[str]:
    lines = ["", "## 本周进展"]
    if not experiments:
        lines.append("（窗口内没有实验记录）")
        return lines
    for hit in experiments:
        text = _clean(hit.get("content", ""), flags)
        first_sentence = text.split("。")[0] if text else ""
        body = f"- {first_sentence}。"
        if flags.cite_sources:
            body += f" {_source(hit)}"
        lines.append(body)
    return lines


NUMBER_LINE = re.compile(r"(\d+\.?\d*\s*(ms|MB|GB|%|个点|x)|Recall@\d+|MRR|P95)")


def _data_section(experiments: list[dict], flags: _Flags) -> list[str]:
    lines = ["", "## 关键数据"]
    count = 0
    for hit in experiments:
        for raw in hit.get("content", "").splitlines():
            line = raw.strip().lstrip("-| ").strip()
            if line.startswith("#") or not line:
                continue
            if NUMBER_LINE.search(line):
                lines.append(f"- {line}" + (f" {_source(hit)}" if flags.cite_sources else ""))
                count += 1
            if count >= 8:
                break
        if count >= 8:
            break
    if count == 0:
        lines.append("（窗口内没有数值型记录）")
    return lines


def _meeting_section(meetings: list[dict], flags: _Flags) -> list[str]:
    if not meetings:
        return []
    lines = ["", "## 会议与导师意见"]
    for hit in meetings:
        for raw in hit.get("content", "").splitlines():
            line = raw.strip()
            if line.startswith(("-", "1", "2", "3", "4")) and len(line) > 4:
                lines.append(f"- {_clean(line.lstrip('-0123456789.、 '), flags)}" + (f" {_source(hit)}" if flags.cite_sources else ""))
    return lines[:10]


def _reference_section(references: list[dict], flags: _Flags) -> list[str]:
    if not references:
        return []
    lines = ["", "## 相关依据（论文与笔记）"]
    for hit in references[:4]:
        snippet = _clean(hit.get("snippet", ""), flags)
        lines.append(f"- {snippet}…" + (f" {_source(hit)}" if flags.cite_sources else ""))
    return lines


def _plan_section(plan_hits: list[dict], flags: _Flags) -> list[str]:
    lines = ["", "## 下周计划"]
    count = 0
    for hit in plan_hits:
        if hit.get("kind") != "todo":
            continue
        for raw in hit.get("content", "").splitlines():
            line = raw.strip().lstrip("- ")
            if line.startswith(("#", "##", "进行", "待开", "已完")) or not line:
                continue
            lines.append(f"- {_clean(line, flags)}" + (f" {_source(hit)}" if flags.cite_sources else ""))
            count += 1
    if count == 0:
        lines.append("（没有待办记录）")
    return lines


def _appendix(
    outcome,
    memory_used: list[dict],
    applied: list[dict],
    since: int,
    until: int,
    project: str | None,
) -> list[str]:
    lines = [
        "",
        "---",
        "## 附录：本次草稿的证据链",
        "",
        f"- 时间窗口：{_fmt_range(since, until)}" + (f"，课题过滤：{project}" if project else ""),
        f"- seekdb 混合检索：命中 {len(outcome.hits)} 条，耗时 {outcome.elapsed_ms:.1f} ms，模式 {outcome.mode}",
        f"- PowerContext 记忆调用：{sum(len(item['hits']) for item in memory_used)} 条命中",
    ]
    if applied:
        lines += ["- 本次因记忆改变的输出："]
        lines += [f"  - {item['note']}" for item in applied]
    else:
        lines += ["- 本次没有命中的记忆偏好：按默认版式输出（可用「记住偏好」后重试对比）。"]
    lines += ["", "### PowerContext 命中的记忆"]
    for item in memory_used:
        lines.append(f"- 查询「{item['query']}」({item['mode']})：")
        for brief in item["hits"]:
            lines.append(f"  - [{brief['kind'] or 'memory'}] {brief['text']}")
    lines += ["", "### 检索语句（seekdb 取证）", "", "```sql", outcome.sql, "```"]
    return lines
