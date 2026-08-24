from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from leo_ppt_generator import cli
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import ConfigServiceError
from leo_ppt_generator.credentials import CredentialManager, UnsupportedCredentialStore
from PIL import Image

from tests.backend_fixtures import backend_contract
from tests.ppt_fixtures import build_editable_page


def parse(*args: str):
    return cli.build_parser().parse_args(args)


def test_doctor_and_route_envelopes_are_versioned():
    doctor = cli.dispatch(parse("doctor", "--route", "generate", "--json"))
    assert doctor["status"] == "ready"
    assert doctor["protocol"] == cli.PROTOCOL
    assert doctor["config"]["max_concurrent_workers"]["source"] in {
        "default",
        "config.yaml",
        "environment",
    }
    assert doctor["credential_references"]["builtin-imagegen"]["status"] == "host_check_required"
    assert doctor["credential_references"]["paddleocr"]["reference_type"] in {
        "none",
        "environment-reference",
        "os-store-reference",
    }
    assert doctor["readiness"]["worker"]["status"] == "host_check_required"
    assert doctor["readiness"]["manual_acceptance"]["status"] == "required"
    assert doctor["readiness_summary"] == {
        "local_mechanism": "ready",
        "field_execution": "action_required",
        "next_actions": [
            "create_and_validate_backend_contract",
            "verify_worker_capability",
            "run_provider_smoke",
            "record_manual_acceptance",
        ],
    }
    unknown = cli.dispatch(parse("doctor", "--route", "unknown", "--json"))
    assert unknown["status"] == "blocked"
    routed = cli.dispatch(parse("route", "--input-kind", "image", "--editable"))
    assert routed["route"] == "direct-editable"


def test_doctor_reports_invalid_config_without_losing_other_readiness(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("schema_version: 99\n", encoding="utf-8")
    monkeypatch.setenv("LEO_PPT_HOME", str(home))

    for route in ("generate", "direct-editable", "upgrade-full", "upgrade-selected"):
        report = cli.dispatch(parse("doctor", "--route", route, "--json"))
        assert report["status"] == "blocked"
        assert report["reason_code"] == "config_schema_too_new"
        assert report["route"] == route
        assert report["readiness"]["config"]["status"] == "failed"
        assert report["readiness"]["local_runtime"]["status"] == "ready"
        assert report["readiness"]["worker"]["status"] == "host_check_required"
        assert report["readiness_summary"]["local_mechanism"] == "blocked"
        assert report["readiness_summary"]["next_actions"] == ["fix_runtime_config"]
        assert report["config"] == {}
        assert '"schema_version": 99' not in json.dumps(report)


@pytest.mark.parametrize(
    "route,office_status",
    [
        ("generate", "not_required"),
        ("direct-editable", "optional_missing"),
        ("upgrade-full", "optional_missing"),
        ("upgrade-selected", "optional_missing"),
    ],
)
def test_doctor_separates_route_readiness_layers(route, office_status, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    report = cli.dispatch(parse("doctor", "--route", route, "--json"))
    assert report["status"] == "ready"
    assert report["readiness"]["route_contract"]["status"] == "passed"
    assert report["readiness"]["provider"]["status"] == "not_probed"
    assert report["readiness"]["office_viewer"]["status"] == office_status
    assert report["readiness"]["manual_acceptance"]["status"] == "required"


def test_backend_create_and_validate_reports_contract_and_credential_readiness(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        cli, "credential_manager", lambda: CredentialManager(UnsupportedCredentialStore(), {})
    )
    output = tmp_path / "backend.json"
    created = cli.dispatch(
        parse(
            "backend",
            "create",
            "--provider",
            "openai",
            "--mode",
            "generate",
            "--output",
            str(output),
        )
    )
    assert created["reason_code"] == "backend_contract_created"
    assert created["contract_path"] == str(output.resolve())
    assert json.loads(output.read_text(encoding="utf-8")) == created["contract"]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing = cli.dispatch(parse("backend", "validate", str(output)))
    assert missing["reason_code"] == "backend_contract_valid"
    assert missing["credential_reference_status"] == "missing"
    assert missing["next_action"]["kind"] == "configure_credential_reference"

    monkeypatch.setenv("OPENAI_API_KEY", "not-persisted")
    available = cli.dispatch(parse("backend", "validate", str(output)))
    assert available["credential_reference_status"] == "available"
    assert "not-persisted" not in json.dumps(available)

    with pytest.raises(cli.BackendContractError, match="backend_contract_exists"):
        cli.dispatch(
            parse(
                "backend",
                "create",
                "--provider",
                "openai",
                "--mode",
                "generate",
                "--output",
                str(output),
            )
        )


def test_openai_compatible_profile_is_frozen_into_backend_contract(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "test-environment-reference")
    configured = cli.dispatch(
        parse(
            "provider", "configure", "--provider", "openai-compatible",
            "--base-url", "https://proxy.example.com", "--model", "proxy-image-model",
        )
    )
    assert configured["reason_code"] == "provider_profile_configured"
    output = tmp_path / "compatible.json"
    created = cli.dispatch(
        parse(
            "backend", "create", "--provider", "openai-compatible", "--mode", "generate",
            "--output", str(output),
        )
    )
    assert created["contract"]["endpoint_origin"] == "https://proxy.example.com"
    assert created["contract"]["model"] == "proxy-image-model"
    assert created["contract"]["credential_ref"] == "env:OPENAI_API_KEY"


def test_backend_create_auto_selects_configured_provider_and_freezes_decision(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "configured-key")
    ConfigStore(home).compare_and_swap(
        None,
        {
            "schema_version": 1,
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                    "enabled": True,
                    "priority": 1,
                }
            },
        },
    )
    output = tmp_path / "automatic.json"

    created = cli.dispatch(
        parse("backend", "create", "--mode", "generate", "--output", str(output))
    )

    assert created["contract"]["provider"] == "openai"
    assert created["contract"]["selection_source"] == "configured-singleton"
    assert created["contract"]["selection"] == {
        "source": "configured-singleton",
        "priority": 1,
        "config_digest": ConfigStore(home).read().canonical_digest,
    }


def test_provider_priority_and_enabled_commands_change_future_auto_selection(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "configured-key")
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    ConfigStore(home).compare_and_swap(
        None,
        {
            "schema_version": 1,
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                    "enabled": True,
                    "priority": 1,
                },
                "atlascloud": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:ATLASCLOUD_API_KEY",
                    "enabled": True,
                    "priority": 2,
                },
            },
        },
    )

    status = cli.dispatch(parse("config", "status", "--route", "generate", "--json"))
    assert status["selection"]["provider"] == "openai"
    assert status["selection"]["source"] == "configured-priority"

    cli.dispatch(parse("config", "provider", "enabled", "--provider", "openai", "--value", "false", "--json"))
    changed = cli.dispatch(parse("config", "status", "--route", "generate", "--json"))
    assert changed["selection"]["provider"] == "atlascloud"
    assert changed["selection"]["source"] == "configured-singleton"
    assert changed["report"]["selected_provider"] == "atlascloud"

    with pytest.raises(ConfigServiceError, match="provider_profile_invalid"):
        cli.dispatch(
            parse(
                "config",
                "provider",
                "priority",
                "--provider",
                "atlascloud",
                "--value",
                "0",
            )
        )


def test_config_status_blocks_when_enabled_candidates_share_top_priority(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "configured-key")
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    ConfigStore(home).compare_and_swap(
        None,
        {
            "schema_version": 1,
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                    "enabled": True,
                    "priority": 1,
                },
                "atlascloud": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:ATLASCLOUD_API_KEY",
                    "enabled": True,
                    "priority": 1,
                },
            },
        },
    )

    result = cli.dispatch(parse("config", "status", "--route", "generate", "--json"))

    assert result["status"] == "action_required"
    assert result["reason_code"] == "provider_priority_tie"
    assert result["selection"] is None
    assert result["primary_action"]["id"] == "resolve_provider_priority"


def test_run_cli_create_advance_next_status_diagnose_cancel(tmp_path):
    run = tmp_path / "run"
    created = cli.dispatch(parse("run", "create", "--run-dir", str(run), "--route", "generate", "--runtime-identity", "runtime"))
    for field in ("operation_id", "idempotency_status", "safe_to_retry", "state_hash"):
        assert field in created
    assert created["run"]["revision"] == 0
    status = cli.dispatch(parse("run", "status", "--run-dir", str(run)))
    assert status["run"]["stage"] == "created"
    first = cli.dispatch(parse("run", "next", "--run-dir", str(run), "--page-count", "1"))
    assert first["next_action"]["step"] == "image.prepare"
    advanced = cli.dispatch(parse("run", "advance", "--run-dir", str(run), "--expected-revision", "0", "--stage", "image.prepare"))
    for field in ("operation_id", "idempotency_status", "safe_to_retry", "state_hash"):
        assert field in advanced
    assert advanced["safe_to_retry"] is False
    assert advanced["run"]["revision"] == 1
    blocked = cli.dispatch(parse("run", "next", "--run-dir", str(run), "--page-count", "2"))
    assert blocked["status"] == "blocked"
    local = cli.dispatch(parse("run", "next", "--run-dir", str(run), "--page-count", "1"))
    assert local["next_action"]["kind"] == "single_unit_current_agent_allowed"
    diagnosis = cli.dispatch(parse("run", "diagnose", "--run-dir", str(run)))
    assert diagnosis["diagnosis"]["next_action"]["kind"] == "resume"
    cancelled = cli.dispatch(parse("run", "cancel", "--run-dir", str(run), "--expected-revision", "1"))
    assert cancelled["status"] == "cancelled"


def test_run_create_stable_contract_freezes_input_and_backend(tmp_path, monkeypatch):
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    backend = tmp_path / "backend.json"
    backend.write_text(json.dumps(backend_contract()), encoding="utf-8")
    run = tmp_path / "stable-run"
    monkeypatch.setenv("LEO_PPT_RUNTIME_IDENTITY", "runtime-from-host")

    created = cli.dispatch(
        parse(
            "run",
            "create",
            "--route",
            "generate",
            "--input",
            str(source),
            "--output",
            str(run),
            "--backend-contract",
            str(backend),
            "--idempotency-key",
            "request-1",
        )
    )
    assert created["idempotency_status"] == "created"
    assert created["safe_to_retry"] is True
    assert created["operation_id"]
    assert created["state_hash"]
    assert created["run_id"] == created["run"]["run_id"]
    assert created["run"]["runtime_identity"] == "runtime-from-host"
    assert created["run"]["input"]["path"].startswith("input/")

    replay = cli.dispatch(
        parse(
            "run",
            "create",
            "--route",
            "generate",
            "--input",
            str(source),
            "--output",
            str(run),
            "--backend-contract",
            str(backend),
            "--idempotency-key",
            "request-1",
        )
    )
    assert replay["idempotency_status"] == "replayed"
    assert replay["run_id"] == created["run_id"]


def test_runtime_identity_is_loaded_from_unresolved_managed_venv_path(tmp_path, monkeypatch):
    runtime = tmp_path / "runtimes" / "managed-identity"
    executable = runtime / "venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(Path(sys.executable).resolve())
    (runtime / "runtime.json").write_text(
        json.dumps({"runtime_identity": "managed-identity"}), encoding="utf-8"
    )
    monkeypatch.delenv("LEO_PPT_RUNTIME_IDENTITY", raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(executable))

    assert cli._runtime_identity(None) == "managed-identity"


def test_run_status_accepts_stable_positional_run(tmp_path):
    run = tmp_path / "run"
    cli.dispatch(
        parse(
            "run",
            "create",
            "--run-dir",
            str(run),
            "--route",
            "generate",
            "--runtime-identity",
            "runtime",
        )
    )
    status = cli.dispatch(parse("run", "status", str(run), "--json"))
    assert status["run_id"] == status["run"]["run_id"]
    assert status["route"] == "generate"
    assert status["stage"] == "created"
    assert status["artifact_refs"] == []
    assert status["evidence_refs"] == []
    assert status["warnings"] == []
    assert status["blockers"] == []


def test_image_editable_delivery_and_cleanup_cli(tmp_path):
    image_run = tmp_path / "image"
    slides = tmp_path / "slides.json"
    slides.write_text('[{"number": 1, "notes": "n"}]\n', encoding="utf-8")
    source = tmp_path / "source.png"
    Image.new("RGB", (160, 90), "red").save(source)
    cli.dispatch(parse("image", "prepare", "--run-dir", str(image_run), "--slides", str(slides)))
    cli.dispatch(parse("image", "record", "--run-dir", str(image_run), "--number", "1", "--image", str(source), "--backend", "fixture", "--expected-revision", "0", "--operation-id", "image-1"))
    completed = cli.dispatch(parse("image", "finalize", "--run-dir", str(image_run), "--output", str(tmp_path / "image.pptx")))
    assert completed["delivery_type"] == "image"

    editable_run = tmp_path / "editable"
    ready = cli.dispatch(parse("editable", "prepare", "--run-dir", str(editable_run), "--sources", str(source)))
    assert ready["status"] == "ready"
    page, manifest = build_editable_page(source, tmp_path / "page.pptx")
    validation = tmp_path / "validation.json"
    validation.write_text('{"passed": true}\n', encoding="utf-8")
    editable = cli.dispatch(parse("editable", "record", "--run-dir", str(editable_run), "--page", "page_001", "--pptx", str(page), "--validation", str(validation), "--manifest", str(manifest), "--expected-revision", "0", "--operation-id", "editable-1"))
    artifacts = tmp_path / "artifacts.json"
    artifacts.write_text(json.dumps([editable["artifact"]]), encoding="utf-8")
    delivery = cli.dispatch(parse("delivery", "assemble", "--artifacts", str(artifacts), "--output", str(tmp_path / "editable.pptx"), "--selected-pages", "1"))
    assert delivery["delivery_type"] == "editable"

    run = tmp_path / "cleanup-run"
    cli.dispatch(parse("run", "create", "--run-dir", str(run), "--route", "generate", "--runtime-identity", "runtime"))
    (run / "tmp").mkdir()
    (run / "tmp/file.tmp").write_text("x", encoding="utf-8")
    preview = cli.dispatch(parse("cleanup", "--run-dir", str(run), "--dry-run", "--expected-revision", "0"))["preview"]
    preview_path = tmp_path / "preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    applied = cli.dispatch(parse("cleanup", "--run-dir", str(run), "--apply", str(preview_path)))
    assert applied["receipt"]["removed"] == ["tmp/file.tmp"]


def test_auth_cli_rejects_plaintext_api_key_argument():
    with pytest.raises(SystemExit):
        parse("auth", "add", "--provider", "openai", "--api-key", "canary-secret")


def test_config_without_subcommand_is_the_wizard_entrypoint():
    args = parse("config")

    assert args.command == "config"
    assert args.config_command is None


class _ConfigDispatchReport:
    class status:
        value = "configured_unverified"

    reason_code = "provider_verification_not_run"

    def to_dict(self):
        return {"status": self.status.value}


def test_config_change_dispatches_to_service_without_route_argument(monkeypatch):
    class Service:
        def __init__(self):
            self.request = None
            self.selected_provider = None
            self.operation_id = None

        def change(self, request, *, selected_provider, operation_id):
            self.request = request
            self.selected_provider = selected_provider
            self.operation_id = operation_id
            return _ConfigDispatchReport()

    service = Service()
    monkeypatch.setattr(cli, "_config_service", lambda: service)
    service.config_store = type(
        "Store",
        (),
        {"read": lambda self: type("Snapshot", (), {"values": {"provider_profiles": {"openai": {}}}})()},
    )()

    result = cli.dispatch(parse("config", "change", "--provider", "openai"))

    assert service.request.route is None
    assert service.selected_provider == "openai"
    assert service.operation_id == "config-change-openai"
    assert result["status"] == "configured_unverified"


def test_config_repair_dispatches_to_service_repair(monkeypatch):
    class Service:
        def __init__(self):
            self.request = None

        def repair(self, request):
            self.request = request
            return _ConfigDispatchReport()

    service = Service()
    monkeypatch.setattr(cli, "_config_service", lambda *args: service)

    result = cli.dispatch(parse("config", "repair", "--route", "generate"))

    assert service.request.route == "generate"
    assert result["status"] == "configured_unverified"


def test_config_change_without_provider_enters_wizard(monkeypatch):
    class Wizard:
        def run(self, request):
            self.request = request
            return type("Result", (), {"report": _ConfigDispatchReport()})()

    wizard = Wizard()
    monkeypatch.setattr(cli, "_config_wizard", lambda *_, **__: wizard)

    result = cli.dispatch(parse("config", "change"))

    assert wizard.request.route is None
    assert result["status"] == "configured_unverified"



def test_config_change_missing_profile_returns_blocked_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))

    exit_code = cli.main(["config", "change", "--provider", "openai", "--json"])

    response = json.loads(capsys.readouterr().err)
    assert exit_code == 2
    assert response["status"] == "blocked"
    assert response["reason_code"] == "credential_input_channel_unavailable"


def test_config_without_subcommand_dispatches_to_wizard(monkeypatch):
    class Wizard:
        def __init__(self):
            self.request = None

        def run(self, request):
            self.request = request
            return type("Result", (), {"report": _ConfigDispatchReport()})()

    wizard = Wizard()
    monkeypatch.setattr(cli, "_config_wizard", lambda *_, **__: wizard)

    result = cli.dispatch(parse("config"))

    assert wizard.request.route is None
    assert result["status"] == "configured_unverified"


def test_resolve_cli_path_uses_executable_posix_sibling(tmp_path, monkeypatch):
    if cli.os.name == "nt":
        pytest.skip("POSIX console-script permission semantics")
    python = tmp_path / "venv" / "bin" / "python"
    script = python.with_name("leo-ppt")
    script.parent.mkdir(parents=True)
    python.write_text("python", encoding="utf-8")
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(cli.sys, "executable", str(python))
    monkeypatch.delenv("LEO_PPT_CLI_PROG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)

    assert cli._resolve_cli_path(platform_name="posix") == str(script.resolve())


def test_resolve_cli_path_rejects_non_executable_posix_sibling(tmp_path, monkeypatch):
    if cli.os.name == "nt":
        pytest.skip("POSIX console-script permission semantics")
    python = tmp_path / "venv" / "bin" / "python"
    script = python.with_name("leo-ppt")
    script.parent.mkdir(parents=True)
    python.write_text("python", encoding="utf-8")
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)
    monkeypatch.setattr(cli.sys, "executable", str(python))
    monkeypatch.delenv("LEO_PPT_CLI_PROG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)

    assert cli._resolve_cli_path(platform_name="posix") is None


def test_resolve_cli_path_uses_windows_exe_sibling(tmp_path, monkeypatch):
    python = tmp_path / "venv" / "Scripts" / "python.exe"
    script = python.with_name("leo-ppt.exe")
    script.parent.mkdir(parents=True)
    python.write_text("python", encoding="utf-8")
    script.write_text("console script", encoding="utf-8")
    monkeypatch.setattr(cli.sys, "executable", str(python))
    monkeypatch.delenv("LEO_PPT_CLI_PROG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)

    assert cli._resolve_cli_path(platform_name="nt") == str(script.resolve())


def test_config_status_uses_module_launcher_without_console_script(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "ATLASCLOUD_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "_resolve_cli_path", lambda: None)

    result = cli.dispatch(parse("config", "status", "--json"))

    action = result["report"]["primary_action"]
    assert action is not None
    assert action["kind"] == "run_cli"
    executable = str(Path(sys.executable).resolve())
    assert Path(executable).is_file()
    if cli.os.name == "nt":
        prefix = (
            f"& '{executable.replace(chr(39), chr(39) * 2)}' "
            "'-m' 'leo_ppt_generator' 'config'"
        )
        assert action["command"].startswith(prefix)
        assert action["command"][len(prefix) :] in {
            "",
            " 'change'",
            " 'repair'",
            " 'verify'",
        }
    else:
        tokens = __import__("shlex").split(action["command"])
        assert tokens[:4] == [
            executable,
            "-m",
            "leo_ppt_generator",
            "config",
        ]
        assert tokens[4:] in ([], ["change"], ["repair"], ["verify"])


def test_config_status_host_imagegen_available_reports_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "ATLASCLOUD_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    result = cli.dispatch(
        parse("config", "status", "--json", "--host-imagegen", "available")
    )

    assert result["status"] == "ready"
    assert result["reason_code"] == "configuration_ready"
    assert result["report"]["installation_readiness"] == "ready"


def test_version_command_has_human_and_machine_contract(capsys):
    report = cli.dispatch(parse("version", "--json"))
    assert report == {
        "protocol": "leo-ppt-version/v1",
        "schema_version": 1,
        "status": "ready",
        "reason_code": "version_reported",
        "package_version": cli.__version__,
        "runtime_version": cli.__version__,
        "runtime_identity": report["runtime_identity"],
        "install_channel": report["install_channel"],
        "config_schema_version": 1,
        "setup_schema_version": 1,
        "cli_path": report["cli_path"],
    }
    assert cli.main(["version"]) == 0
    assert f"leo-ppt {cli.__version__}" in capsys.readouterr().out


def test_version_rejects_unknown_or_empty_install_channel(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    from leo_ppt_generator.config.runtime_config import default_home as runtime_home

    current_dir = runtime_home()
    current_dir.mkdir(parents=True, exist_ok=True)
    for bad in ("", "hand-edited-channel"):
        (current_dir / "current").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runtime_identity": "abc",
                    "bundle_root": "/fake/bundle",
                    "install_channel": bad,
                }
            ),
            encoding="utf-8",
        )
        report = cli.dispatch(parse("version", "--json"))
        # 非法渠道被降级为路径推导，而非原样透传空串/手改值。
        assert report["install_channel"] != bad


def test_setup_and_config_provider_share_openai_compatible_choice():
    setup = parse(
        "setup",
        "--route",
        "generate",
        "--provider",
        "openai-compatible",
    )
    configured = parse(
        "config",
        "provider",
        "configure",
        "--provider",
        "openai-compatible",
    )
    assert setup.provider == configured.provider == "openai-compatible"


def test_config_provider_list_uses_registry_and_local_status(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    for name in ("OPENAI_API_KEY", "ATLASCLOUD_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    result = cli.dispatch(parse("config", "provider", "list", "--json"))

    assert result["reason_code"] == "provider_listed"
    assert [item["provider"] for item in result["providers"]] == [
        "openai",
        "openai-compatible",
        "atlascloud",
    ]
    assert all(item["selected"] is False for item in result["providers"])


def test_config_verify_requires_explicit_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    result = cli.dispatch(parse("config", "verify", "--json"))
    assert result["status"] == "action_required"
    assert result["reason_code"] == "paid_verification_consent_required"
    # 同意必须来自真实交互 TTY，而不是可直接执行的 --yes 自指命令。
    action = result["primary_action"]
    assert action["kind"] == "run_cli"
    assert action["command"] == "config"
    assert "--yes" not in action["command"]


def test_config_verify_with_yes_returns_honest_unavailable_when_executor_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    result = cli.dispatch(parse("config", "verify", "--yes", "--json"))
    assert result["status"] == "action_required"
    assert result["reason_code"] == "provider_smoke_executor_unavailable"
    # 不可用状态不能伪装成 ready，恢复入口是交互式 config。
    assert result["primary_action"]["kind"] == "run_cli"
    assert result["primary_action"]["command"] == "config"


def test_config_reset_clears_profiles_but_preserves_credentials(tmp_path, monkeypatch):
    from leo_ppt_generator.config.runtime_config import ConfigStore

    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    store = ConfigStore(home)
    store.compare_and_swap(
        None,
        {
            "schema_version": 1,
            "selected_provider": "openai",
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                }
            },
        },
    )
    result = cli.dispatch(parse("config", "reset", "--confirm", "--json"))
    assert result["reason_code"] == "config_reset"
    assert result["credentials_preserved"] is True
    assert store.read().values["provider_profiles"] == {}
    assert store.read().values.get("selected_provider") is None


def test_config_reset_requires_confirmation(tmp_path, monkeypatch):
    from leo_ppt_generator.config.runtime_config import ConfigStore

    home = tmp_path / "home"
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    store = ConfigStore(home)
    store.compare_and_swap(
        None,
        {
            "schema_version": 1,
            "provider_profiles": {
                "openai": {"model": "gpt-image-2",
                           "credential_source": "environment-reference",
                           "credential_ref": "env:OPENAI_API_KEY"},
            },
        },
    )
    with pytest.raises(ConfigServiceError) as error:
        cli.dispatch(parse("config", "reset", "--json"))
    assert error.value.reason_code == "destructive_confirmation_required"
    # 无确认不得破坏现有配置。
    assert store.read().values["provider_profiles"] != {}


def test_config_reset_conflict_fails_closed_without_mutating(tmp_path, monkeypatch):
    from leo_ppt_generator.config.runtime_config import RuntimeConfigError
    from leo_ppt_generator.config.service import ConfigService
    from leo_ppt_generator.config.readiness import ConfigReport

    class ConflictStore:
        def read(self):
            return type(
                "Snapshot", (),
                {"canonical_digest": "abc", "document": {}, "values": {}, "validation_issues": ()},
            )()

        def compare_and_swap(self, expected_digest, candidate):
            # 并发写入者已改动 digest：任何基于现有 digest 的 reset CAS 均被拒绝。
            raise RuntimeConfigError("config_write_conflict")

    class NoopReceipt:
        def invalidate(self, provider, cause, operation_id):
            return None

    service = ConfigService(
        ConflictStore(), None, None, NoopReceipt()
    )
    monkeypatch.setattr(cli, "_config_service", lambda: service)

    with pytest.raises(ConfigServiceError) as error:
        cli.dispatch(parse("config", "reset", "--confirm", "--json"))
    assert error.value.reason_code == "config_write_conflict"


def test_config_provider_remove_missing_profile_returns_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_PPT_HOME", str(tmp_path / "home"))
    result = cli.dispatch(
        parse("config", "provider", "remove", "--provider", "openai",
              "--confirm", "--json")
    )
    assert result["reason_code"] == "provider_not_found"
    assert result["status"] == "completed"


def test_config_credential_set_accepts_only_explicit_key_stdin(monkeypatch):
    class Store:
        def __init__(self):
            self.value = None

        def status(self, provider):
            return "available" if self.value is not None else "missing"

        def reference(self, provider):
            return f"keychain:leo-ppt-generator/{provider}"

        def write(self, provider, secret):
            # 协议签名是 write(provider, secret: str)；CLI 层通过 reveal_text()
            # 显式受让文本副本再写入。
            self.value = secret

        def fingerprint_key(self, create=False):
            return None

    store = Store()
    manager = CredentialManager(store, {})
    monkeypatch.setattr(cli, "credential_manager", lambda: manager)
    monkeypatch.setattr(cli.sys, "stdin", __import__("io").StringIO("secret-from-stdin\n"))
    result = cli.dispatch(
        parse(
            "config",
            "credential",
            "set",
            "--provider",
            "openai",
            "--key-stdin",
            "--json",
        )
    )
    assert store.value == "secret-from-stdin"
    assert result["credential"]["credential_ref"].endswith("/openai")


def test_update_without_yes_is_preview_and_confirmation(monkeypatch, tmp_path):
    manager = tmp_path / "runtime_manager.py"
    manager.write_text("# manager", encoding="utf-8")
    bundle = tmp_path / "leo-ppt-generator"
    bundle.mkdir()
    monkeypatch.setattr(cli, "_runtime_manager_metadata", lambda: (manager, bundle))
    payload = {
        "protocol": "leo-ppt-update/v1",
        "status": "update_available",
        "reason_code": "release_update_available",
        "update_available": True,
    }
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    monkeypatch.setattr(cli.subprocess, "run", run)
    result = cli.dispatch(parse("update", "--version", "v1.2.3", "--json"))
    assert observed["command"][-3:] == ["check", "--ref", "v1.2.3"]
    assert result["status"] == "action_required"
    assert result["reason_code"] == "update_confirmation_required"


def test_update_without_yes_when_current_reports_ready(monkeypatch, tmp_path):
    manager = tmp_path / "runtime_manager.py"
    manager.write_text("# manager", encoding="utf-8")
    bundle = tmp_path / "leo-ppt-generator"
    bundle.mkdir()
    monkeypatch.setattr(cli, "_runtime_manager_metadata", lambda: (manager, bundle))
    payload = {
        "protocol": "leo-ppt-update/v1",
        "status": "current",
        "reason_code": "release_current",
        "update_available": False,
    }
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    monkeypatch.setattr(cli.subprocess, "run", run)
    result = cli.dispatch(parse("update", "--version", "v1.2.3", "--json"))
    assert observed["command"][-3:] == ["check", "--ref", "v1.2.3"]
    assert result["status"] == "ready"
    assert result["reason_code"] == "release_current"
    assert result.get("primary_action") is None


def test_rollback_delegates_to_runtime_manager(monkeypatch, tmp_path):
    manager = tmp_path / "runtime_manager.py"
    manager.write_text("# manager", encoding="utf-8")
    bundle = tmp_path / "leo-ppt-generator"
    bundle.mkdir()
    monkeypatch.setattr(cli, "_runtime_manager_metadata", lambda: (manager, bundle))
    payload = {"status": "ready", "reason_code": "runtime_rolled_back"}

    def run(command, **kwargs):
        assert command[-1] == "rollback"
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    monkeypatch.setattr(cli.subprocess, "run", run)
    result = cli.dispatch(parse("rollback", "--json"))
    assert result["status"] == "ready"
    assert result["reason_code"] == "runtime_rolled_back"
