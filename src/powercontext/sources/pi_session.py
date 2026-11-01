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

# ruff: noqa: TRY003, TRY004 - inline ValueError is the documented offline input contract.

"""Capture the raw visible history of one selected Pi session branch.

Pi stores a session as a JSONL tree in which every record names its parent.
``parse_pi_session`` walks the ancestors of one selected leaf and turns every
visible record into an immutable ``pi-event`` Source.  The connector keeps an
opaque, durable checkpoint so repeated runs import only new events while
refusing to replace evidence that was already captured.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    ConnectorSubmissionStatus,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_EVENT_SOURCE_VERSION = "1"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
PI_SESSION_CONNECTOR_VERSION = "1"
PI_SESSION_VERSION = 3

_CHECKPOINT_VERSION = 1


class PiSessionInput(BaseModel):
    """A complete Pi JSONL session archive and the branch leaf to capture."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """Adapter-native value for one visible event on the selected branch."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    """Captured Pi event retained exactly as it appeared in the archive."""

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Return every visible event on the selected leaf's ancestor chain."""

    session_id, nodes, parents, order = _parse_archive(value.content)
    leaf_id = _select_leaf(value.leaf_id, nodes, order)
    if leaf_id is None:
        return ()

    chain: list[str] = []
    cursor: str | None = leaf_id
    while cursor is not None and cursor != session_id:
        chain.append(cursor)
        cursor = parents[cursor]
    chain.reverse()

    events: list[PiEventInput] = []
    for event_id in chain:
        event = _build_event(session_id, nodes[event_id])
        if event is not None:
            events.append(event)
    return tuple(events)


def pi_event_source_id(session_id: str, event_id: str) -> str:
    """Return a stable, collision-free identity for one session event."""

    for field, component in (("session_id", session_id), ("event_id", event_id)):
        if not isinstance(component, str) or not component:
            raise ValueError(f"Pi {field} must be a non-empty string")
    identity = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(identity) <= MAX_SOURCE_ID_LENGTH:
        return identity
    # Identity is still derived only from the two raw components, but a digest
    # keeps arbitrarily long provider ids inside the Source identity limit.
    digest = hashlib.sha256(f"{session_id}\x00{event_id}".encode()).hexdigest()
    return f"pi:sha256:{digest}"


class PiEventAdapter:
    """Resolve one parsed event into its Captured Source and read it back."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = pi_event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=dict(value.record),
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=dict(source.record),
        )


class PiEventTextEvidenceProjection:
    """Expose the full event text with the identity fields as metadata."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        metadata: dict[str, JsonValue] = {
            "session_id": source.session_id,
            "event_id": source.event_id,
            "parent_id": source.parent_id,
            "event_type": source.event_type,
            "role": source.role,
        }
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata=metadata,
        )


PI_EVENT_SOURCE_ADAPTER = PiEventAdapter()
PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PI_EVENT_SOURCE_ADAPTER,
    version=PI_EVENT_SOURCE_VERSION,
    projections=(PiEventTextEvidenceProjection(),),
)


class PiSessionConnector:
    """Import only not-yet-captured visible events from one Pi session file."""

    name = PI_SESSION_CONNECTOR_NAME
    version = PI_SESSION_CONNECTOR_VERSION
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        content = self._path.read_bytes()
        # Parse and validate the whole archive before submitting any item.
        events = parse_pi_session(PiSessionInput(content=content, leaf_id=self._leaf_id))
        captured = _load_checkpoint(session.checkpoint)

        digests = {_event_key(event): _record_digest(event) for event in events}
        for event in events:
            key = _event_key(event)
            previous = captured.get(key)
            if previous is not None and previous != digests[key]:
                raise ValueError(
                    f"Pi event {event.event_id!r} of session {event.session_id!r} was rewritten after capture"
                )

        imported = dict(captured)
        for event in events:
            key = _event_key(event)
            if key in imported:
                continue
            outcome = await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            if outcome.status is not ConnectorSubmissionStatus.ACCEPTED:
                raise ValueError(f"Pi event {event.event_id!r} could not be captured: {outcome.detail}")
            imported[key] = digests[key]

        checkpoint: dict[str, JsonValue] = {
            "version": _CHECKPOINT_VERSION,
            "events": [
                {"session_id": session_id, "event_id": event_id, "digest": digest}
                for (session_id, event_id), digest in sorted(imported.items())
            ],
        }
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint=checkpoint)


def _parse_archive(  # noqa: C901 - explicit JSONL and graph validation stages
    content: bytes,
) -> tuple[str, dict[str, dict[str, JsonValue]], dict[str, str | None], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except (UnicodeDecodeError, AttributeError) as error:
        raise ValueError("Pi session content must be strict UTF-8") from error

    records: list[dict[str, JsonValue]] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("Pi session content is not valid JSONL") from error
        if not isinstance(record, dict):
            raise ValueError("Pi session records must be JSON objects")
        records.append(record)

    if not records:
        raise ValueError("Pi session archive must start with a session record")
    header = records[0]
    if header.get("type") != "session":
        raise ValueError("Pi session archive must start with a type=session record")
    version = header.get("version")
    if type(version) is not int or version != PI_SESSION_VERSION:
        raise ValueError(f"Pi session version must be {PI_SESSION_VERSION}")
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Pi session record must declare a non-empty string id")

    nodes: dict[str, dict[str, JsonValue]] = {}
    parents: dict[str, str | None] = {}
    order: list[str] = []
    seen = {session_id}
    for record in records[1:]:
        event_type = record.get("type")
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("Pi session records must declare a non-empty string type")
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Pi session records must declare a non-empty string id")
        if event_id in seen:
            raise ValueError(f"Pi session event id {event_id!r} is duplicated")
        if "parentId" not in record:
            raise ValueError(f"Pi session event {event_id!r} is missing parentId")
        parent_id = record["parentId"]
        if parent_id is not None and not isinstance(parent_id, str):
            raise ValueError(f"Pi session event {event_id!r} has an invalid parentId")
        if parent_id == event_id:
            raise ValueError(f"Pi session event {event_id!r} cannot be its own parent")
        if parent_id not in (None, "") and parent_id not in seen:
            raise ValueError(f"Pi session event {event_id!r} references missing parent {parent_id!r}")
        seen.add(event_id)
        nodes[event_id] = record
        parents[event_id] = None if parent_id in (None, "") else parent_id
        order.append(event_id)
    return session_id, nodes, parents, order


def _select_leaf(leaf_id: str | None, nodes: dict[str, Any], order: list[str]) -> str | None:
    if leaf_id is None:
        return order[-1] if order else None
    if not isinstance(leaf_id, str) or leaf_id not in nodes:
        raise ValueError(f"Pi session leaf {leaf_id!r} was not found")
    return leaf_id


def _build_event(session_id: str, record: dict[str, JsonValue]) -> PiEventInput | None:
    event_type = record.get("type")
    event_id = record.get("id")
    if not isinstance(event_type, str) or not isinstance(event_id, str):
        return None
    role, body = _event_text(event_type, record)
    if not body:
        return None
    return PiEventInput(
        session_id=session_id,
        event_id=event_id,
        parent_id=record.get("parentId") or None,
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def _event_text(event_type: str, record: dict[str, JsonValue]) -> tuple[str, str]:
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return "", ""
        role = message.get("role")
        if not isinstance(role, str) or not role:
            return "", ""
        return role, _message_body(role, message)
    if event_type in {"compaction", "branch_summary"}:
        summary = record.get("summary")
        if not isinstance(summary, str):
            return event_type, ""
        return event_type, summary
    if event_type == "custom_message":
        return "custom", _joined_blocks(record.get("content"), tool_calls=False)
    return "", ""


def _message_body(role: str, message: dict[str, JsonValue]) -> str:
    if role == "toolResult":
        text = _joined_blocks(message.get("content"), tool_calls=False)
        return f"[tool_result {_text(message.get('toolName'))} {_text(message.get('toolCallId'))}] {text}"
    if role == "bashExecution":
        command = _text(message.get("command"))
        output = _text(message.get("output"))
        return f"$ {command}\n{output}"
    return _joined_blocks(message.get("content"), tool_calls=True)


def _joined_blocks(content: JsonValue, *, tool_calls: bool) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif block_type == "toolCall" and tool_calls:
            arguments = block.get("arguments")
            parts.append(
                f"[tool_call {_text(block.get('name'))} {_text(block.get('id'))}] "
                f"{json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"
            )
    return "\n".join(parts)


def _text(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _event_key(event: PiEventInput) -> tuple[str, str]:
    return event.session_id, event.event_id


def _record_digest(event: PiEventInput) -> str:
    canonical = json.dumps(event.record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _load_checkpoint(checkpoint: JsonValue | None) -> dict[tuple[str, str], str]:
    if checkpoint is None:
        return {}
    if not isinstance(checkpoint, dict) or checkpoint.get("version") != _CHECKPOINT_VERSION:
        raise ValueError("Pi session checkpoint is not readable")
    entries = checkpoint.get("events")
    if not isinstance(entries, list):
        raise ValueError("Pi session checkpoint is not readable")
    captured: dict[tuple[str, str], str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Pi session checkpoint is not readable")
        session_id = entry.get("session_id")
        event_id = entry.get("event_id")
        digest = entry.get("digest")
        if not all(isinstance(value, str) and value for value in (session_id, event_id, digest)):
            raise ValueError("Pi session checkpoint is not readable")
        captured[(session_id, event_id)] = digest
    return captured
