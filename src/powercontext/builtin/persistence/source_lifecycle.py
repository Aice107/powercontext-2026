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

"""Persist Source lifecycle nodes and dependency edges for one scope."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_TABLE


@dataclass(frozen=True, slots=True)
class StoredSourceLifecycleNode:
    scope_id: str
    node_id: str
    node_kind: str
    ordinal: int
    reference: str
    source_revision: int
    policy: str
    parents: str
    available: bool
    last_sequence: int
    registration: str


def _decode(row: object) -> StoredSourceLifecycleNode:
    data = dict(row)  # type: ignore[arg-type]
    return StoredSourceLifecycleNode(**data)


class SourceLifecycleRepository:
    """Read and write lifecycle nodes using caller-owned transactions."""

    async def list(self, connection: AsyncConnection, scope_id: str, /) -> tuple[StoredSourceLifecycleNode, ...]:
        table = SOURCE_LIFECYCLE_TABLE
        rows = (
            await connection.execute(
                select(table).where(table.c.scope_id == scope_id).order_by(table.c.ordinal, table.c.node_id)
            )
        ).mappings()
        return tuple(_decode(row) for row in rows)

    async def get(
        self, connection: AsyncConnection, scope_id: str, node_id: str, /
    ) -> StoredSourceLifecycleNode | None:
        table = SOURCE_LIFECYCLE_TABLE
        row = (
            (await connection.execute(select(table).where(table.c.scope_id == scope_id, table.c.node_id == node_id)))
            .mappings()
            .one_or_none()
        )
        return None if row is None else _decode(row)

    async def max_ordinal(self, connection: AsyncConnection, scope_id: str, /) -> int:
        table = SOURCE_LIFECYCLE_TABLE
        value = await connection.scalar(select(func.max(table.c.ordinal)).where(table.c.scope_id == scope_id))
        return int(value or 0)

    async def insert(self, connection: AsyncConnection, node: StoredSourceLifecycleNode, /) -> None:
        await connection.execute(
            SOURCE_LIFECYCLE_TABLE.insert().values(
                scope_id=node.scope_id,
                node_id=node.node_id,
                node_kind=node.node_kind,
                ordinal=node.ordinal,
                reference=node.reference,
                source_revision=node.source_revision,
                policy=node.policy,
                parents=node.parents,
                available=node.available,
                last_sequence=node.last_sequence,
                registration=node.registration,
            )
        )

    async def update_state(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        /,
        *,
        available: bool,
        last_sequence: int | None = None,
    ) -> None:
        values: dict[str, object] = {"available": available}
        if last_sequence is not None:
            values["last_sequence"] = last_sequence
        await connection.execute(
            update(SOURCE_LIFECYCLE_TABLE)
            .where(
                SOURCE_LIFECYCLE_TABLE.c.scope_id == scope_id,
                SOURCE_LIFECYCLE_TABLE.c.node_id == node_id,
            )
            .values(**values)
        )
