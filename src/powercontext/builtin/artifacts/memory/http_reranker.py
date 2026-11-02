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

# ruff: noqa: TRY003 - inline messages are the documented HTTP protocol contract.

"""HTTP cross-encoder Memory reranking.

The remote service scores ``(query, candidate)`` pairs.  Candidates keep the
global one-based rank they had in the complete input pool; batching never
renumbers them, and the final selection always uses one global ordering over
every returned score.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage


class HTTPMemoryReranker:
    """Score Memory candidates through one batching HTTP service."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("reranker endpoint must be a non-empty string")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("reranker batch_size must be a positive integer")
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError("reranker policy_id must be a non-empty string")
        self.endpoint = endpoint
        self.policy_id = policy_id
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score every candidate exactly once and select one global top list."""

        if not candidates:
            raise ValueError("rerank requires at least one candidate")
        if type(limit) is not int or limit < 1 or limit > len(candidates):
            raise ValueError("rerank limit must be between one and the candidate count")

        ranked = tuple(enumerate(candidates, start=1))
        batches = [ranked[index : index + self._batch_size] for index in range(0, len(ranked), self._batch_size)]
        scores: dict[int, float] = {}
        for batch in batches:
            payload = {
                "query": query,
                "candidates": [{"rank": rank, "text": candidate.text} for rank, candidate in batch],
            }
            response = await self._client.post(self.endpoint, json=payload)
            response.raise_for_status()
            scores.update(_parse_scores(response, {rank for rank, _ in batch}))

        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return MemoryRerankDecision(
            selected_ranks=tuple(rank for rank, _ in ordered[:limit]),
            usage=InferenceUsage(requests=len(batches)),
        )


def _parse_scores(response: httpx.Response, expected_ranks: set[int]) -> dict[int, float]:
    """Validate one response and return the finite scores for its exact batch."""

    try:
        body: Any = response.json()
    except ValueError as error:
        raise ValueError("reranker response must be valid JSON") from error
    if not isinstance(body, dict) or set(body) != {"scores"}:
        raise ValueError("reranker response must contain exactly the scores field")
    raw_scores = body["scores"]
    if not isinstance(raw_scores, list):
        raise ValueError("reranker scores must be a list")  # noqa: TRY004 - protocol failure is ValueError

    parsed: dict[int, float] = {}
    for item in raw_scores:
        if not isinstance(item, dict) or set(item) != {"rank", "score"}:
            raise ValueError("each reranker score must contain exactly rank and score")
        rank = item["rank"]
        score = item["score"]
        if type(rank) is not int or rank not in expected_ranks:
            raise ValueError("reranker score rank is outside this batch")
        if rank in parsed:
            raise ValueError("reranker score rank is duplicated")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("reranker score must be a finite number")
        parsed[rank] = float(score)

    if set(parsed) != expected_ranks:
        raise ValueError("reranker scores must cover every batch rank exactly once")
    return parsed
