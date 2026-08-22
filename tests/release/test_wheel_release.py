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


def _cleanup_release_debris() -> None:
    for path in (
        RUNTIME / "build",
        RUNTIME / "src/leo_ppt_generator_runtime.egg-info",
    ):
        if path.is_dir():
            shutil.rmtree(path)


def _build_wheel(tmp_path: Path) -> Path:
    source = tmp_path / "runtime"
    shutil.copytree(
        RUNTIME,
        source,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo", "build", "dist", "*.egg-info"
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
    # setuptools 可能在 checkout 的 runtime 旁写入 build/egg-info；发布测试
    # 必须在断言和退出前恢复 source tree 的 clean inventory。
    _cleanup_release_debris()
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_source_tree_has_no_release_debris():
    _cleanup_release_debris()
    debris = []
    for path in (ROOT / "skills/leo-ppt-generator").rglob("*"):
        if (
            path.is_dir()
            and (
                path.name in {"__pycache__", "build", "dist", "third_party"}
                or path.name.endswith(".egg-info")
            )
        ) or (path.is_file() and path.suffix in {".pyc", ".pyo"}):
            debris.append(path.relative_to(ROOT).as_posix())
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
