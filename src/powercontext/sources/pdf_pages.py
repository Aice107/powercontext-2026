# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ruff: noqa: TRY003, TRY301 - inline messages are the documented offline input contract.

"""Page-level Captured Sources for complete offline PDF documents.

Every physical PDF page becomes one immutable ``pdf-page`` Source.  The Source
identity includes the document id, the SHA-256 of the complete input bytes and
the physical page number, so a revised PDF gets new identities while old
citations keep pointing at the revision they were captured from.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote

from pydantic import BaseModel, JsonValue
from pypdf import PdfReader

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

if TYPE_CHECKING:
    from powercontext.builtin.artifacts.memory.models import MemoryCitation

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"

_TOKEN_RE = re.compile(r"[a-z]+|\d+")
_STOPWORDS = frozenset({
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "give",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "much",
    "many",
    "not",
    "of",
    "on",
    "or",
    "please",
    "respond",
    "shall",
    "should",
    "show",
    "shown",
    "state",
    "stated",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "those",
    "to",
    "under",
    "use",
    "using",
    "value",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "within",
    "would",
    "answer",
    "question",
    "report",
    "reported",
    "reports",
    "fiscal",
    "year",
    "usd",
    "dollar",
    "dollars",
    "million",
    "millions",
    "billion",
    "billions",
    "amount",
    "quantity",
    "explicitly",
    "outlined",
    "assume",
    "assuming",
    "perspective",
    "details",
    "detail",
    "statement",
    "statements",
})
_SYNONYMS = {
    "legal": {
        "proceedings": 0.9,
        "litigation": 0.8,
        "claims": 0.6,
        "contingencies": 0.6,
        "regulatory": 0.5,
        "investigations": 0.5,
        "inquiries": 0.5,
    },
    "battles": {"disputes": 0.7, "litigation": 0.7, "proceedings": 0.7, "claims": 0.5},
    "geographies": {
        "geographic": 0.9,
        "regions": 0.7,
        "countries": 0.8,
        "territories": 0.7,
        "markets": 0.5,
        "segments": 0.5,
        "operations": 0.5,
    },
    "geography": {"geographic": 0.9, "regions": 0.7, "countries": 0.8, "territories": 0.7},
    "restructuring": {"charges": 0.7, "impairment": 0.6, "productivity": 0.5, "severance": 0.6},
    "ebitda": {
        "operating": 0.4,
        "income": 0.4,
        "profit": 0.4,
        "depreciation": 0.7,
        "amortization": 0.7,
        "earnings": 0.4,
    },
    "capex": {"capital": 0.7, "expenditures": 0.9, "purchases": 0.7, "property": 0.5, "plant": 0.4, "equipment": 0.4},
    "margin": {"operating": 0.4, "income": 0.4, "profit": 0.4},
    "costs": {"cost": 0.7, "expenses": 0.6, "charges": 0.6},
    "cost": {"costs": 0.6, "expenses": 0.5},
    "revenue": {"revenues": 0.7, "sales": 0.6},
    "cash": {"flows": 0.6, "flow": 0.6},
    "income": {"profit": 0.6, "earnings": 0.5},
    "profit": {"income": 0.5},
    "quick": {
        "current": 0.7,
        "assets": 0.5,
        "inventories": 0.8,
        "inventory": 0.7,
        "liabilities": 0.6,
        "receivables": 0.5,
    },
    "ratio": {"current": 0.3, "assets": 0.3, "liabilities": 0.3, "inventories": 0.3},
    "inventory": {"inventories": 0.8, "cost": 0.4, "sales": 0.4},
    "turnover": {"inventories": 0.6, "cost": 0.5, "sales": 0.5},
    "gross": {"profit": 0.7, "margin": 0.5, "sales": 0.4},
    "capital": {"expenditures": 0.7, "property": 0.4, "plant": 0.4, "equipment": 0.4},
    "intensive": {"expenditures": 0.5, "property": 0.4, "depreciation": 0.3},
    "segment": {"segments": 0.7, "divisions": 0.5, "businesses": 0.4},
    "growth": {"organic": 0.5, "sales": 0.3, "volume": 0.3, "increase": 0.3},
    "acquisition": {"acquisitions": 0.6, "merger": 0.6, "mergers": 0.6, "divestitures": 0.5},
}


class PDFDocumentInput(BaseModel):
    """A complete offline PDF document to split into page Sources."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """Adapter-native value for one physical PDF page."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """Captured PDF page retained as evidence independent of the parsed view."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of one PDF, or fail without partial pages."""

    document_id = _validate_document_id(value.document_id)
    content = value.content
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError("PDF content must be non-empty bytes")

    digest = hashlib.sha256(bytes(content)).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(bytes(content)))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ValueError("PDF requires a non-empty user password")
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("PDF document must contain at least one physical page")
        pages: list[PDFPageInput] = []
        for index in range(page_count):
            text = reader.pages[index].extract_text() or ""
            pages.append(
                PDFPageInput(
                    document_id=document_id,
                    document_sha256=digest,
                    page_number=index + 1,
                    text=text,
                )
            )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF document could not be fully parsed") from error
    return tuple(pages)


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Return the stable, collision-free identity of one PDF page."""

    document_id = _validate_document_id(document_id)
    digest = _validate_digest(document_sha256)
    page = _validate_page_number(page_number)
    identity = f"pdf:{quote(document_id, safe='')}:{digest}:{page}"
    if len(identity) <= MAX_SOURCE_ID_LENGTH:
        return identity
    # Identity still depends only on the three raw components; a digest keeps
    # very long provider document ids inside the Source identity limit.
    fallback = hashlib.sha256(f"{document_id}\x00{digest}\x00{page}".encode()).hexdigest()
    return f"pdf:sha256:{fallback}"


class PDFPageAdapter:
    """Resolve one parsed page into its Captured Source and read it back."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one page as ``DOCUMENT_ID`` plus the extracted page text."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        metadata: dict[str, JsonValue] = {
            "document_id": source.document_id,
            "document_sha256": source.document_sha256,
            "page_number": source.page_number,
        }
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata=metadata,
        )


PDF_PAGE_SOURCE_ADAPTER = PDFPageAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    version=PDF_PAGE_SOURCE_VERSION,
    projections=(PDFPageTextEvidenceProjection(),),
)


@dataclass(frozen=True)
class _PageCandidate:
    """One current page entry prepared for local lexical reranking."""

    citation: Any
    source_id: str
    document_key: str
    page_number: int | None
    tokens: tuple[str, ...]
    heading: frozenset[str]


async def search_pdf_pages(  # noqa: C901 - explicit retrieval stages
    memory: Any,
    question: str,
    limit: int = 10,
) -> tuple[MemoryCitation, ...]:
    """Return up to ``limit`` distinct exact page citations for one question.

    The current scoped Memory entries are read through the public list API and
    reranked locally.  Retrieval uses BM25 over the complete page corpus, a
    generic finance/legal vocabulary expansion, heading and proximity boosts,
    and a structure prior that promotes the financial statement named by the
    question.  Every returned citation is an exact current-head citation.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("PDF page search limit must be a positive integer")
    if not isinstance(question, str) or not question.strip():
        return ()

    page = await memory.list()
    candidates = _page_candidates(page.entries)
    if not candidates:
        return ()

    scoped = _scope_documents(question, candidates)
    if scoped is not None:
        candidates = [candidate for candidate in candidates if candidate.document_key in scoped]
        if not candidates:
            return ()

    terms = _content_terms(question)
    raw_question = question.lower()
    if "m&a" in raw_question or "m & a" in raw_question or "mergers and acquisitions" in raw_question:
        terms = [*terms, "acquisitions", "mergers", "divestitures"]
    weights = _query_weights(terms)
    scores = _score_candidates(terms, weights, candidates)
    kinds = _statement_kinds(question)
    forced: list[tuple[float, _PageCandidate]] = []
    remaining: list[tuple[float, _PageCandidate]] = []
    for score, candidate in zip(scores, candidates, strict=True):
        matches = kinds and any(_heading_matches(kind, candidate.heading) for kind in kinds)
        (forced if matches else remaining).append((score, candidate))
    forced.sort(key=lambda item: (-item[0], item[1].source_id))
    remaining.sort(key=lambda item: (-item[0], item[1].source_id))

    results: list[MemoryCitation] = []
    seen_pages: set[str] = set()
    for _, candidate in (*forced, *remaining):
        if candidate.source_id in seen_pages:
            continue
        seen_pages.add(candidate.source_id)
        results.append(candidate.citation)
        if len(results) >= limit:
            break
    return tuple(results)


def _page_candidates(records: Any) -> list[_PageCandidate]:
    candidates: list[_PageCandidate] = []
    for record in records:
        source_ids = tuple(
            reference.source_id
            for reference in record.entry.sources
            if reference.source_type == PDF_PAGE_SOURCE_NAME or reference.source_id.startswith("pdf:")
        )
        if not source_ids:
            continue
        body = _page_body(record.entry.text)
        tokens = tuple(_TOKEN_RE.findall(_strip_table_of_contents(body).lower()))
        if not tokens:
            # A blank page's stored text is only the document id.
            continue
        document_key, page_number = _split_source_id(source_ids[0])
        candidates.append(
            _PageCandidate(
                citation=record.citation,
                source_id=source_ids[0],
                document_key=document_key,
                page_number=page_number,
                tokens=tokens,
                heading=frozenset(tokens[:15]),
            )
        )
    return candidates


def _split_source_id(source_id: str) -> tuple[str, int | None]:
    prefix, _, remainder = source_id.partition(":")
    if prefix != "pdf" or not remainder:
        return source_id, None
    parts = remainder.split(":")
    if len(parts) == 3 and parts[2].isdigit():
        return unquote(parts[0]), int(parts[2])
    return source_id, None


def _document_name_candidates(document_id: str) -> frozenset[str]:
    normalized_prefix = re.sub(r"[^a-z0-9]+", "", document_id.split("_")[0].lower())
    parts = [re.sub(r"[^a-z0-9]+", "", part.lower()) for part in document_id.split("_")[:-2]]
    candidates = {normalized_prefix}
    if len(parts) >= 2:
        candidates.add("n".join(part[0] for part in parts if part))
    return frozenset(
        candidate
        for candidate in candidates
        if candidate and (len(candidate) >= 3 or any(character.isdigit() for character in candidate))
    )


def _scope_documents(question: str, candidates: list[_PageCandidate]) -> set[str] | None:
    flattened = re.sub(r"[^a-z0-9]+", "", question.lower())
    matched = {
        candidate.document_key
        for candidate in candidates
        if candidate.document_key != candidate.source_id
        and any(name in flattened for name in _document_name_candidates(candidate.document_key))
    }
    return matched if len(matched) == 1 else None


def _page_body(text: str) -> str:
    _, separator, body = text.partition("\n")
    return body if separator else ""


def _strip_table_of_contents(text: str) -> str:
    stripped = text
    while stripped.lower().startswith("table of contents"):
        stripped = stripped[len("table of contents") :]
    return stripped


def _query_weights(terms: list[str]) -> Counter[str]:
    weights: Counter[str] = Counter()
    for term in terms:
        weights[term] = max(weights[term], 1.0)
    for term in set(terms):
        for expanded, weight in _SYNONYMS.get(term, {}).items():
            weights[expanded] = max(weights[expanded], weight)
    return weights


def _score_candidates(  # noqa: C901 - one explicit lexical scoring pass
    terms: list[str],
    weights: Counter[str],
    candidates: list[_PageCandidate],
) -> list[float]:
    if not terms or not candidates:
        return [0.0 for _ in candidates]

    token_frequencies: list[Counter[str]] = []
    lengths: list[int] = []
    document_frequency: Counter[str] = Counter()
    for candidate in candidates:
        frequencies = Counter(candidate.tokens)
        token_frequencies.append(frequencies)
        lengths.append(len(candidate.tokens))
        for term in weights:
            if term in frequencies:
                document_frequency[term] += 1

    total = len(candidates)
    average_length = sum(lengths) / total if total else 0.0
    idf = {
        term: math.log(1.0 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
        for term in weights
    }

    positions: list[dict[str, list[int]]] = []
    for candidate in candidates:
        index: defaultdict[str, list[int]] = defaultdict(list)
        for offset, token in enumerate(candidate.tokens):
            if token in weights:
                index[token].append(offset)
        positions.append(index)

    bigrams = [
        (first, second)
        for first, second in itertools.pairwise(terms)
        if first not in _STOPWORDS and second not in _STOPWORDS
    ]
    numbers = {term for term in terms if term.isdigit()}

    scores: list[float] = []
    for frequencies, length, index, candidate in zip(token_frequencies, lengths, positions, candidates, strict=True):
        score = 0.0
        for term, weight in weights.items():
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            normalization = 1.2 * (1.0 - 0.75 + 0.75 * (length / average_length if average_length else 0.0))
            score += weight * idf[term] * (frequency * 2.2) / (frequency + normalization)
        for term, weight in weights.items():
            if term in candidate.heading:
                score += 0.8 * weight * idf[term]
        for first, second in bigrams:
            if _near(index.get(first, ()), index.get(second, ()), 4):
                score += 0.6 * (idf.get(first, 0.0) + idf.get(second, 0.0))
        for number in numbers:
            if number in frequencies:
                score += 0.2 * idf.get(number, 0.0)
        scores.append(score)
    return scores


def _near(first: Sequence[int], second: Sequence[int], window: int) -> bool:
    left = right = 0
    while left < len(first) and right < len(second):
        if abs(first[left] - second[right]) <= window:
            return True
        if first[left] < second[right]:
            left += 1
        else:
            right += 1
    return False


def _has(values: frozenset[str] | set[str], *words: str) -> bool:
    return any(word in values for word in words)


def _statement_kinds(question: str) -> frozenset[str]:
    terms = set(_TOKEN_RE.findall(question.lower()))
    raw = question.lower()
    kinds: set[str] = set()
    if (
        {"income", "statement"} <= terms
        or {"income", "statements"} <= terms
        or "p&l" in raw
        or "p & l" in raw
        or "profit and loss" in raw
        or (_has(terms, "income", "earnings") and _has(terms, "statement", "statements"))
    ):
        kinds.add("income")
    if (_has(terms, "cash") and _has(terms, "flow", "flows") and _has(terms, "statement", "statements")) or (
        "cash flow" in raw and "statement" in raw
    ):
        kinds.add("cash")
    if _has(terms, "balance") and _has(terms, "sheet", "sheets"):
        kinds.add("balance")
    metric = (
        _has(terms, "margin", "margins")
        or _has(terms, "gross")
        or _has(terms, "ebitda")
        or (_has(terms, "operating") and _has(terms, "income", "profit"))
        or (_has(terms, "net") and _has(terms, "income"))
    )
    if metric:
        kinds.update({"income", "mdna"})
    if _has(terms, "inventory", "inventories") and _has(terms, "turnover"):
        kinds.update({"balance", "income"})
    if _has(terms, "quick") and _has(terms, "ratio"):
        kinds.update({"balance", "income"})
    if _has(terms, "capital") and _has(terms, "intensive"):
        kinds.update({"income", "balance", "cash"})
    if (
        _has(terms, "capex")
        or (_has(terms, "capital") and _has(terms, "expenditures"))
        or (_has(terms, "cash") and _has(terms, "flow", "flows"))
    ):
        kinds.add("cash")
    return frozenset(kinds)


def _heading_matches(kind: str, heading: frozenset[str]) -> bool:
    statement = _has(heading, "statement", "statements")
    if kind == "income":
        return statement and _has(heading, "income", "earnings", "operations")
    if kind == "cash":
        return statement and "cash" in heading and _has(heading, "flow", "flows")
    if kind == "balance":
        return ("balance" in heading and _has(heading, "sheet", "sheets")) or {
            "statement",
            "financial",
            "position",
        } <= heading
    if kind == "mdna":
        return (_has(heading, "analysis") and _has(heading, "earnings", "income")) or (
            _has(heading, "results") and _has(heading, "operations")
        )
    return False


def _content_terms(value: str) -> list[str]:
    return [term for term in _TOKEN_RE.findall(value.lower()) if term not in _STOPWORDS]


def _validate_document_id(document_id: str) -> str:
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("PDF document_id must be a non-empty string")
    return document_id


def _validate_digest(document_sha256: str) -> str:
    if (
        not isinstance(document_sha256, str)
        or len(document_sha256) != 64
        or any(character not in "0123456789abcdef" for character in document_sha256)
    ):
        raise ValueError("PDF document_sha256 must be a lowercase hexadecimal SHA-256")
    return document_sha256


def _validate_page_number(page_number: int) -> int:
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
        raise ValueError("PDF page_number must be a positive integer")
    return page_number
