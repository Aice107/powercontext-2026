#!/usr/bin/env bash
# 打包提交物：dify/ 树打成 zip，并生成带 sha256 的 MANIFEST
# 用法：bash tools/package.sh [输出目录，默认 ../dist]
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT="${1:-$ROOT/../dist}"
NAME="dify-submission-$(date +%Y%m%d)"
mkdir -p "$OUT"

python3 - "$ROOT" "$OUT" "$NAME" <<'PY'
import hashlib
import os
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
name = sys.argv[3]
zip_path = out / f"{name}.zip"

EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules", "dist"}
EXCLUDE_FILES = {".env", ".local.env", ".DS_Store"}


def eligible(p: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in p.parts):
        return False
    if p.name in EXCLUDE_FILES:
        return False
    if p.suffix in {".pyc", ".sse"}:
        return False
    return True


files = sorted(p for p in root.rglob("*") if p.is_file() and eligible(p.relative_to(root)))
lines = []
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        rel = f.relative_to(root)
        zf.write(f, rel.as_posix())
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel.as_posix()}  ({f.stat().st_size} bytes)")

manifest = out / "MANIFEST.sha256"
manifest.write_text(
    "\n".join(
        [
            f"# {name}",
            f"# files: {len(files)}",
            f"# generated: {__import__('datetime').datetime.now().isoformat(timespec='seconds')}",
            "# sha256  path  (size)",
            *lines,
            "",
        ]
    )
)
size_mb = zip_path.stat().st_size / 1024 / 1024
print(f"zip: {zip_path}  ({size_mb:.1f} MB, {len(files)} files)")
print(f"manifest: {manifest}")
PY
