from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from leo_ppt_generator import cli
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
