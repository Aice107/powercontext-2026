#!/usr/bin/env python3
"""Hourly compliance snapshot for the six mandatory MiniMax-x-OceanBase items."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"


def latest_run() -> Path | None:
    runs = sorted([path for path in EVIDENCE.glob("run-*") if path.is_dir()], key=lambda path: path.stat().st_mtime)
    return runs[-1] if runs else None


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def check() -> dict[str, Any]:
    run = latest_run()
    acceptance = load_json(run / "acceptance.json", {}) if run else {}
    items = {item.get("id"): item for item in acceptance.get("items", [])} if isinstance(acceptance, dict) else {}
    checks: list[dict[str, Any]] = []

    def add(item_id: int, name: str, state: str, evidence: list[str], note: str) -> None:
        checks.append(
            {
                "id": item_id,
                "name": name,
                "state": state,
                "evidence": evidence,
                "note": note,
            }
        )

    # Prefer the machine-checked acceptance result; fall back to file presence.
    def state_for(item_id: int, fallback_files: list[Path], fallback_note: str) -> tuple[str, str]:
        item = items.get(item_id)
        if item:
            return ("PASS" if item.get("passed") else "FAIL", str(item.get("details", "")))
        ok = all(path.exists() for path in fallback_files) if fallback_files else False
        return ("PASS" if ok else "PENDING", fallback_note)

    run_label = str(run) if run else "no evidence run yet"
    state, note = state_for(
        1,
        [ROOT / "README.md", ROOT / "scripts" / "demo.py", ROOT / "scripts" / "pc_server.sh"],
        "等待首次 demo 运行",
    )
    add(1, "能够运行", state, [run_label], note)

    records: list[dict[str, Any]] = []
    record_path = run / "minimax" / "dev-record.jsonl" if run else None
    if record_path and record_path.exists():
        for line in record_path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    live = [record for record in records if record.get("mode") == "minimax" and record.get("applied")]
    if live:
        add(2, "MiniMax 实际参与", "PASS", [str(record_path)], f"live records={len(live)}")
    else:
        key_present = bool(__import__("os").environ.get("MINIMAX_API_KEY"))
        add(
            2,
            "MiniMax 实际参与",
            "BLOCKED" if not key_present else "FAIL",
            [str(record_path)] if record_path else [],
            "MINIMAX_API_KEY 未设置；仅 replay 记录，不计入必做项"
            if not key_present
            else "已有 Key 但尚无成功应用的 MiniMax 记录",
        )

    state, note = state_for(
        3,
        [run / "context-v1.json", run / "context-v2.json", run / "assert-v2.json"] if run else [],
        "等待上下文证据",
    )
    add(3, "上下文正确且规格更新生效", state, [str(run)] if run else [], note)

    state, note = state_for(
        4,
        [run / "db-stats.json", run / "db-queries.log"] if run else [],
        "等待 seekdb 证据",
    )
    add(4, "数据库实际参与", state, [str(run)] if run else [], note)

    state, note = state_for(
        5,
        [run / "state-save.json", run / "state-after-restart.json", run / "resume-context.json"] if run else [],
        "等待 PowerContext 状态证据",
    )
    add(5, "状态能够复用", state, [str(run)] if run else [], note)

    state, note = state_for(
        6,
        [run / "before-target.log", run / "after-target.log", run / "code-diff.patch"] if run else [],
        "等待修改前后测试证据",
    )
    add(6, "代码修改有效", state, [str(run)] if run else [], note)

    overall = "PASS" if all(item["state"] == "PASS" for item in checks) else "INCOMPLETE"
    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run": str(run) if run else None,
        "overall": overall,
        "checks": checks,
        "git": _git(),
    }


def _git() -> dict[str, Any]:
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        status = subprocess.run(["git", "-C", str(ROOT), "status", "--short"], capture_output=True, text=True)
        return {"head": head.stdout.strip(), "dirty": bool(status.stdout.strip())}
    except OSError:
        return {"head": None, "dirty": None}


def render(result: dict[str, Any], markdown: bool = False) -> str:
    if markdown:
        lines = [
            f"## {result['at']} 自动合规巡检",
            "",
            f"- 运行证据：`{result['run'] or '尚未生成'}`",
            f"- 总体：**{result['overall']}**",
            f"- 代码：`{result['git'].get('head')}` dirty={result['git'].get('dirty')}",
            "",
        ]
        for item in result["checks"]:
            lines.append(f"- [{item['state']}] {item['id']}. {item['name']}：{item['note']}")
        lines.append("")
        return "\n".join(lines)
    lines = [f"{result['at']} overall={result['overall']} run={result['run']}"]
    for item in result["checks"]:
        lines.append(f"  [{item['state']}] {item['id']}. {item['name']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--append", action="store_true", help="append a markdown section to PROGRESS_LOG.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check()
    if args.append:
        log = ROOT / "PROGRESS_LOG.md"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(render(result, markdown=True) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
