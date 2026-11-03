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

"""Source lifecycle withdrawal, restoration, and dependency propagation."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory.models import MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.source_lifecycle import (
    SourceLifecycleRepository,
    StoredSourceLifecycleNode,
)
from powercontext.builtin.runtime.models import GetMemoryEntryRequest
from powercontext.builtin.statistics import ModelUsagePurpose
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import BuiltinRuntime

MAX_LIFECYCLE_REASON_LENGTH = 1000
LifecyclePolicy = Literal["all", "any"]
LifecyclePurpose = Literal["generation", "audit"]


class SourceLifecycleError(ValueError):
    """A lifecycle registration, event, or resolution request is invalid."""


class SourceLifecycleEvent(BaseModel):
    """One ordered availability observation for a registered Source node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=MAX_SOURCE_ID_LENGTH)
    revision: int = Field(strict=True, ge=1)
    sequence: int = Field(strict=True, ge=1)
    available: bool = Field(strict=True)
    reason: str = Field(min_length=1, max_length=MAX_LIFECYCLE_REASON_LENGTH)

    @field_validator("node_id", "reason")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("lifecycle text must be nonempty and trimmed")
        return value


class SourceLifecycleApplication:
    """Select the lifecycle service for one scope."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase) -> None:
        self._runtime = runtime
        self._database = database
        self._repository = SourceLifecycleRepository()

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, self._database, scope_id, self._repository)


class ScopedSourceLifecycle:
    """Register dependency nodes and apply ordered Source availability events."""

    def __init__(
        self,
        runtime: BuiltinRuntime,
        database: AsyncDatabase,
        scope_id: str,
        repository: SourceLifecycleRepository,
    ) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = scope_id
        self._repository = repository

    async def register_source(self, node_id: str, reference: SourceRef, /, *, revision: int) -> None:
        if not isinstance(reference, SourceRef):
            raise SourceLifecycleError("source reference is invalid")
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("source revision must be positive")
        node = self._validate_node_id(node_id)
        try:
            await self._runtime.records.for_scope(self.scope_id).get_source(reference.source_type, reference.source_id)
        except Exception as error:
            raise SourceLifecycleError("source reference does not exist") from error
        await self._register(
            node,
            kind="source",
            reference=reference,
            revision=revision,
            parents=(),
            policy="all",
            available=True,
        )

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        /,
        *,
        parents: tuple[str, ...],
        policy: LifecyclePolicy,
    ) -> None:
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("memory citation is invalid")
        node = self._validate_node_id(node_id)
        parent_ids = await self._validate_parents(node, parents)
        selected_policy = self._validate_policy(policy)
        try:
            await self._runtime.memory.for_scope(self.scope_id).get(GetMemoryEntryRequest(citation=citation))
        except Exception as error:
            raise SourceLifecycleError("memory citation does not exist") from error
        await self._register(
            node,
            kind="memory",
            reference=citation,
            revision=0,
            parents=parent_ids,
            policy=selected_policy,
            available=False,
        )

    async def register_topic(
        self,
        node_id: str,
        reference: ArtifactRef,
        /,
        *,
        parents: tuple[str, ...],
        policy: LifecyclePolicy,
    ) -> None:
        if not isinstance(reference, ArtifactRef):
            raise SourceLifecycleError("topic reference is invalid")
        node = self._validate_node_id(node_id)
        parent_ids = await self._validate_parents(node, parents)
        selected_policy = self._validate_policy(policy)
        try:
            await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                reference.family, reference.artifact_id, reference.revision
            )
        except Exception as error:
            raise SourceLifecycleError("topic reference does not exist") from error
        await self._register(
            node,
            kind="topic",
            reference=reference,
            revision=0,
            parents=parent_ids,
            policy=selected_policy,
            available=False,
        )

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:  # noqa: C901 - ordered propagation
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("lifecycle event is invalid")
        active: list[str] = []
        async with (
            self._runtime._scoped_operation(self.scope_id),
            self._runtime._locked(self.scope_id),
            self._database.transaction() as connection,
        ):
            rows = await self._repository.list(connection, self.scope_id)
            by_id = {row.node_id: row for row in rows}
            source = by_id.get(event.node_id)
            if source is None:
                raise SourceLifecycleError("source node is not registered")
            if source.node_kind != "source":
                raise SourceLifecycleError("event node is not a Source")
            if event.revision != source.source_revision:
                raise SourceLifecycleError("event revision does not match the registered Source")
            if event.sequence < source.last_sequence:
                raise SourceLifecycleError("event sequence is stale")
            replay = event.sequence == source.last_sequence
            if replay and event.available != source.available:
                raise SourceLifecycleError("event sequence already has different availability")
            if not replay:
                await self._repository.update_state(
                    connection,
                    self.scope_id,
                    source.node_id,
                    available=event.available,
                    last_sequence=event.sequence,
                )
            states = {row.node_id: row.available for row in rows}
            states[source.node_id] = event.available
            for row in sorted(rows, key=lambda item: (item.ordinal, item.node_id)):
                if row.node_kind == "source":
                    target = states[row.node_id]
                else:
                    support = [states[parent] for parent in json.loads(row.parents)]
                    target = all(support) if row.policy == "all" else any(support)
                if target != row.available:
                    await self._repository.update_state(connection, self.scope_id, row.node_id, available=target)
                states[row.node_id] = target
            active = sorted(node_id for node_id, available in states.items() if available)
        await self._sync_memory_states()
        return active

    async def resolve(self, node_id: str, /, *, purpose: LifecyclePurpose) -> SourceRef | MemoryCitation | ArtifactRef:
        if purpose not in ("generation", "audit"):
            raise SourceLifecycleError("resolution purpose is invalid")
        rows = await self._load()
        row = next((item for item in rows if item.node_id == node_id), None)
        if row is None:
            raise SourceLifecycleError("node is not registered")
        if purpose == "generation" and not row.available:
            raise SourceLifecycleError("node is unavailable for generation")
        return self._decode_reference(row)

    async def inactive_topic_identities(self) -> frozenset[tuple[str, int]]:
        rows = await self._load()
        identities: set[tuple[str, int]] = set()
        for row in rows:
            if row.node_kind != "topic" or row.available:
                continue
            reference = self._decode_reference(row)
            if isinstance(reference, ArtifactRef):
                identities.add((reference.artifact_id, reference.revision))
        return frozenset(identities)

    async def _register(
        self,
        node_id: str,
        *,
        kind: str,
        reference: SourceRef | MemoryCitation | ArtifactRef,
        revision: int,
        parents: tuple[str, ...],
        policy: str,
        available: bool,
    ) -> None:
        registration = _registration(kind, reference, revision, parents, policy)
        async with (
            self._runtime._scoped_operation(self.scope_id),
            self._runtime._locked(self.scope_id),
            self._database.transaction() as connection,
        ):
            existing = await self._repository.get(connection, self.scope_id, node_id)
            if existing is not None:
                if existing.registration != registration:
                    raise SourceLifecycleError("node is already registered with different identity")
                target = existing.available
            else:
                rows = await self._repository.list(connection, self.scope_id)
                by_id = {row.node_id: row for row in rows}
                if not parents:
                    if kind != "source":
                        raise SourceLifecycleError("derived nodes require at least one parent")
                    target = available
                else:
                    for parent in parents:
                        if parent not in by_id:
                            raise SourceLifecycleError("parent is not registered")
                    support = [by_id[parent].available for parent in parents]
                    target = all(support) if policy == "all" else any(support)
                ordinal = max((row.ordinal for row in rows), default=0) + 1
                await self._repository.insert(
                    connection,
                    StoredSourceLifecycleNode(
                        scope_id=self.scope_id,
                        node_id=node_id,
                        node_kind=kind,
                        ordinal=ordinal,
                        reference=json.dumps(reference.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
                        source_revision=revision,
                        policy=policy,
                        parents=json.dumps(list(parents), separators=(",", ":")),
                        available=target,
                        last_sequence=0,
                        registration=registration,
                    ),
                )
        if kind == "memory":
            await self._sync_memory_node(node_id)

    async def _sync_memory_states(self) -> None:
        rows = await self._load()
        for row in rows:
            if row.node_kind == "memory":
                await self._sync_memory_node(row.node_id)

    async def _sync_memory_node(self, node_id: str) -> None:
        rows = await self._load()
        row = next((item for item in rows if item.node_id == node_id), None)
        if row is None or row.node_kind != "memory":
            return
        reference = self._decode_reference(row)
        if not isinstance(reference, MemoryCitation):
            raise SourceLifecycleError("memory node reference is invalid")
        async with self._runtime._context(
            self.scope_id,
            embedding_purpose=ModelUsagePurpose.MEMORY_INDEXING,
        ) as context:
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            entries = await service.entries(current)
            entry = next((item for item in entries if item.entry_id == reference.entry_id), None)
            if entry is None:
                raise SourceLifecycleError("memory entry no longer exists")
            state = next(
                (
                    item.state
                    for item in current.content.manifest.entries
                    if item.entry_id == reference.entry_id and item.entry_version_id == entry.entry_version_id
                ),
                None,
            )
            if (state == "active") == row.available:
                return
            async with self._runtime._locked(self.scope_id):
                if row.available:
                    await service.reactivate(current, entries=(entry,), reason="source lifecycle")
                else:
                    await service.forget(current, entries=(entry,), reason="source lifecycle")

    async def _load(self) -> tuple[StoredSourceLifecycleNode, ...]:
        async with self._database.transaction() as connection:
            return await self._repository.list(connection, self.scope_id)

    def _decode_reference(self, row: StoredSourceLifecycleNode) -> SourceRef | MemoryCitation | ArtifactRef:
        payload = json.loads(row.reference)
        if row.node_kind == "source":
            return SourceRef.model_validate(payload)
        if row.node_kind == "memory":
            return MemoryCitation.model_validate(payload)
        if row.node_kind == "topic":
            return ArtifactRef.model_validate(payload)
        raise SourceLifecycleError("node kind is invalid")

    async def _validate_parents(self, node_id: str, parents: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(parents, tuple) or not parents:
            raise SourceLifecycleError("parents must be a nonempty tuple")
        if any(not isinstance(parent, str) or parent != parent.strip() for parent in parents):
            raise SourceLifecycleError("parent identifier is invalid")
        if len(set(parents)) != len(parents):
            raise SourceLifecycleError("parents must be unique")
        if node_id in parents:
            raise SourceLifecycleError("node cannot depend on itself")
        rows = await self._load()
        known = {row.node_id for row in rows}
        if any(parent not in known for parent in parents):
            raise SourceLifecycleError("parent is not registered")
        return parents

    def _validate_node_id(self, node_id: str) -> str:
        if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
            raise SourceLifecycleError("node identifier must be nonempty and trimmed")
        if len(node_id) > MAX_SOURCE_ID_LENGTH:
            raise SourceLifecycleError("node identifier is too long")
        return node_id

    def _validate_policy(self, policy: str) -> LifecyclePolicy:
        if policy not in ("all", "any"):
            raise SourceLifecycleError("policy must be all or any")
        return policy


def _registration(
    kind: str,
    reference: SourceRef | MemoryCitation | ArtifactRef,
    revision: int,
    parents: tuple[str, ...],
    policy: str,
) -> str:
    return json.dumps(
        {
            "kind": kind,
            "reference": reference.model_dump(mode="json"),
            "revision": revision,
            "parents": list(parents),
            "policy": policy,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
