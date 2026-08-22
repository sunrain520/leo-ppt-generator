from __future__ import annotations

import email
import shutil
import subprocess
import sys
from shutil import which
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "skills/leo-ppt-generator/runtime"


def _build_wheel(tmp_path: Path) -> Path:
    source = tmp_path / "runtime"
    shutil.copytree(
        RUNTIME,
        source,
        ignore=shutil.ignore_patterns(
            ".venv", "__pycache__", "*.pyc", "*.pyo", "build", "dist", "*.egg-info"
        ),
    )
    out = tmp_path / "dist"
    uv = which("uv")
    command = (
        [uv, "run", "--with", "build", "--no-project", "python", "-m", "build", "--wheel", "--outdir", str(out), str(source)]
        if uv
        else [sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(source)]
    )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_source_tree_has_no_release_debris():
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "skills/leo-ppt-generator"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    tracked_paths = [
        ROOT / relative_path
        for relative_path in completed.stdout.split("\0")
        if relative_path
    ]
    debris = [
        path.relative_to(ROOT).as_posix()
        for path in tracked_paths
        if path.suffix in {".pyc", ".pyo"}
        or any(
            part in {"__pycache__", "build", "dist", "third_party"}
            or part.endswith(".egg-info")
            for part in path.relative_to(ROOT).parts
        )
    ]
    assert not debris


def test_wheel_inventory_has_runtime_without_skill_or_legacy_entrypoints(tmp_path: Path):
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        lowered = [name.lower() for name in names]
        assert any(name.endswith("leo_ppt_generator/cli.py") for name in names)
        assert any(name.endswith("leo_ppt_generator/schemas/run.schema.json") for name in names)
        assert any("_vendor/codex_ppt/image_gen.py" in name for name in names)
        assert any("_vendor/editable_ppt/editppt/runtime/main.py" in name for name in names)
        assert not any("third_party" in name for name in lowered)
        assert not any(name.endswith(("SKILL.md", ".pyc", ".pyo")) for name in names)
        assert not any("/__pycache__/" in name or "/build/" in name or ".egg-info/" in name for name in lowered)

        entry_name = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        entry_points = archive.read(entry_name).decode("utf-8")
        assert "leo-ppt = leo_ppt_generator.cli:main" in entry_points
        assert "editppt" not in entry_points
        assert "codex-ppt" not in entry_points

        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_name))
        assert metadata["Name"] == "leo-ppt-generator-runtime"
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Requires-Python"] == "<3.13,>=3.12"
