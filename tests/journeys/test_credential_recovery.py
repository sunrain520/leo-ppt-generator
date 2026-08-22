"""通过公开 CLI 验证凭据丢失、恢复和泄露边界。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = ROOT / "skills/leo-ppt-generator/runtime/src"
SECRET_NAMES = ("OPENAI_API_KEY", "ATLASCLOUD_API_KEY", "PADDLE_OCR_TOKEN")


def _environment(home: Path, **values: str) -> dict[str, str]:
    environment = {
        **os.environ,
        "HOME": str(home),
        "LEO_PPT_HOME": str(home / "leo-home"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(CLI_ROOT),
    }
    for name in SECRET_NAMES:
        environment.pop(name, None)
    environment.update(values)
    return environment


def _invoke(
    home: Path,
    *arguments: str,
    stdin: str | None = None,
    **values: str,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        [sys.executable, "-m", "leo_ppt_generator", *arguments],
        cwd=ROOT,
        env=_environment(home, **values),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout.strip() or result.stderr.strip()
    payload = json.loads(output.splitlines()[-1])
    return result, payload


def test_non_tty_add_rejects_before_reading_or_echoing_secret(tmp_path: Path):
    secret = "journey-secret-must-never-echo-91A7"

    result, payload = _invoke(
        tmp_path,
        "auth",
        "add",
        "--provider",
        "openai",
        "--json",
        stdin=secret,
    )

    assert result.returncode == 2
    assert payload["reason_code"] == "credential_tty_required"
    assert secret not in result.stdout + result.stderr


def test_revoked_reference_fails_stably_and_same_provider_recovers(tmp_path: Path):
    contract = tmp_path / "run-input/backend.json"
    contract.parent.mkdir()
    original_secret = "journey-openai-original-4F2C"

    created_result, created = _invoke(
        tmp_path,
        "backend",
        "create",
        "--provider",
        "openai",
        "--mode",
        "generate",
        "--output",
        str(contract),
        OPENAI_API_KEY=original_secret,
    )
    frozen_hash = hashlib.sha256(contract.read_bytes()).hexdigest()
    missing_result, missing = _invoke(
        tmp_path,
        "upstream",
        "--backend-contract",
        str(contract),
        "codex-ppt",
        "--",
        "image",
        "generate",
        "--prompt",
        "fixture",
        "--output",
        str(tmp_path / "missing.png"),
    )
    repeated_result, repeated = _invoke(
        tmp_path,
        "upstream",
        "--backend-contract",
        str(contract),
        "codex-ppt",
        "--",
        "image",
        "generate",
        "--prompt",
        "fixture",
        "--output",
        str(tmp_path / "repeated.png"),
    )
    restored_result, restored = _invoke(
        tmp_path,
        "backend",
        "validate",
        str(contract),
        OPENAI_API_KEY="journey-openai-restored-8B1D",
    )

    assert created_result.returncode == 0
    assert created["contract"]["credential_ref"] == "env:OPENAI_API_KEY"
    assert missing_result.returncode == repeated_result.returncode == 2
    assert missing["status"] == repeated["status"] == "blocked"
    assert repeated["reason_code"] == missing["reason_code"]
    assert missing["reason_code"] == "credential_reference_unavailable"
    assert missing["next_action"]["kind"] == "inspect_reason_code"
    assert restored_result.returncode == 0
    assert restored["credential_reference_status"] == "available"
    assert restored["next_action"]["kind"] == "create_run"
    assert hashlib.sha256(contract.read_bytes()).hexdigest() == frozen_hash


def test_new_secret_does_not_mutate_frozen_contract_or_leak_to_artifacts(tmp_path: Path):
    contract = tmp_path / "reports/backend.json"
    contract.parent.mkdir()
    first = "journey-first-secret-7719"
    second = "journey-second-secret-8820"

    _invoke(
        tmp_path,
        "backend",
        "create",
        "--provider",
        "openai",
        "--mode",
        "generate",
        "--output",
        str(contract),
        OPENAI_API_KEY=first,
    )
    before = contract.read_bytes()
    _invoke(
        tmp_path,
        "backend",
        "validate",
        str(contract),
        OPENAI_API_KEY=second,
    )

    assert contract.read_bytes() == before
    serialized = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert first not in serialized
    assert second not in serialized
    payload = json.loads(contract.read_text(encoding="utf-8"))
    assert payload["credential_ref"] == "env:OPENAI_API_KEY"
    assert set(payload).isdisjoint({"api_key", "secret", "token", "password"})
