"""安装后绝对 console script 的四条 route 黑盒回归。"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

import pytest
from PIL import Image

from tests.ppt_fixtures import build_editable_page
from tests.release.test_wheel_release import _build_wheel

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "skills/leo-ppt-generator/runtime"


def _write_backend(path: Path, mode: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "fixture",
                "backend_kind": "openai-compatible",
                "model": "fixture-model",
                "mode": mode,
                "credential_source": "host-managed",
                "selection_source": "user-confirmed",
                "capabilities": {
                    "generate": True,
                    "edit": True,
                    "mask": False,
                    "max_reference_images": 4,
                    "execution_owner": "runtime",
                },
                "timeouts": {"backend_api_seconds": 30, "backend_api_retries": 0},
            }
        ),
        encoding="utf-8",
    )
    return path


def _png(path: Path, color: str = "navy") -> Path:
    Image.new("RGB", (160, 90), color).save(path)
    return path


@pytest.fixture(scope="module")
def installed_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("installed-skill")
    wheel = _build_wheel(root)
    assert wheel.is_absolute()
    python = root / ("venv/Scripts/python.exe" if os.name == "nt" else "venv/bin/python")
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--constraint",
            str(
                RUNTIME
                / "constraints"
                / f"py{sys.version_info.major}{sys.version_info.minor}-{sys.platform}-{platform.machine().lower()}.txt"
            ),
            str(wheel),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    cli = root / ("venv/Scripts/leo-ppt.exe" if os.name == "nt" else "venv/bin/leo-ppt")
    assert cli.is_file()
    return cli


def _run(cli: Path, *args: str, expect: str = "completed") -> dict:
    result = subprocess.run([str(cli), *args], text=True, capture_output=True, check=False)
    output = result.stdout.strip() or result.stderr.strip()
    payload = None
    for line in reversed(output.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "status" in candidate:
            payload = candidate
            break
    assert payload is not None, output
    assert payload["status"] == expect, payload
    return payload


def _prepare_editable_page(cli: Path, run: Path, source: Path, page: str = "page_001") -> None:
    prompt_file = run / "worker-prompt.md"
    prompt_file.write_text("build page", encoding="utf-8")
    dispatched = _run(
        cli,
        "editable",
        "dispatch",
        str(run),
        "--page",
        page,
        "--agent-id",
        "installed-worker",
        "--prompt-file",
        str(prompt_file),
        expect="ready",
    )
    worker_dir = Path(dispatched["dispatch"]["worker_dir"])
    _page_pptx, manifest = build_editable_page(source, worker_dir / "page.pptx")
    if manifest != worker_dir / "manifest.json":
        (worker_dir / "manifest.json").write_bytes(manifest.read_bytes())
    (worker_dir / "validation.json").write_text('{"passed": true}\n', encoding="utf-8")
    _run(
        cli,
        "editable",
        "record",
        str(run),
        "--page",
        page,
        "--agent-id",
        "installed-worker",
        expect="ready",
    )


def test_installed_console_script_creates_and_validates_backend_contract(
    installed_cli: Path, tmp_path: Path
):
    contract = tmp_path / "builtin-backend.json"

    created = _run(
        installed_cli,
        "backend",
        "create",
        "--provider",
        "builtin-imagegen",
        "--mode",
        "generate",
        "--output",
        str(contract),
        expect="ready",
    )
    validated = _run(
        installed_cli,
        "backend",
        "validate",
        str(contract),
        expect="ready",
    )

    assert created["contract_path"] == str(contract.resolve())
    assert validated["provider"] == "builtin-imagegen"
    assert validated["credential_reference_status"] == "host_check_required"


def test_installed_console_script_completes_all_four_routes_and_replays(
    installed_cli: Path, tmp_path: Path
):
    # generate
    generate = tmp_path / "generate"
    content = tmp_path / "source.md"
    content.write_text("# Installed route\n", encoding="utf-8")
    generate_backend = _write_backend(tmp_path / "generate-backend.json", "generate")
    _run(installed_cli, "run", "create", "--route", "generate", "--input", str(content), "--output", str(generate), "--backend-contract", str(generate_backend), expect="ready")
    (generate / "work/slides.json").write_text('[{"number": 1, "notes": "note"}]\n', encoding="utf-8")
    source = _png(tmp_path / "source.png")
    _run(installed_cli, "image", "prepare", str(generate), expect="ready")
    _run(installed_cli, "image", "record", str(generate), "--slide", "slide_01", "--result", str(source), expect="ready")
    first = _run(installed_cli, "image", "assemble", str(generate))
    replay = _run(installed_cli, "image", "assemble", str(generate))
    assert replay["idempotency_status"] == "replayed"

    # direct-editable
    direct = tmp_path / "direct"
    edit_backend = _write_backend(tmp_path / "edit-backend.json", "edit")
    _run(installed_cli, "run", "create", "--route", "direct-editable", "--input", str(source), "--output", str(direct), "--backend-contract", str(edit_backend), expect="ready")
    _run(installed_cli, "editable", "prepare", str(direct), expect="ready")
    _prepare_editable_page(installed_cli, direct, source)
    _run(installed_cli, "editable", "finalize", str(direct))

    # 两条 upgrade route 都从 generate delivery 导入 baseline。
    source_pptx = Path(first["pptx"])
    for route in ("upgrade-full", "upgrade-selected"):
        target = tmp_path / route
        _run(installed_cli, "run", "create", "--route", route, "--input", str(source_pptx), "--output", str(target), "--backend-contract", str(edit_backend), "--office-trusted", expect="ready")
        _run(installed_cli, "upgrade", "import-baseline", str(target), "--source-run", str(generate), expect="ready")
        if route == "upgrade-selected":
            # 默认选择页由 run contract 冻结；单页 fixture 足以覆盖 selected route。
            pass
        prepare_args = ["editable", "prepare", str(target)]
        if route == "upgrade-selected":
            prepare_args.extend(["--pages", "1"])
        _run(installed_cli, *prepare_args, expect="ready")
        _prepare_editable_page(installed_cli, target, source)
        _run(installed_cli, "upgrade", "finalize", str(target))
