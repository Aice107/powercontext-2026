#!/usr/bin/env bash
# One-command final live run: requires a real MINIMAX_API_KEY in .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "missing .env; create it with MINIMAX_API_KEY=<real-key> and chmod 600 it" >&2
  exit 2
fi
chmod 600 .env || true

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [ -z "${MINIMAX_API_KEY:-}" ] || [ "${MINIMAX_API_KEY}" = "<set-me>" ]; then
  echo "MINIMAX_API_KEY is empty/placeholder in .env" >&2
  exit 2
fi

bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start
.venv/bin/python scripts/demo.py --mode minimax --run-id final

rm -rf "$ROOT/evidence/reference"
cp -a "$ROOT/evidence/run-final" "$ROOT/evidence/reference"
cat > "$ROOT/evidence/reference/README.md" <<'EOF'
# 参考运行（live MiniMax）

- 生成命令：`.venv/bin/python scripts/demo.py --mode minimax --run-id final`
- 本目录的 `minimax/dev-record.jsonl` 应包含 `mode=minimax` 且 `applied=true` 的记录。
- 机器核验：`.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/reference`
EOF

.venv/bin/python scripts/verify_acceptance.py --run-dir "$ROOT/evidence/reference"
echo
echo "final evidence: $ROOT/evidence/reference"
echo "next: review, git add minimax/evidence/reference, commit, and submit the HEAD hash"
