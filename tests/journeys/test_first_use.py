"""从公开 launcher/CLI 验证首次使用旅程，不绕过产品入口。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "skills/leo-ppt-generator"
CLI_ROOT = BUNDLE / "runtime/src"


def _environment(home: Path, **values: str) -> dict[str, str]:
    environment = {
        **os.environ,
        "HOME": str(home),
        "LEO_PPT_HOME": str(home / "Leo 数据"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(CLI_ROOT),
    }
    for name in ("OPENAI_API_KEY", "ATLASCLOUD_API_KEY", "PADDLE_OCR_TOKEN"):
        environment.pop(name, None)
    environment.update(values)
    return environment


def _payload(result: subprocess.CompletedProcess[str]) -> dict:
    output = result.stdout.strip() or result.stderr.strip()
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionError(output)


def _cli(home: Path, *arguments: str, **values: str) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, "-m", "leo_ppt_generator", *arguments],
        cwd=ROOT,
        env=_environment(home, **values),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, _payload(result)


@pytest.fixture(scope="module")
def bootstrapped_cli(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, dict]:
    home = tmp_path_factory.mktemp("首次 使用")
    result = subprocess.run(
        ["bash", str(BUNDLE / "scripts/leo-bootstrap.sh"), "bootstrap"],
        cwd=ROOT,
        env=_environment(home),
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = _payload(result)
    cli = Path(receipt["cli_reference"])
    assert cli.is_absolute() and cli.is_file()
    assert receipt["protocol"] == "leo-ppt-bootstrap/v1"
    assert receipt["status"] == "ready"
    return home, cli, receipt


def test_bootstrap_to_zero_key_setup_uses_one_public_path(bootstrapped_cli):
    home, cli, receipt = bootstrapped_cli

    setup = subprocess.run(
        [
            str(cli),
            "setup",
            "--route",
            "generate",
            "--host-imagegen",
            "available",
            "--json",
        ],
        cwd=ROOT,
        env=_environment(home),
        text=True,
        capture_output=True,
        check=False,
    )
    report = _payload(setup)

    assert setup.returncode == 0, setup.stderr
    assert receipt["runtime_outcome"] in {"installed", "reused"}
    assert report["protocol"] == "leo-ppt-setup/v1"
    assert report["status"] == "ready"
    assert report["selected_provider"] == "builtin-imagegen"
    assert report["primary_action"] is None


def test_unknown_host_capability_never_becomes_false_ready(tmp_path: Path):
    code, report = _cli(
        tmp_path,
        "setup",
        "--route",
        "generate",
        "--host-imagegen",
        "unknown",
        "--json",
    )

    assert code == 2
    assert report["status"] == "action_required"
    assert report["reason_code"] == "host_image_capability_unknown"
    assert set(report["primary_action"]) == {"id", "command", "verification"}


def test_two_external_providers_require_a_choice(tmp_path: Path):
    code, report = _cli(
        tmp_path,
        "setup",
        "--route",
        "generate",
        "--host-imagegen",
        "unavailable",
        "--json",
        OPENAI_API_KEY="journey-openai",
        ATLASCLOUD_API_KEY="journey-atlas",
    )

    assert code == 2
    assert report["status"] == "choice_required"
    assert report["reason_code"] == "provider_choice_required"
    assert {item["provider"] for item in report["provider_options"]} >= {
        "openai",
        "atlascloud",
    }


def test_mask_and_ocr_are_disclosed_only_when_the_route_needs_them(tmp_path: Path):
    code, mask = _cli(
        tmp_path,
        "setup",
        "--route",
        "generate",
        "--host-imagegen",
        "unavailable",
        "--require-mask",
        "--json",
        OPENAI_API_KEY="journey-openai",
        ATLASCLOUD_API_KEY="journey-atlas",
    )
    _, generate = _cli(
        tmp_path,
        "setup",
        "--route",
        "generate",
        "--host-imagegen",
        "available",
        "--ocr-requirement",
        "editable_text_hints",
        "--json",
    )
    _, editable = _cli(
        tmp_path,
        "setup",
        "--route",
        "direct-editable",
        "--host-imagegen",
        "available",
        "--ocr-requirement",
        "editable_text_hints",
        "--json",
    )

    assert code == 2
    assert {item["provider"] for item in mask["provider_options"]} == {
        "openai",
        "openai-compatible",
    }
    assert generate["optional_services"] == []
    assert editable["optional_services"][0]["service"] == "paddleocr"
    assert editable["optional_services"][0]["required"] is False


def test_public_cli_writes_contract_under_spaces_and_unicode(tmp_path: Path):
    contract = tmp_path / "中文 空格/backend.json"
    contract.parent.mkdir()

    code, created = _cli(
        tmp_path,
        "backend",
        "create",
        "--provider",
        "builtin-imagegen",
        "--mode",
        "generate",
        "--output",
        str(contract),
    )
    validate_code, validated = _cli(
        tmp_path,
        "backend",
        "validate",
        str(contract),
    )

    assert code == validate_code == 0
    assert created["contract_path"] == str(contract.resolve())
    assert validated["status"] == "ready"
    assert validated["provider"] == "builtin-imagegen"
