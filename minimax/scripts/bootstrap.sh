#!/usr/bin/env bash
# Prepare the reproducible environment for the SDD context demo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [ "$CHECK_ONLY" -eq 0 ]; then
  if [ ! -x "$ROOT/.venv/bin/python" ]; then
    uv venv --python 3.12 "$ROOT/.venv"
  fi
  uv sync --python 3.12
fi

"$ROOT/.venv/bin/python" - <<'PY'
import importlib.metadata
import sys
print(f"python={sys.version.split()[0]}")
for name in ("flask", "pymysql", "pylibseekdb", "pytest"):
    try:
        print(f"{name}={importlib.metadata.version(name)}")
    except importlib.metadata.PackageNotFoundError:
        print(f"{name}=missing")
PY

if ! command -v powercontext >/dev/null 2>&1; then
  echo "PowerContext CLI not found. Install it with:" >&2
  echo "  uv tool install --force 'powercontext[cli,server]==1.4.1'" >&2
  exit 1
fi
echo "powercontext=$(powercontext --version)"
echo "bootstrap OK"
