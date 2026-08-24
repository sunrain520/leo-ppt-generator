from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = REPO_ROOT / "skills/leo-ppt-generator/runtime/src"


def invoke(*args: str):
    command = [sys.executable, "-m", "leo_ppt_generator", *args]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(CLI_ROOT),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    stream = result.stdout if result.stdout else result.stderr
    return result.returncode, json.loads(stream)


def test_cli_protocol_routes_and_worker_gate_do_not_depend_on_display_text(tmp_path):
    code, routed = invoke("route", "--input-kind", "image-deck", "--editable", "--upgrade", "--pages", "1,3")
    assert code == 0
    assert routed["protocol"] == "leo-ppt-machine/v1"
    assert routed["route"] == "upgrade-selected"
    run = tmp_path / "run"
    code, _created = invoke("run", "create", "--run-dir", str(run), "--route", "generate", "--runtime-identity", "fixture-runtime")
    assert code == 0
    code, _advanced = invoke("run", "advance", "--run-dir", str(run), "--expected-revision", "0", "--stage", "image.prepare")
    assert code == 0
    code, next_action = invoke("run", "next", "--run-dir", str(run), "--page-count", "2")
    assert code == 2
    assert next_action["reason_code"] == "worker_capability_unavailable"
    assert next_action["next_action"]["kind"] == "blocked"


def test_unknown_protocol_route_and_revision_fail_closed(tmp_path):
    run = tmp_path / "run"
    invoke("run", "create", "--run-dir", str(run), "--route", "generate", "--runtime-identity", "fixture-runtime")
    code, bad = invoke("run", "advance", "--run-dir", str(run), "--expected-revision", "9", "--stage", "image.prepare")
    assert code == 2
    assert bad["reason_code"] == "revision_conflict"
    code, bad_route = invoke("doctor", "--route", "arbitrary", "--json")
    assert code == 2
    assert bad_route["reason_code"] == "unknown_route"


def test_auth_add_rejects_non_tty_without_echoing_secret():
    secret = "secret-that-must-not-appear"
    command = [
        sys.executable,
        "-m",
        "leo_ppt_generator",
        "auth",
        "add",
        "--provider",
        "openai",
        "--json",
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(CLI_ROOT),
        },
        input=secret,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["reason_code"] == "credential_tty_required"
    assert secret not in result.stdout + result.stderr


def test_auth_status_is_versioned_and_never_returns_secret(monkeypatch):
    secret = "status-secret-must-not-appear"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    code, status = invoke("auth", "status", "--provider", "openai", "--json")

    assert code == 0
    assert status["protocol"] == "leo-ppt-credential/v1"
    assert status["credential_ref"] == "env:OPENAI_API_KEY"
    assert secret not in json.dumps(status)


def test_config_status_is_versioned_and_side_effect_free(tmp_path, monkeypatch):
    """`leo-ppt config status` 输出 leo-ppt-config/v1 且不修改任何文件。"""
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ATLASCLOUD_API_KEY", raising=False)

    code, payload = invoke("config", "status", "--json")
    assert code == 0
    report = payload["report"]
    assert report["protocol"] == "leo-ppt-config/v1"
    assert report["schema_version"] == 1
    assert report["status"] in {
        "not_configured",
        "configured_unverified",
        "ready",
        "degraded",
        "invalid",
    }
    assert report["execution_eligibility"] in {"allowed", "retryable", "blocked"}
    assert report["readiness_scope"]["route"] == "generate"
    # status 是只读操作：LEO_PPT_HOME 下不得产生任何文件。
    assert list(tmp_path.iterdir()) == []


def test_config_status_with_environment_credential_is_configured_unverified(
    tmp_path, monkeypatch
):
    """env 引用存在时 status 返回 configured_unverified 而非 blocked。"""
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-integration-test")

    code, payload = invoke("config", "status", "--json")
    assert code == 0
    report = payload["report"]
    assert report["status"] in {"not_configured", "configured_unverified"}
    if report["status"] == "configured_unverified":
        assert report["execution_eligibility"] == "allowed"
        assert report["installation_readiness"] == "usable_unverified"
        assert report["readiness_scope"]["route"] == "generate"
        assert "generate" in report["readiness_scope"]["missing_capabilities"]
