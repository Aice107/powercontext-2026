"""本地 ONNX 向量模型。不依赖任何云端推理接口。

模型是 bge-small-zh-v1.5（512 维，mean pooling + 单位归一化）。
检索场景下查询侧带 bge 的指令前缀，文档侧不带，这是该模型的官方用法。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from .config import Settings, load_settings

QUERY_PREFIX = "为这个句子生成表示以用于检索文章："
SPECIAL_TOKENS = ("[CLS]", "[SEP]", "[PAD]", "[MASK]", "[UNK]")
MAX_TOKENS = 256


class Embedder:
    """把文本编码成单位长度的 512 维向量。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._lock = threading.Lock()
        model_dir = self.settings.model_dir
        if not (model_dir / "model.onnx").is_file():
            raise FileNotFoundError(f"模型缺失：{model_dir}/model.onnx，请先执行 bash scripts/fetch_model.sh")
        tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        missing = [t for t in SPECIAL_TOKENS if tokenizer.token_to_id(t) is None]
        if missing:
            tokenizer.add_special_tokens(missing)
        tokenizer.enable_padding(pad_id=tokenizer.token_to_id("[PAD]") or 0, pad_token="[PAD]")
        self._tokenizer = tokenizer
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"),
            sess_options=_session_options(),
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        config = model_dir / "config.json"
        self._dim = self.settings.embedding_dim
        if config.is_file():
            hidden = json.loads(config.read_text()).get("hidden_size")
            if isinstance(hidden, int) and hidden > 0:
                self._dim = hidden

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_id(self) -> str:
        return self.settings.embedding_model

    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        payloads = [f"{QUERY_PREFIX}{t}" if is_query else t for t in texts]
        with self._lock:
            encodings = self._tokenizer.encode_batch(payloads)
            feeds = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)
            output = self._session.run(None, feeds)[0].astype(np.float32)
        mask = feeds["attention_mask"].astype(np.float32)[:, :, None]
        summed = (output * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1.0, None)
        vectors = summed / counts
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.clip(norms, 1e-12, None)
        return [[float(x) for x in row] for row in vectors]


def _session_options() -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.log_severity_level = 3
    return options
