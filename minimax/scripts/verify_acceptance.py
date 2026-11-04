#!/usr/bin/env python3
"""Check the six mandatory acceptance items from an evidence run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ENV_MARKERS = ("ModuleNotFoundError", "ImportError", "ERROR collecting", "error during collection", "No module named")


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Report:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, item_id: int, name: str, ok: bool, evidence: list[str], details: str) -> None:
        self.items.append(
            {
                "id": item_id,
                "name": name,
                "passed": bool(ok),
                "evidence": evidence,
                "details": details,
            }
        )

    def finish(self) -> dict[str, Any]:
        return {
            "schema": "sdd-acceptance/v1",
            "passed": all(item["passed"] for item in self.items),
            "items": self.items,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    report = Report()

    summary = load_json(run_dir / "summary.json", {}) or {}
    commands = (run_dir / "commands.log").read_text(encoding="utf-8") if (run_dir / "commands.log").exists() else ""
    db_stats = load_json(run_dir / "db-stats.json", {}) or {}
    index_v2 = load_json(run_dir / "index-v2.json", {}) or {}
    assert_v1 = load_json(run_dir / "assert-v1.json", {}) or {}
    assert_v2 = load_json(run_dir / "assert-v2.json", {}) or {}
    context_v1 = load_json(run_dir / "context-v1.json", {}) or {}
    context_v2 = load_json(run_dir / "context-v2.json", {}) or {}
    state_save = load_json(run_dir / "state-save.json", {}) or {}
    state_input = load_json(run_dir / "state-save-input.json", {}) or {}
    state_after = load_json(run_dir / "state-after-restart.json", {}) or {}
    resume = load_json(run_dir / "resume-context.json", {}) or {}
    before_target = load_json(run_dir / "before-target.result.json", {}) or {}
    before_regression = load_json(run_dir / "before-regression.result.json", {}) or {}
    after_target = load_json(run_dir / "after-target.result.json", {}) or {}
    after_regression = load_json(run_dir / "after-regression.result.json", {}) or {}

    # 1. runnable
    required_cmds = [
        "seekdb_server.sh reset",
        "pc_server.sh start",
        "index --workspace",
        "context --workspace",
        "before-target",
        "state-save",
        "pc_server.sh restart",
        "state-load",
    ]
    missing_cmds = [item for item in required_cmds if item not in commands]
    runnable_evidence = [
        "commands.log",
        "seekdb-reset.log",
        "seekdb-status.txt",
        "context-v2.json",
        "db-stats.json",
        "before-target.log",
        "after-target.log",
        "state-after-restart.json",
    ]
    runnable = not missing_cmds and all((run_dir / name).exists() for name in runnable_evidence)
    report.add(
        1,
        "能够运行",
        runnable,
        [str(run_dir / name) for name in runnable_evidence],
        "按脚本完成初始化、导入、上下文、测试与状态读取" if runnable else f"缺失命令或文件: {missing_cmds}",
    )

    # 2. MiniMax actually participated
    records: list[dict[str, Any]] = []
    record_path = run_dir / "minimax" / "dev-record.jsonl"
    if record_path.exists():
        for line in record_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    live = [record for record in records if record.get("mode") == "minimax" and record.get("applied")]
    applied_patch = run_dir / "minimax" / "applied.patch"
    prompt_file = run_dir / "minimax" / "prompt.md"
    response_files = sorted((run_dir / "minimax").glob("response-*.txt"))
    patch_hash_ok = False
    if live and applied_patch.exists():
        patch_hash_ok = sha256_file(applied_patch) == live[-1].get("patch_sha256")
    usage_ok = bool(live and isinstance(live[-1].get("usage"), dict) and live[-1]["usage"])
    minimax_ok = bool(live) and patch_hash_ok and usage_ok and prompt_file.exists() and bool(response_files)
    reason = "存在 mode=minimax 且成功应用的记录"
    if not live:
        reason = "没有 mode=minimax 的实际调用记录（replay 不计入必做项）"
    elif not patch_hash_ok:
        reason = "applied.patch 与开发记录中的 patch_sha256 不一致"
    elif not usage_ok:
        reason = "开发记录缺少 usage"
    report.add(
        2,
        "MiniMax 实际参与",
        minimax_ok,
        [str(record_path), str(applied_patch), str(prompt_file), *map(str, response_files)],
        reason,
    )

    # 3. context correct + spec update
    v1_specs = {item.get("spec_id") for item in context_v1.get("specs", [])}
    v2_specs = {item.get("spec_id") for item in context_v2.get("specs", [])}
    v2_text = "\n".join(item.get("text", "") for item in context_v2.get("specs", []))
    context_ok = (
        assert_v1.get("passed") is True
        and assert_v2.get("passed") is True
        and "SPEC-API-013" not in v1_specs
        and "SPEC-API-013" in v2_specs
        and "包含截止当天" in v2_text
    )
    source_checks: list[str] = []
    sources_ok = True
    for item in context_v2.get("required_sources", []):
        rel = item.get("path")
        expected = item.get("sha256")
        if not rel or not expected:
            continue
        found = False
        for root_name in ("workspace-before", "workspace-after"):
            candidate = run_dir / root_name / rel
            if candidate.exists() and sha256_file(candidate) == expected:
                found = True
                source_checks.append(f"{root_name}/{rel}")
                break
        if not found:
            sources_ok = False
            source_checks.append(f"MISSING {rel}")
    report.add(
        3,
        "上下文正确且规格更新生效",
        context_ok and sources_ok,
        [str(run_dir / "context-v1.json"), str(run_dir / "context-v2.json"), str(run_dir / "assert-v2.json")],
        "v1 不含 SPEC-API-013，v2 含 SPEC-API-013 与‘包含截止当天’，来源可回查"
        if context_ok and sources_ok
        else f"context_ok={context_ok} sources_ok={sources_ok} sources={source_checks}",
    )

    # 4. database actually participates
    db_ok = (
        int(db_stats.get("sources", 0)) >= 10
        and int(db_stats.get("chunks", 0)) > 0
        and int(db_stats.get("terms", 0)) > 0
        and int(index_v2.get("indexed", 0)) == 1
        and int(index_v2.get("skipped", 0)) >= 9
        and (run_dir / "db-queries.log").exists()
        and "FROM terms" in (run_dir / "db-queries.log").read_text(encoding="utf-8", errors="replace")
    )
    report.add(
        4,
        "数据库实际参与",
        db_ok,
        [str(run_dir / "db-stats.json"), str(run_dir / "db-queries.log"), str(run_dir / "index-v2.json")],
        f"sources={db_stats.get('sources')} chunks={db_stats.get('chunks')} terms={db_stats.get('terms')} "
        f"index_v2={index_v2.get('indexed')} reindexed/{index_v2.get('skipped')} skipped",
    )

    # 5. state reuse
    state_ok = (
        bool(state_save.get("artifact_id"))
        and state_after.get("task_id") == state_input.get("task_id")
        and state_after.get("done") == state_input.get("done")
        and state_after.get("todo") == state_input.get("todo")
        and state_after.get("verifications") == state_input.get("verifications")
        and resume.get("progress", {}).get("resumed_from_powercontext") is True
        and resume.get("progress", {}).get("done") == state_input.get("done")
        and (run_dir / "pc-after-restart.txt").exists()
    )
    report.add(
        5,
        "状态能够复用",
        state_ok,
        [
            str(run_dir / "state-save.json"),
            str(run_dir / "state-after-restart.json"),
            str(run_dir / "resume-context.json"),
            str(run_dir / "pc-after-restart.txt"),
        ],
        "重启 PowerContext 与新进程后读回 done/todo/verifications，并注入 --resume 上下文"
        if state_ok
        else "状态保存/重启读回字段不一致",
    )

    # 6. code modification effective
    def test_ok(result: dict[str, Any], expect_pass: bool) -> bool:
        if not result:
            return False
        if expect_pass:
            return result.get("exit_code") == 0 and result.get("summary", {}).get("passed", 0) >= 1
        return (
            result.get("exit_code", 0) != 0
            and result.get("classification") == "test_failure"
            and result.get("summary", {}).get("failed", 0) >= 1
        )

    before_log = run_dir / "before-target.log"
    before_text = before_log.read_text(encoding="utf-8", errors="replace") if before_log.exists() else ""
    tests_identical = _tree_hashes(run_dir / "workspace-before" / "tests") == _tree_hashes(
        run_dir / "workspace-after" / "tests"
    )
    code_diff = run_dir / "code-diff.patch"
    code_ok = (
        test_ok(before_target, False)
        and test_ok(before_regression, True)
        and test_ok(after_target, True)
        and test_ok(after_regression, True)
        and not any(marker in before_text for marker in ENV_MARKERS)
        and tests_identical
        and code_diff.exists()
        and code_diff.stat().st_size > 0
    )
    report.add(
        6,
        "代码修改有效",
        code_ok,
        [
            str(run_dir / "before-target.log"),
            str(run_dir / "before-regression.log"),
            str(run_dir / "after-target.log"),
            str(run_dir / "after-regression.log"),
            str(code_diff),
        ],
        "修改前目标测试因断言失败，回归通过；修改后目标+回归通过；测试文件未改动"
        if code_ok
        else "测试结果、失败类型、测试文件一致性或补丁不满足要求",
    )

    result = report.finish()
    result["run_dir"] = str(run_dir)
    result["summary"] = summary
    out = Path(args.out) if args.out else run_dir / "acceptance.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["items"]:
            mark = "PASS" if item["passed"] else "FAIL"
            print(f"[{mark}] {item['id']}. {item['name']}: {item['details']}")
        print(f"OVERALL: {'PASS' if result['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


if __name__ == "__main__":
    raise SystemExit(main())
