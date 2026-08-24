from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/publish-release.sh"


def test_publish_script_is_valid_and_help_is_non_mutating():
    assert SCRIPT.is_file()
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
    )
    assert result.returncode == 0
    assert "--publish" in result.stdout
    assert "自动创建 annotated tag" in result.stdout
