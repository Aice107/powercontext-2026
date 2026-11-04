"""Tokenisation and query expansion for Chinese/English engineering text."""

from __future__ import annotations

import re
import unicodedata

ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "must", "not", "of", "on", "or",
    "that", "the", "their", "then", "this", "to", "was", "were", "will", "with",
    "的", "了", "和", "与", "及", "或", "在", "对", "把", "被", "这", "那", "个",
    "一个", "需要", "可以", "必须", "以及", "进行",
}

# Chinese phrase -> canonical English engineering term(s).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "筛选": ("filter",),
    "过滤": ("filter",),
    "筛选条件": ("filter",),
    "截止": ("due",),
    "截止日期": ("due", "date", "due_date"),
    "日期": ("date",),
    "上界": ("upper", "before"),
    "边界": ("boundary",),
    "任务": ("task",),
    "列表": ("list",),
    "分页": ("pagination", "limit", "offset"),
    "状态": ("status",),
    "优先": ("priority",),
    "优先级": ("priority",),
    "回归": ("regression",),
    "测试": ("test",),
    "规格": ("spec",),
    "规格条目": ("spec",),
    "非法": ("invalid",),
    "包含": ("inclusive", "include"),
    "当天": ("inclusive", "day"),
    "闭区间": ("inclusive",),
    "排除": ("exclude",),
    "校验": ("validation",),
    "错误": ("error",),
    "接口": ("api", "endpoint"),
    "空": ("empty",),
    "组合": ("combine",),
    "既有": ("existing", "regression"),
    "修复": ("fix",),
    "增加": ("add",),
}

ASCII_SYNONYMS: dict[str, tuple[str, ...]] = {
    "filters": ("filter",),
    "filtering": ("filter",),
    "tests": ("test",),
    "testing": ("test",),
    "specs": ("spec",),
    "specification": ("spec",),
    "specifications": ("spec",),
    "fixed": ("fix",),
    "fixes": ("fix",),
    "dates": ("date",),
    "tasks": ("task",),
    "lists": ("list",),
    "listed": ("list",),
    "inclusive": ("inclusive", "include"),
    "upper_bound": ("upper", "before"),
}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def tokenize(text: str) -> list[str]:
    """Return stable tokens: ASCII identifiers (split on _/camel) + CJK bigrams."""

    text = normalize(text)
    tokens: list[str] = []

    for match in ASCII_RE.finditer(text):
        raw = match.group(0)
        lowered = raw.lower()
        if len(lowered) >= 2 and lowered not in STOPWORDS:
            tokens.append(lowered)
        for part in re.split(r"[_\W]+", lowered):
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.append(part)
        for part in CAMEL_RE.findall(raw):
            part = part.lower()
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.append(part)

    for match in CJK_RE.finditer(text):
        phrase = match.group(0)
        if len(phrase) == 1:
            tokens.append(phrase)
            continue
        for index in range(len(phrase) - 1):
            tokens.append(phrase[index : index + 2])
        # Keep longer domain phrases that the bigram window alone would miss.
        for phrase_term in SYNONYMS:
            if len(phrase_term) >= 2 and phrase_term in phrase:
                tokens.append(phrase_term)

    # de-duplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def expand_terms(tokens: list[str]) -> list[str]:
    """Add canonical English synonyms without dropping the original tokens."""

    expanded: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        if term and term not in seen:
            seen.add(term)
            expanded.append(term)

    for token in tokens:
        add(token)
        for synonym in SYNONYMS.get(token, ()):
            add(synonym)
        for synonym in ASCII_SYNONYMS.get(token, ()):
            add(synonym)
        # crude English plural normalisation
        if token.endswith("s") and len(token) > 4:
            add(token[:-1])
    return expanded


def query_terms(text: str) -> list[str]:
    return expand_terms(tokenize(text))


def index_terms(text: str) -> list[str]:
    return expand_terms(tokenize(text))
