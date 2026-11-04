#!/usr/bin/env python3
"""Assert that a generated context contains (or omits) required real sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--require-spec", action="append", default=[])
    parser.add_argument("--forbid-spec", action="append", default=[])
    parser.add_argument("--require-code", action="append", default=[], help="path::symbol")
    parser.add_argument("--require-test", action="append", default=[], help="path::symbol")
    parser.add_argument("--require-text", action="append", default=[])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    spec_ids = {item.get("spec_id") for item in context.get("specs", [])}
    for spec_id in args.require_spec:
        checks.append({"check": "require_spec", "value": spec_id, "ok": spec_id in spec_ids})
    for spec_id in args.forbid_spec:
        checks.append({"check": "forbid_spec", "value": spec_id, "ok": spec_id not in spec_ids})

    code_keys = {f"{item['path']}::{item.get('symbol')}" for item in context.get("code", [])}
    for key in args.require_code:
        checks.append({"check": "require_code", "value": key, "ok": key in code_keys})

    test_keys = {f"{item['path']}::{item.get('symbol')}" for item in context.get("tests", [])}
    for key in args.require_test:
        checks.append({"check": "require_test", "value": key, "ok": key in test_keys})

    all_text = "\n".join(
        item.get("text", "")
        for section in ("specs", "code", "tests")
        for item in context.get(section, [])
    )
    for needle in args.require_text:
        checks.append({"check": "require_text", "value": needle, "ok": needle in all_text})

    result = {
        "context": str(Path(args.context).resolve()),
        "task_id": context.get("task", {}).get("id"),
        "context_sha256": context.get("context_sha256"),
        "specs": sorted(spec_ids),
        "checks": checks,
        "passed": all(check["ok"] for check in checks),
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
