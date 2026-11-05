"""运行期配置。所有路径与连接参数都可以用环境变量覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    home: Path
    seekdb_dir: Path
    seekdb_database: str
    model_dir: Path
    embedding_dim: int
    embedding_model: str
    pc_base_url: str
    pc_token: str
    scope_owner: str
    host: str
    port: int
    log_dir: Path

    @property
    def corpus_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "corpus"

    @property
    def evidence_dir(self) -> Path:
        return PROJECT_ROOT / "evidence"


def load_settings() -> Settings:
    home = Path(_env("GEWU_HOME", str(PROJECT_ROOT / ".data"))).expanduser()
    return Settings(
        home=home,
        seekdb_dir=Path(_env("GEWU_SEEKDB_DIR", str(home / "seekdb"))),
        seekdb_database=_env("GEWU_SEEKDB_DATABASE", "gewu"),
        model_dir=Path(_env("GEWU_MODEL_DIR", str(home / "models" / "bge-small-zh-v1.5-onnx"))),
        embedding_dim=_env_int("GEWU_EMBEDDING_DIM", 512),
        embedding_model=_env("GEWU_EMBEDDING_MODEL", "bge-small-zh-v1.5"),
        pc_base_url=_env("GEWU_PC_URL", "http://127.0.0.1:8000").rstrip("/"),
        pc_token=_env("GEWU_PC_TOKEN", ""),
        scope_owner=_env("GEWU_SCOPE_OWNER", "u_demo"),
        host=_env("GEWU_HOST", "127.0.0.1"),
        port=_env_int("GEWU_PORT", 8712),
        log_dir=home / "logs",
    )
