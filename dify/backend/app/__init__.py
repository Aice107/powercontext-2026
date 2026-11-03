"""极简 .env 加载器：让 `uvicorn app.main:app` 直接可用，无需先 source。

只支持 KEY=VALUE 与 # 注释；已存在的环境变量优先（便于容器/CI 覆盖）。
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_env() -> None:
    for candidate in (Path(__file__).resolve().parents[1] / ".env", Path.cwd() / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        break


_load_env()
