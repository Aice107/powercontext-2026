import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sdd_context.minimax import MiniMaxError, apply_patch, extract_patch, validate_patch_paths

ROOT = Path(__file__).resolve().parents[1]


def test_extract_patch_from_fenced_response():
    response = "Sure.\n```diff\ndiff --git a/app/store.py b/app/store.py\n--- a/app/store.py\n+++ b/app/store.py\n@@ -1 +1 @@\n-x\n+y\n```\n"
    patch = extract_patch(response)
    assert patch.startswith("diff --git")
    assert "+++ b/app/store.py" in patch


def test_patch_cannot_touch_tests_or_specs():
    patch = "--- a/tests/test_due_before.py\n+++ b/tests/test_due_before.py\n@@ -1 +1 @@\n-x\n+y\n"
    with pytest.raises(MiniMaxError):
        validate_patch_paths(patch)


def test_recorded_patch_applies_and_target_tests_pass(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "demo" / "baseline", workspace)
    # apply the spec update first, then the code patch
    subprocess.run(
        ["patch", "-p1", "-i", str(ROOT / "patches" / "0002-spec-due-before.patch")],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    patch_text = (ROOT / "patches" / "0001-due-before-filter.patch").read_text(encoding="utf-8")
    result = apply_patch(workspace, patch_text)
    assert result["applied"] is True
    assert set(result["files"]) == {"app/api.py", "app/store.py"}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests/test_due_before.py"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
