"""Run pytest with reproducible logs and machine-readable summaries."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ENV_ERROR_MARKERS = (
    "ModuleNotFoundError",
    "ImportError",
    "ERROR collecting",
    "error during collection",
    "No module named",
)


def run_pytest(
    workspace: str | Path,
    targets: Sequence[str],
    log_path: str | Path,
    *,
    label: str,
    timeout: int = 300,
) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    log_path = Path(log_path).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *targets]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    started_perf = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "") + f"\nTIMEOUT after {timeout}s\n"
        exit_code = 124
    duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
    summary = parse_summary(output)
    classification = classify(exit_code, output)
    log_path.write_text(
        "\n".join(
            [
                f"# label: {label}",
                f"# command: {' '.join(command)}",
                f"# cwd: {workspace}",
                f"# started_at: {started}",
                f"# duration_ms: {duration_ms}",
                f"# exit_code: {exit_code}",
                f"# classification: {classification}",
                "#",
                output,
            ]
        ),
        encoding="utf-8",
    )
    return {
        "label": label,
        "command": " ".join(command),
        "cwd": str(workspace),
        "started_at": started,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "classification": classification,
        "summary": summary,
        "log": str(log_path),
    }


def parse_summary(output: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for name in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed"):
        match = re.search(rf"(\d+) {name}\b", output)
        if match:
            counts[name] = int(match.group(1))
    if not counts:
        return {"text": "no pytest summary found", **counts}
    ordered = []
    for name in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed"):
        if name in counts:
            ordered.append(f"{counts[name]} {name}")
    return {"text": ", ".join(ordered), **counts}


def classify(exit_code: int, output: str) -> str:
    if exit_code == 0:
        return "pass"
    if any(marker in output for marker in ENV_ERROR_MARKERS):
        return "environment_error"
    if "FAILED " in output or "assert" in output:
        return "test_failure"
    if exit_code == 124:
        return "timeout"
    return "other_error"
