#!/usr/bin/env python3
"""End-to-end validation: import -> context -> spec update -> MiniMax -> tests -> state -> restart.

Every step is recorded in ``commands.log`` with its command, cwd, exit code and log
file, so the evidence can be audited without trusting this script.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "bin" / "python"
PC_SCRIPT = ROOT / "scripts" / "pc_server.sh"
TASK_FILE = ROOT / "validation" / "task.md"
TASK_ID = "taskhub-due-before"
BASELINE = ROOT / "demo" / "baseline"
BUSINESS = ROOT / "demo" / "business"


class Recorder:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.commands = run_dir / "commands.log"
        self.commands.write_text("", encoding="utf-8")

    def run(
        self,
        name: str,
        command: list[str],
        log_name: str,
        *,
        stdout_name: str | None = None,
        cwd: Path | None = None,
        timeout: int = 900,
    ) -> dict[str, Any]:
        log_path = self.run_dir / log_name
        started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        started_perf = time.perf_counter()
        with self.commands.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {name}\n$ {' '.join(command)}\n")
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd or ROOT),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\nTIMEOUT after {timeout}s\n"
            exit_code = 124
        except OSError as exc:
            stdout, stderr, exit_code = "", f"{exc}\n", 127
        duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
        log_path.write_text(
            "\n".join(
                [
                    f"# step: {name}",
                    f"# command: {' '.join(command)}",
                    f"# cwd: {cwd or ROOT}",
                    f"# started_at: {started}",
                    f"# duration_ms: {duration_ms}",
                    f"# exit_code: {exit_code}",
                    "#",
                    stdout,
                    stderr,
                ]
            ),
            encoding="utf-8",
        )
        if stdout_name:
            (self.run_dir / stdout_name).write_text(stdout, encoding="utf-8")
        with self.commands.open("a", encoding="utf-8") as handle:
            handle.write(f"exit_code={exit_code} duration_ms={duration_ms} log={log_name}\n")
            if stdout_name:
                handle.write(f"stdout={stdout_name}\n")
        return {
            "name": name,
            "command": " ".join(command),
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "log": log_name,
        }


def sdd(*args: str) -> list[str]:
    return [
        str(PY),
        "-m",
        "sdd_context",
        "--seekdb-host", os.environ.get("SEEKDB_HOST", "127.0.0.1"),
        "--seekdb-port", os.environ.get("SEEKDB_PORT", "2893"),
        "--seekdb-db", os.environ.get("SEEKDB_DATABASE", "sdd"),
        "--query-log", str(RUN_DIR / "db-queries.log"),
        *args,
    ]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def copy_workspace(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.sqlite3"),
    )


def make_patch(before: Path, after: Path, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sdd-patch-") as tmp:
        tmp_path = Path(tmp)
        shutil.copytree(before, tmp_path / "a")
        shutil.copytree(after, tmp_path / "b")
        completed = subprocess.run(
            ["diff", "-ruN", "-x", "__pycache__", "-x", "*.pyc", "a", "b"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        output.write_text(completed.stdout, encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full SDD validation demo")
    parser.add_argument("--mode", choices=("auto", "minimax", "replay"), default="auto")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args()

    load_env_file(ROOT / ".env")
    os.environ.setdefault("SEEKDB_HOST", "127.0.0.1")
    os.environ.setdefault("SEEKDB_PORT", "2893")
    os.environ.setdefault("SEEKDB_DATABASE", "sdd")
    os.environ.setdefault("POWERCONTEXT_URL", f"http://127.0.0.1:{os.environ.get('POWERCONTEXT_PORT', '8093')}")
    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S")
    global RUN_DIR
    RUN_DIR = ROOT / "evidence" / f"run-{run_id}"
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "minimax").mkdir(parents=True, exist_ok=True)
    runtime = ROOT / ".runtime" / f"demo-{run_id}"
    runtime.mkdir(parents=True, exist_ok=True)
    workspace = runtime / "workspace"
    recorder = Recorder(RUN_DIR)
    started_at = utc_now()

    mode = args.mode
    if mode == "auto":
        mode = "minimax" if os.environ.get("MINIMAX_API_KEY") else "replay"

    def step(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return recorder.run(*args, **kwargs)

    # 0. environment ---------------------------------------------------------
    step("env-check", ["bash", str(ROOT / "scripts" / "bootstrap.sh"), "--check"], "env-check.log")
    step("seekdb-reset", ["bash", str(ROOT / "scripts" / "seekdb_server.sh"), "reset"], "seekdb-reset.log")
    step("seekdb-status", ["bash", str(ROOT / "scripts" / "seekdb_server.sh"), "status"], "seekdb-status.txt")
    step("pc-start", ["bash", str(PC_SCRIPT), "start"], "pc-start.log")
    step("pc-status-before", ["bash", str(PC_SCRIPT), "status"], "pc-status-before.txt")

    # 1. workspace + import v1 ----------------------------------------------
    copy_workspace(BASELINE, workspace)
    step("index-v1", sdd("index", "--workspace", str(workspace)), "index-v1.log", stdout_name="index-v1.json")
    step(
        "context-v1",
        sdd(
            "context",
            "--workspace", str(workspace),
            "--task-file", str(TASK_FILE),
            "--task-id", TASK_ID,
            "--out", str(RUN_DIR / "context-v1.json"),
            "--md", str(RUN_DIR / "context-v1.md"),
        ),
        "context-v1.log",
    )
    step(
        "assert-v1",
        [
            str(PY), str(ROOT / "scripts" / "assert_context.py"),
            "--context", str(RUN_DIR / "context-v1.json"),
            "--forbid-spec", "SPEC-API-013",
            "--require-code", "app/store.py::list_tasks",
            "--require-test", "tests/test_due_before.py::test_due_before_includes_boundary_day",
            "--out", str(RUN_DIR / "assert-v1.json"),
        ],
        "assert-v1.log",
    )

    # 2. spec update + re-import --------------------------------------------
    step(
        "spec-update",
        ["patch", "-p1", "-d", str(workspace), "-i", str(ROOT / "patches" / "0002-spec-due-before.patch")],
        "spec-update.log",
    )
    step("index-v2", sdd("index", "--workspace", str(workspace)), "index-v2.log", stdout_name="index-v2.json")
    step(
        "context-v2",
        sdd(
            "context",
            "--workspace", str(workspace),
            "--task-file", str(TASK_FILE),
            "--task-id", TASK_ID,
            "--out", str(RUN_DIR / "context-v2.json"),
            "--md", str(RUN_DIR / "context-v2.md"),
        ),
        "context-v2.log",
    )
    step(
        "assert-v2",
        [
            str(PY), str(ROOT / "scripts" / "assert_context.py"),
            "--context", str(RUN_DIR / "context-v2.json"),
            "--require-spec", "SPEC-API-013",
            "--require-text", "包含截止当天",
            "--require-code", "app/store.py::list_tasks",
            "--require-test", "tests/test_due_before.py::test_due_before_includes_boundary_day",
            "--out", str(RUN_DIR / "assert-v2.json"),
        ],
        "assert-v2.log",
    )
    copy_workspace(workspace, RUN_DIR / "workspace-before")

    # 3. before tests --------------------------------------------------------
    before_target = step(
        "before-target",
        sdd(
            "test",
            "--workspace", str(workspace),
            "--target", "tests/test_due_before.py",
            "--log", str(RUN_DIR / "before-target.log"),
            "--label", "before-target",
        ),
        "before-target.cli.log",
        stdout_name="before-target.result.json",
    )
    before_regression = step(
        "before-regression",
        sdd(
            "test",
            "--workspace", str(workspace),
            "--target", "tests/test_tasks_regression.py",
            "--log", str(RUN_DIR / "before-regression.log"),
            "--label", "before-regression",
        ),
        "before-regression.cli.log",
        stdout_name="before-regression.result.json",
    )

    # 4. MiniMax / replay ----------------------------------------------------
    if mode == "minimax":
        minimax_args = [
            "minimax",
            "--workspace", str(workspace),
            "--context", str(RUN_DIR / "context-v2.json"),
            "--patch-out", str(RUN_DIR / "minimax" / "applied.patch"),
            "--evidence-dir", str(RUN_DIR / "minimax"),
        ]
    else:
        minimax_args = [
            "minimax",
            "--workspace", str(workspace),
            "--context", str(RUN_DIR / "context-v2.json"),
            "--patch-out", str(RUN_DIR / "minimax" / "applied.patch"),
            "--evidence-dir", str(RUN_DIR / "minimax"),
            "--patch-file", str(ROOT / "patches" / "0001-due-before-filter.patch"),
        ]
    minimax_result = step("minimax", sdd(*minimax_args), "minimax.cli.log", stdout_name="minimax.result.json")
    (RUN_DIR / "mode.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "minimax_live": mode == "minimax",
                "minimax_exit_code": minimax_result["exit_code"],
                "note": "replay is not evidence of MiniMax participation",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    copy_workspace(workspace, RUN_DIR / "workspace-after")

    # 5. after tests + diff --------------------------------------------------
    after_target = step(
        "after-target",
        sdd(
            "test",
            "--workspace", str(workspace),
            "--target", "tests/test_due_before.py",
            "--log", str(RUN_DIR / "after-target.log"),
            "--label", "after-target",
        ),
        "after-target.cli.log",
        stdout_name="after-target.result.json",
    )
    after_regression = step(
        "after-regression",
        sdd(
            "test",
            "--workspace", str(workspace),
            "--target", "tests/test_tasks_regression.py",
            "--log", str(RUN_DIR / "after-regression.log"),
            "--label", "after-regression",
        ),
        "after-regression.cli.log",
        stdout_name="after-regression.result.json",
    )
    make_patch(BASELINE / "app", workspace / "app", RUN_DIR / "code-diff.patch")
    make_patch(BASELINE / "specs", workspace / "specs", RUN_DIR / "spec-diff.patch")

    # 6. state save + restart + resume --------------------------------------
    state_input = {
        "schema": "sdd-task-state/v1",
        "task_id": TASK_ID,
        "status": "implemented" if after_target.get("exit_code") == 0 else "partial",
        "workspace": str(workspace),
        "context_sha256": read_json(RUN_DIR / "context-v2.json", {}).get("context_sha256"),
        "done": [
            "导入 specs v1 并生成不含 SPEC-API-013 的上下文",
            "更新规格到 v2 并重新导入（仅 spec 文件重建索引）",
            f"以 {mode} 模式生成并应用代码补丁",
            "运行修改前目标测试与回归测试并记录退出码",
            "运行修改后目标测试与回归测试并记录退出码",
        ],
        "todo": ["评审按 README 从干净环境复跑", "如后续规格再变更，重新导入并更新任务状态"],
        "verifications": [
            {
                "name": item["name"].replace(".result.json", ""),
                "exit_code": read_json(RUN_DIR / f"{item['name']}.result.json", {}).get("exit_code"),
                "summary": read_json(RUN_DIR / f"{item['name']}.result.json", {}).get("summary", {}).get("text"),
            }
            for item in [before_target, before_regression, after_target, after_regression]
        ],
        "next_step": "评审复跑；若规格变化则重新导入并重新生成上下文",
        "saved_at": utc_now(),
        "saved_at_ns": time.time_ns(),
    }
    (RUN_DIR / "state-save-input.json").write_text(json.dumps(state_input, ensure_ascii=False, indent=2), encoding="utf-8")
    step(
        "state-save",
        sdd("state-save", "--state-file", str(RUN_DIR / "state-save-input.json"), "--reason", "demo before restart"),
        "state-save.log",
        stdout_name="state-save.json",
    )
    step("pc-restart", ["bash", str(PC_SCRIPT), "restart"], "pc-restart.log")
    step("pc-after-restart", ["bash", str(PC_SCRIPT), "status"], "pc-after-restart.txt")
    step(
        "state-load",
        sdd("state-load", "--task-id", TASK_ID),
        "state-load.log",
        stdout_name="state-after-restart.json",
    )
    step(
        "resume-context",
        sdd(
            "context",
            "--workspace", str(workspace),
            "--task-file", str(TASK_FILE),
            "--task-id", TASK_ID,
            "--resume",
            "--out", str(RUN_DIR / "resume-context.json"),
            "--md", str(RUN_DIR / "resume-context.md"),
        ),
        "resume-context.log",
    )
    step("db-stats", sdd("db-stats"), "db-stats.log", stdout_name="db-stats.json")

    # 7. summary + acceptance ------------------------------------------------
    summary = {
        "schema": "sdd-run-summary/v1",
        "run_id": run_id,
        "mode": mode,
        "minimax_live": mode == "minimax",
        "task_id": TASK_ID,
        "started_at": started_at,
        "finished_at": utc_now(),
        "git_commit": _git_commit(),
        "context_v1_sha256": read_json(RUN_DIR / "context-v1.json", {}).get("context_sha256"),
        "context_v2_sha256": read_json(RUN_DIR / "context-v2.json", {}).get("context_sha256"),
        "before": {
            "target": read_json(RUN_DIR / "before-target.result.json", {}),
            "regression": read_json(RUN_DIR / "before-regression.result.json", {}),
        },
        "after": {
            "target": read_json(RUN_DIR / "after-target.result.json", {}),
            "regression": read_json(RUN_DIR / "after-regression.result.json", {}),
        },
        "state_save": read_json(RUN_DIR / "state-save.json", {}),
        "seekdb": {
            "host": os.environ.get("SEEKDB_HOST"),
            "port": os.environ.get("SEEKDB_PORT"),
            "database": os.environ.get("SEEKDB_DATABASE"),
        },
        "db": read_json(RUN_DIR / "db-stats.json", {}),
        "minimax": read_json(RUN_DIR / "minimax.result.json", {}),
        "acceptance": str(RUN_DIR / "acceptance.json"),
    }
    (RUN_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    acceptance = step(
        "acceptance",
        [str(PY), str(ROOT / "scripts" / "verify_acceptance.py"), "--run-dir", str(RUN_DIR), "--out", str(RUN_DIR / "acceptance.json")],
        "acceptance.log",
    )
    print(f"run_dir: {RUN_DIR}")
    print(f"mode: {mode} (MiniMax live: {mode == 'minimax'})")
    print((RUN_DIR / "acceptance.log").read_text(encoding="utf-8", errors="replace"))
    if acceptance["exit_code"] != 0:
        print("ACCEPTANCE FAILED; see acceptance.json for the exact missing evidence", file=sys.stderr)
    return 0 if acceptance["exit_code"] == 0 else 1


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout.strip() or None
    except OSError:
        return None


RUN_DIR: Path


if __name__ == "__main__":
    raise SystemExit(main())
