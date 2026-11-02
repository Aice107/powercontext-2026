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

# ruff: noqa: TRY003 - inline messages are the documented batching contract.

"""Cross-call Embedding request coalescing and bounded vector caching.

Callers enqueue unique texts; one background worker forms bounded underlying
batches.  Identical texts share in-flight work, successful vectors feed an LRU
cache, and callers keep their original order and duplicate positions.  Caller
cancellation is isolated from the shared worker by shielding per-text futures.
"""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass
class _Pending:
    text: str
    future: asyncio.Future[tuple[float, ...]]
    batch: _Batch | None = None


@dataclass(frozen=True)
class _Batch:
    usage: InferenceUsage


class CoalescingEmbeddingModel:
    """Coalesce concurrent Embedding calls behind one bounded worker."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if not callable(getattr(model, "embed", None)):
            raise ValueError("embedding model must provide embed()")  # noqa: TRY004
        if type(max_batch_size) is not int or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")
        if (
            isinstance(coalesce_ms, bool)
            or not isinstance(coalesce_ms, (int, float))
            or not math.isfinite(coalesce_ms)
            or coalesce_ms < 0
        ):
            raise ValueError("coalesce_ms must be a finite non-negative number")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        self._model = model
        self.max_batch_size = max_batch_size
        self.coalesce_ms = float(coalesce_ms)
        self.cache_size = cache_size
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._pending: dict[str, _Pending] = {}
        self._queue: deque[_Pending] = deque()
        self._lock = asyncio.Lock()
        self._wakeup = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None

    @property
    def profile(self) -> Any:
        return self._model.profile

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Return one ordered vector per input position, sharing duplicate work."""

        values = tuple(texts)
        if not values:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        unique = tuple(dict.fromkeys(values))
        loop = asyncio.get_running_loop()
        pending: list[_Pending] = []
        vectors: dict[str, tuple[float, ...]] = {}
        async with self._lock:
            for text in unique:
                if text in self._cache:
                    self._cache.move_to_end(text)
                    vectors[text] = self._cache[text]
                    continue
                entry = self._pending.get(text)
                if entry is None:
                    entry = _Pending(text=text, future=loop.create_future())
                    self._pending[text] = entry
                    self._queue.append(entry)
                pending.append(entry)
            if pending:
                self._ensure_worker()
                self._wakeup.set()

        batches: list[_Batch] = []
        if pending:
            results = await asyncio.gather(
                *(asyncio.shield(entry.future) for entry in pending),
                return_exceptions=True,
            )
            for entry, result in zip(pending, results, strict=True):
                if isinstance(result, BaseException):
                    raise result
                vectors[entry.text] = result
                if entry.batch is not None:
                    batches.append(entry.batch)
        return EmbeddingResult(
            vectors=tuple(vectors[text] for text in values),
            usage=_sum_usage(_distinct_batches(batches)),
        )

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            if self.coalesce_ms > 0:
                await asyncio.sleep(self.coalesce_ms / 1000.0)
            while True:
                async with self._lock:
                    batch = self._take_batch()
                if not batch:
                    break
                await self._execute(batch)

    def _take_batch(self) -> list[_Pending]:
        batch: list[_Pending] = []
        while self._queue and len(batch) < self.max_batch_size:
            batch.append(self._queue.popleft())
        return batch

    async def _execute(self, batch: list[_Pending]) -> None:  # noqa: C901 - explicit batch lifecycle
        texts = tuple(entry.text for entry in batch)
        try:
            result = await self._model.embed(texts)
            if len(result.vectors) != len(texts):
                raise ValueError("embedding model returned a mismatched vector count")  # noqa: TRY301
            resolved: list[tuple[float, ...]] = []
            for vector in result.vectors:
                vector_tuple = tuple(float(component) for component in vector)
                resolved.append(vector_tuple)
            marker = _Batch(usage=result.usage)
            async with self._lock:
                if self.cache_size > 0:
                    for text, vector in zip(texts, resolved, strict=True):
                        self._cache[text] = vector
                        self._cache.move_to_end(text)
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
                for entry in batch:
                    entry.batch = marker
                    self._pending.pop(entry.text, None)
            for entry, vector in zip(batch, resolved, strict=True):
                if not entry.future.done():
                    entry.future.set_result(vector)
        except Exception as error:
            async with self._lock:
                for entry in batch:
                    self._pending.pop(entry.text, None)
            for entry in batch:
                if not entry.future.done():
                    entry.future.set_exception(error)


def _distinct_batches(batches: list[_Batch]) -> list[_Batch]:
    seen: set[int] = set()
    distinct: list[_Batch] = []
    for batch in batches:
        if id(batch) in seen:
            continue
        seen.add(id(batch))
        distinct.append(batch)
    return distinct


def _sum_usage(batches: list[_Batch]) -> InferenceUsage:
    if not batches:
        return InferenceUsage(requests=0)
    input_tokens = [batch.usage.input_tokens for batch in batches if batch.usage.input_tokens is not None]
    output_tokens = [batch.usage.output_tokens for batch in batches if batch.usage.output_tokens is not None]
    return InferenceUsage(
        requests=sum(batch.usage.requests for batch in batches),
        input_tokens=sum(input_tokens) if input_tokens else None,
        output_tokens=sum(output_tokens) if output_tokens else None,
    )


__all__ = ["CoalescingEmbeddingModel"]
