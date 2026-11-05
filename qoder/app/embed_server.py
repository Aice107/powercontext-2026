"""独立向量服务：OpenAI 兼容的 /v1/embeddings。

PowerContext Server 与主应用都调用它。单独拆成进程是为了避免启动顺序依赖，
也让"本地推理、零云端 Key"成为显式的、可单独验证的组件。
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import load_settings
from .embedder import Embedder

app = FastAPI(title="Gewu Embedding Service", version="1.0.0")
_embedder: Embedder | None = None


class EmbeddingRequest(BaseModel):
    model: str = ""
    input: str | list[str]
    dimensions: int | None = Field(default=None)
    user: str | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(load_settings())
    return _embedder


@app.get("/health")
def health() -> dict:
    embedder = get_embedder()
    return {"ok": True, "model": embedder.model_id, "dim": embedder.dim}


@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest) -> dict:
    embedder = get_embedder()
    inputs = [request.input] if isinstance(request.input, str) else list(request.input)
    started = time.perf_counter()
    vectors = embedder.embed(inputs)
    elapsed = (time.perf_counter() - started) * 1000
    return {
        "object": "list",
        "model": request.model or embedder.model_id,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
        "x_elapsed_ms": round(elapsed, 1),
    }


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=int(__import__("os").environ.get("GEWU_EMBED_PORT", "8710")), log_level="warning")


if __name__ == "__main__":
    main()
