from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from leo_ppt_generator import cli

SCHEMAS = Path(__file__).resolve().parents[2] / "skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas"


def schema(name: str):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_machine_result_schema_accepts_real_cli_envelope():
    Draft202012Validator(schema("command-result-v1.schema.json")).validate(cli.doctor_report("generate"))


def test_page_artifact_and_delivery_canonical_schemas_are_well_formed():
    for name in (
        "page_artifact.schema.json",
        "delivery.schema.json",
        "run.schema.json",
        "backend-contract-v1.schema.json",
        "bootstrap-result-v1.schema.json",
        "setup-report-v1.schema.json",
        "credential-status-v1.schema.json",
    ):
        Draft202012Validator.check_schema(schema(name))


def test_setup_schema_accepts_a_real_setup_report(monkeypatch):
    from leo_ppt_generator import setup

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ATLASCLOUD_API_KEY", raising=False)
    report = setup.build_setup_report("generate", host_imagegen="available")
    Draft202012Validator(schema("setup-report-v1.schema.json")).validate(report)


def test_setup_schema_rejects_ready_report_with_primary_action(monkeypatch):
    from leo_ppt_generator import setup

    report = setup.build_setup_report("generate", host_imagegen="available")
    report["primary_action"] = {
        "id": "unexpected",
        "command": "unexpected",
        "verification": "unexpected",
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(schema("setup-report-v1.schema.json")).validate(report)


def test_bootstrap_result_schema_accepts_v1_and_rejects_unknown_version():
    result = {
        "protocol": "leo-ppt-bootstrap/v1",
        "schema_version": 1,
        "platform": "macos",
        "architecture": "arm64",
        "python_source": "system",
        "runtime_outcome": "reused",
        "runtime_identity": "runtime-1",
        "cli_reference": "leo-ppt",
        "stage": "complete",
        "status": "ready",
        "reason_code": "bootstrap_ready",
        "primary_action": None,
        "details": {},
    }
    validator = Draft202012Validator(schema("bootstrap-result-v1.schema.json"))
    validator.validate(result)
    invalid_action = {
        **result,
        "primary_action": {
            "id": "unexpected",
            "command": "unexpected",
            "verification": "unexpected",
        },
    }
    with pytest.raises(ValidationError):
        validator.validate(invalid_action)
    result["schema_version"] = 2
    with pytest.raises(ValidationError):
        validator.validate(result)


def test_credential_status_schema_accepts_non_sensitive_manager_report():
    from leo_ppt_generator.credentials import CredentialManager

    class MissingStore:
        def status(self, _provider):
            return "missing"

        def reference(self, provider):
            return f"keychain:leo-ppt-generator/{provider}"

    report = CredentialManager(MissingStore(), {}).status("openai")
    Draft202012Validator(schema("credential-status-v1.schema.json")).validate(report)
    assert "secret" not in json.dumps(report).lower()
