"""证据日志：把 seekdb 检索与 PowerContext 记忆读写落成 JSONL，供评审核对。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Journal:
    def __init__(self, log_dir: Path) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, channel: str) -> Path:
        return self._dir / f"{channel}.jsonl"

    def append(self, channel: str, record: dict) -> None:
        path = self._path(channel)
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}, ensure_ascii=False)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def tail(self, channel: str, limit: int = 50) -> list[dict]:
        path = self._path(channel)
        if not path.is_file():
            return []
        with self._lock, path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()[-limit:]
        records: list[dict] = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
