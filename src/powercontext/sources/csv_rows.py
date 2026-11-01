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

# ruff: noqa: TRY003 - inline messages are the documented offline input contract.

"""Row-level Captured Sources for offline CSV documents.

Every data row becomes one immutable ``csv-row`` Source identified by its
document id and primary key value.  The standard ``powercontext.text-evidence``
projection serializes the row as a JSON object that preserves the original
column order and every original field value.
"""

from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
CSV_ROW_SOURCE_VERSION = "1"


class CSVDocumentInput(BaseModel):
    """A complete offline CSV document to split into row Sources."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """Adapter-native value for one CSV data row."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """Captured CSV row retained as evidence independent of file ordering."""

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Parse and validate a whole CSV document before returning any row.

    Records become visible only after the header, every data record and every
    primary key have been validated, so an invalid document never yields a
    partial result.
    """

    document_id = _validate_document_id(value.document_id)
    primary_key = _validate_primary_key(value.primary_key)
    text = _decode_document(value.content)
    records = _read_records(text)
    columns = _parse_header(records)
    primary_key_index = _primary_key_index(columns, primary_key)
    return tuple(_parse_rows(records, columns, primary_key, primary_key_index, document_id))


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Return the stable, delimiter-safe identity of one CSV row."""

    document_id = _validate_document_id(document_id)
    if not isinstance(primary_key_value, str) or not primary_key_value.strip():
        raise ValueError("CSV primary key value must be a non-empty string")
    identity = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"CSV row Source identity must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return identity


class CSVRowAdapter:
    """Resolve one parsed row into its Captured Source and read it back."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=tuple(value.columns),
            values=tuple(value.values),
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=tuple(source.columns),
            values=tuple(source.values),
        )


class CSVRowTextEvidenceProjection:
    """Expose one row as the canonical text evidence object."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        content = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        metadata: dict[str, JsonValue] = {
            "document_id": source.document_id,
            "primary_key": source.primary_key,
            "primary_key_value": source.primary_key_value,
            "columns": list(source.columns),
            "row": row,
        }
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=content,
            metadata=metadata,
        )


CSV_ROW_SOURCE_ADAPTER = CSVRowAdapter()
CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    version=CSV_ROW_SOURCE_VERSION,
    projections=(CSVRowTextEvidenceProjection(),),
)


def _validate_document_id(document_id: str) -> str:
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("CSV document_id must be a non-empty string")
    if document_id != document_id.strip():
        raise ValueError("CSV document_id must not contain leading or trailing whitespace")
    return document_id


def _validate_primary_key(primary_key: str) -> str:
    if not isinstance(primary_key, str) or not primary_key:
        raise ValueError("CSV primary_key must be a non-empty string")
    return primary_key


def _decode_document(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV content must be strict UTF-8") from error


def _read_records(text: str) -> list[list[str]]:
    try:
        return list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise ValueError("CSV content contains malformed quoting") from error


def _parse_header(records: list[list[str]]) -> tuple[str, ...]:
    if not records or not records[0]:
        raise ValueError("CSV document must declare a non-empty header record")
    columns = tuple(records[0])
    if len(set(columns)) != len(columns):
        raise ValueError("CSV header column names must be unique")
    for column in columns:
        if not column or not column.strip():
            raise ValueError("CSV header column names must be non-empty and must not be whitespace")
    return columns


def _primary_key_index(columns: tuple[str, ...], primary_key: str) -> int:
    try:
        return columns.index(primary_key)
    except ValueError:
        raise ValueError(f"CSV primary_key {primary_key!r} does not match any header column") from None


def _parse_rows(
    records: list[list[str]],
    columns: tuple[str, ...],
    primary_key: str,
    primary_key_index: int,
    document_id: str,
) -> list[CSVRowInput]:
    rows: list[CSVRowInput] = []
    seen_primary_key_values: set[str] = set()
    for record in records[1:]:
        if not record:
            # Completely empty physical records carry no fields and are ignored.
            continue
        if len(record) != len(columns):
            raise ValueError(f"CSV data record has {len(record)} fields but the header declares {len(columns)}")
        values = tuple(record)
        primary_key_value = values[primary_key_index]
        if not primary_key_value.strip():
            raise ValueError("CSV primary key value must not be empty or whitespace")
        if primary_key_value in seen_primary_key_values:
            raise ValueError(f"CSV primary key value {primary_key_value!r} is duplicated")
        seen_primary_key_values.add(primary_key_value)
        # Validate identity while parsing so an unbounded row fails atomically.
        csv_row_source_id(document_id, primary_key_value)
        rows.append(
            CSVRowInput(
                document_id=document_id,
                primary_key=primary_key,
                primary_key_value=primary_key_value,
                columns=columns,
                values=values,
            )
        )
    return rows
