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

# ruff: noqa: TRY003 - inline messages are the documented wire protocol contract.

"""Incremental Context Pack wire protocol.

A full pack carries deterministic, UTF-8-valid chunks plus a digest and its own
serialized size.  A delta reuses a valid prefix of a base pack and only carries
the target suffix.  Decoding depends only on the serialized bytes, never on
sender-side memory.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512


class ContextPackError(ValueError):
    """Raised when a pack or delta violates the wire protocol."""


@dataclass(frozen=True)
class ContextPack:
    """One complete context payload with deterministic chunks."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: Any) -> ContextPack:
        """Build a complete pack from a bytes iterable."""

        normalized = _normalize_items(items)
        encoded = [base64.b64encode(item).decode("ascii") for item in normalized]
        digest = _pack_digest(encoded)
        return cls(normalized, digest, _pack_byte_count(encoded, digest))

    @classmethod
    def from_content(cls, content: str | bytes, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        """Chunk text into deterministic, UTF-8-valid chunks within the byte bound."""

        if type(chunk_bytes) is not int or chunk_bytes < 1:
            raise ContextPackError("chunk_bytes must be a positive integer")
        if isinstance(content, str):
            data = content.encode("utf-8")
        elif isinstance(content, (bytes, bytearray)):
            data = bytes(content)
        else:
            raise ContextPackError("content must be text or bytes")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContextPackError("content must be valid UTF-8") from error
        return cls.build(tuple(_chunk_text(text, chunk_bytes)))

    def to_bytes(self) -> bytes:
        """Serialize the complete pack in canonical wire JSON."""

        return _canonical({
            "schema": PACK_SCHEMA,
            "items": [base64.b64encode(item).decode("ascii") for item in self.items],
            "digest": self.digest,
            "byte_count": self.byte_count,
        })

    @classmethod
    def from_bytes(cls, data: bytes | str) -> ContextPack:
        """Decode and validate one complete pack."""

        payload = _load_object(data)
        _require_keys(payload, {"schema", "items", "digest", "byte_count"})
        if payload["schema"] != PACK_SCHEMA:
            raise ContextPackError("pack schema is invalid")
        encoded = _require_base64_list(payload["items"])
        digest = _require_digest(payload["digest"])
        if digest != _pack_digest(encoded):
            raise ContextPackError("pack digest does not match its items")
        byte_count = payload["byte_count"]
        if type(byte_count) is not int or byte_count < 0:
            raise ContextPackError("pack byte_count must be a non-negative integer")
        expected = _pack_byte_count(encoded, digest)
        if byte_count != expected:
            raise ContextPackError("pack byte_count does not match its serialization")
        return cls(tuple(_decode_base64(value) for value in encoded), digest, expected)


@dataclass(frozen=True)
class ContextPackDelta:
    """A target suffix plus the valid base prefix it reuses."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        """Choose the longest valid common item prefix and carry the suffix."""

        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("delta endpoints must be complete ContextPacks")
        prefix = 0
        for existing, incoming in zip(base.items, target.items, strict=False):
            if existing != incoming:
                break
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=target.items[prefix:],
        )

    def to_bytes(self) -> bytes:
        """Serialize the delta without the non-wire ``byte_count`` field."""

        return _canonical({
            "schema": DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [base64.b64encode(item).decode("ascii") for item in self.appended],
        })

    @classmethod
    def from_bytes(cls, data: bytes | str) -> ContextPackDelta:
        """Decode and validate one delta."""

        payload = _load_object(data)
        _require_keys(payload, {"schema", "base_digest", "target_digest", "prefix_items", "appended"})
        if payload["schema"] != DELTA_SCHEMA:
            raise ContextPackError("delta schema is invalid")
        base_digest = _require_digest(payload["base_digest"])
        target_digest = _require_digest(payload["target_digest"])
        prefix = payload["prefix_items"]
        if type(prefix) is not int or prefix < 0:
            raise ContextPackError("delta prefix_items must be a non-negative integer")
        appended = tuple(_decode_base64(value) for value in _require_base64_list(payload["appended"]))
        return cls(base_digest, target_digest, prefix, appended)


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Validate a delta against its base and rebuild the exact target pack."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("delta application requires a complete base pack and delta")
    if base.digest != delta.base_digest:
        raise ContextPackError("delta base digest does not match the supplied base pack")
    if type(delta.prefix_items) is not int or delta.prefix_items < 0 or delta.prefix_items > len(base.items):
        raise ContextPackError("delta prefix_items is outside the base pack")
    target = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("delta target digest does not match the rebuilt pack")
    return target


def _normalize_items(items: Any) -> tuple[bytes, ...]:
    if not isinstance(items, (tuple, list)):
        raise ContextPackError("pack items must be a bytes sequence")
    normalized: list[bytes] = []
    for item in items:
        if not isinstance(item, (bytes, bytearray)):
            raise ContextPackError("pack items must be bytes")
        normalized.append(bytes(item))
    return tuple(normalized)


def _chunk_text(text: str, chunk_bytes: int) -> list[bytes]:
    chunks: list[bytes] = []
    current = bytearray()
    for character in text:
        encoded = character.encode("utf-8")
        if len(encoded) > chunk_bytes:
            raise ContextPackError("a single character exceeds chunk_bytes")
        if current and len(current) + len(encoded) > chunk_bytes:
            chunks.append(bytes(current))
            current = bytearray()
        current.extend(encoded)
    if current:
        chunks.append(bytes(current))
    return chunks


def _pack_digest(encoded_items: list[str]) -> str:
    canonical = _canonical({"schema": PACK_SCHEMA, "items": encoded_items})
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _pack_byte_count(encoded_items: list[str], digest: str) -> int:
    count = 0
    while True:
        serialized = _canonical({"schema": PACK_SCHEMA, "items": encoded_items, "digest": digest, "byte_count": count})
        updated = len(serialized)
        if updated == count:
            return count
        count = updated


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_object(data: bytes | str) -> dict[str, Any]:
    try:
        payload = json.loads(data)
    except (TypeError, ValueError) as error:
        raise ContextPackError("wire payload must be valid JSON") from error
    if not isinstance(payload, dict):
        raise ContextPackError("wire payload must be a JSON object")
    return payload


def _require_keys(payload: dict[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ContextPackError("wire payload fields do not match the schema")


def _require_base64_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContextPackError("chunk arrays must contain Base64 strings")
    for item in value:
        _decode_base64(item)
    return value


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ContextPackError("chunk is not valid Base64") from error


def _require_digest(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ContextPackError("digest must be sha256:<lowercase hex>")
    return value


__all__ = [
    "DEFAULT_CHUNK_BYTES",
    "DELTA_SCHEMA",
    "PACK_SCHEMA",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
