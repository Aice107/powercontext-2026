"""轻量字符 n-gram 哈希向量（离线可复现，无需外部 Embedding 服务）。

设计取舍（写进运行说明，评审可核对）：
1. 本项目运行环境无 GPU，且赛题要求"评审无需作者本地服务即可复现"，因此默认使用
   确定性哈希向量，不依赖任何远程 embedding API；
2. 相似度只需在"短句级恶作剧描述"（10~40 字）上排序，字符 bigram 已能区分
   "往酒坛里兑水" / "偷吃酱牛肉" / "掀桌子" 这类语义簇；
3. 通过 EMBEDDING_MODE=api 可切换到任意 OpenAI 兼容 embeddings 端点，
   维度由 EMBEDDING_DIM 控制（默认 1024，与建表语句一致）。

注意：向量只用于 seekdb 相似度排序（翻旧账），不参与任何业务判定。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request

DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
MODE = os.getenv("EMBEDDING_MODE", "hash").lower()
API_BASE = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
API_KEY = os.getenv("EMBEDDING_API_KEY", "")
API_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

_NORM_RE = re.compile(r"[\s，。、；：！？,.;:!?\"'“”‘’（）()\[\]【】]+")


def _normalize(text: str) -> str:
    return _NORM_RE.sub("", (text or "").strip().lower())


def _hash_embed(text: str) -> list[float]:
    """字符 unigram + bigram 哈希到 DIM 维，L2 归一化。"""
    s = _normalize(text)
    if not s:
        return [0.0] * DIM
    vec = [0.0] * DIM
    grams: list[str] = []
    grams.extend(s)  # unigram
    grams.extend(s[i : i + 2] for i in range(len(s) - 1))  # bigram
    for g in grams:
        h = int.from_bytes(hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest(), "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _api_embed(text: str) -> list[float]:
    body = json.dumps({"model": API_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/embeddings",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vec = data["data"][0]["embedding"]
    if len(vec) != DIM:
        raise ValueError(f"embedding dim mismatch: got {len(vec)}, expected {DIM}")
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def embed(text: str) -> list[float]:
    if MODE == "api" and API_BASE:
        return _api_embed(text)
    return _hash_embed(text)


def to_literal(vec: list[float]) -> str:
    """seekdb VECTOR 字面量：'[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
