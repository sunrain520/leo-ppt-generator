from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from leo_ppt_generator.config import models, ports
from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ConfigurationState,
    ConfigReport,
    ConfigStatus,
    CredentialReferenceType,
    ExecutionEligibility,
    InstallationReadiness,
    PrimaryAction,
    PrimaryActionKind,
    ProviderName,
    ProviderReport,
    ReadinessScope,
    RouteName,
    VerificationFingerprint,
    VerificationReceipt,
    VerificationSource,
    VerificationState,
)

SCHEMAS = (
    Path(__file__).resolve().parents[2]
    / "skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas"
)


def _schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _fingerprint(provider: ProviderName = ProviderName.OPENAI) -> VerificationFingerprint:
    return VerificationFingerprint(
        provider=provider,
        endpoint_origin="https://api.openai.com",
        model="gpt-image-1",
        credential_version="generation:1",
        runtime_identity="leo-ppt-generator/0.1.0",
        adapter_version="openai/v1",
        verification_policy_version=1,
        sha256="a" * 64,
    )


def _evidence(capability: Capability = Capability.GENERATE) -> CapabilityEvidence:
    verified_at = datetime(2026, 1, 1, tzinfo=UTC)
    return CapabilityEvidence(
        capability=capability,
        verified_at=verified_at,
        expires_at=verified_at + timedelta(days=7),
        operation_id="operation-1",
        verification_source=VerificationSource.PROVIDER_SMOKE,
        artifact_digest=ArtifactDigest(
            sha256="b" * 64,
            media_type="image/png",
            size_bytes=128,
        ),
    )


def _configured_report(action: PrimaryAction | None = None) -> ConfigReport:
    provider = ProviderReport(
        provider=ProviderName.OPENAI,
        configuration_state=ConfigurationState.LOCALLY_CONFIGURED,
        verification_state=VerificationState.NOT_RUN,
        candidate_capabilities=frozenset({Capability.GENERATE}),
        scope_compatible=True,
        credential_reference_type=CredentialReferenceType.OS_STORE,
        reason_code="provider_verification_not_run",
        evidence_refs=("credential:openai",),
    )
    return ConfigReport(
        stage="status",
        status=ConfigStatus.CONFIGURED_UNVERIFIED,
        configuration_state=ConfigurationState.LOCALLY_CONFIGURED,
        verification_state=VerificationState.NOT_RUN,
        execution_eligibility=ExecutionEligibility.ALLOWED,
        installation_readiness=InstallationReadiness.USABLE_UNVERIFIED,
        readiness_scope=ReadinessScope(
            route=RouteName.GENERATE,
            required_capabilities=frozenset({Capability.GENERATE}),
            verified_capabilities=frozenset(),
            missing_capabilities=frozenset({Capability.GENERATE}),
        ),
        reason_code="provider_verification_not_run",
        selected_provider=ProviderName.OPENAI,
        providers=(provider,),
        evidence_refs=("config:current",),
        primary_action=action,
    )


def test_readiness_scope_requires_an_exact_capability_partition():
    with pytest.raises(ValueError, match="partition"):
        ReadinessScope(
            route=RouteName.GENERATE,
            required_capabilities=frozenset({Capability.GENERATE}),
            verified_capabilities=frozenset(),
            missing_capabilities=frozenset(),
        )

    scope = ReadinessScope(
        route=RouteName.DIRECT_EDITABLE,
        required_capabilities=frozenset({Capability.EDIT, Capability.MASK}),
        verified_capabilities=frozenset({Capability.EDIT}),
        missing_capabilities=frozenset({Capability.MASK}),
    )
    assert scope.to_dict()["required_capabilities"] == ["edit", "mask"]


def test_primary_action_has_one_null_or_typed_command_representation():
    assert _configured_report().to_dict()["primary_action"] is None
    assert PrimaryAction(
        PrimaryActionKind.RUN_CLI,
        command="'/opt/Leo PPT/leo-ppt' config repair",
    ).to_dict()["kind"] == "run_cli"

    with pytest.raises(ValueError, match="requires command"):
        PrimaryAction(PrimaryActionKind.RUN_CLI)
    with pytest.raises(ValueError, match="only run_cli"):
        PrimaryAction(PrimaryActionKind.START_TASK, command="leo-ppt config")


def test_capability_evidence_requires_utc_ordered_timestamps():
    verified_at = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="later"):
        CapabilityEvidence(
            capability=Capability.GENERATE,
            verified_at=verified_at,
            expires_at=verified_at,
            operation_id="operation-1",
            verification_source=VerificationSource.PROVIDER_SMOKE,
            artifact_digest=_evidence().artifact_digest,
        )


def test_verification_receipt_rejects_host_and_mismatched_capability_keys():
    with pytest.raises(ValueError, match="host providers"):
        _fingerprint(ProviderName.BUILTIN_IMAGEGEN)

    with pytest.raises(ValueError, match="key must match"):
        VerificationReceipt(
            fingerprint=_fingerprint(),
            capability_evidence={Capability.EDIT: _evidence(Capability.GENERATE)},
        )


def test_domain_payloads_validate_against_machine_protocol_schemas():
    report_schema = _schema("config-report-v1.json")
    receipt_schema = _schema("verification-receipt-v1.json")
    Draft202012Validator.check_schema(report_schema)
    Draft202012Validator.check_schema(receipt_schema)

    Draft202012Validator(report_schema).validate(_configured_report().to_dict())
    receipt = VerificationReceipt(
        fingerprint=_fingerprint(),
        capability_evidence={Capability.GENERATE: _evidence()},
    )
    Draft202012Validator(
        receipt_schema,
        format_checker=FormatChecker(),
    ).validate(receipt.to_dict())


def test_config_report_schema_rejects_untyped_or_illegal_actions():
    validator = Draft202012Validator(_schema("config-report-v1.json"))
    payload = _configured_report().to_dict()
    payload["primary_action"] = {}
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload["primary_action"] = {"kind": "start_task", "command": "leo-ppt config"}
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_domain_and_ports_do_not_import_adapter_dependencies():
    forbidden = {"argparse", "subprocess", "platform", "openai", "requests"}
    imported: set[str] = set()
    for module in (models, ports):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden)
