from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ConfigurationState,
    ConfigStatus,
    CredentialReferenceType,
    ExecutionEligibility,
    HostCapabilityState,
    InstallationReadiness,
    PrimaryAction,
    ProviderName,
    RouteName,
    VerificationSource,
    VerificationState,
)
from leo_ppt_generator.config.readiness import (
    OperationContext,
    ProviderReadinessFacts,
    build_config_report,
)
from leo_ppt_generator.config.reason_codes import (
    ActionIntent,
    CommandRenderer,
    ReasonCode,
    ShellKind,
)
from leo_ppt_generator.config.receipt_store import ReceiptInspection


NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _evidence(capability: Capability) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        verified_at=NOW,
        expires_at=NOW + timedelta(days=7),
        operation_id=f"operation-{capability.value}",
        verification_source=VerificationSource.BUSINESS_REQUEST,
        artifact_digest=ArtifactDigest(
            sha256=hashlib.sha256(capability.value.encode()).hexdigest(),
            media_type="image/png",
            size_bytes=128,
        ),
    )


def _receipt(
    provider: ProviderName,
    *capabilities: Capability,
    status: str = "valid",
    fingerprint_matches: bool = True,
    expired: frozenset[Capability] = frozenset(),
) -> ReceiptInspection:
    return ReceiptInspection(
        provider=provider,
        status=status,
        reason_code="verification_receipt_valid",
        fingerprint_matches=fingerprint_matches,
        valid_evidence={item: _evidence(item) for item in capabilities},
        expired_capabilities=expired,
        fingerprint_ref="a" * 12,
    )


def _facts(
    provider: ProviderName = ProviderName.OPENAI,
    *,
    configuration: ConfigurationState = ConfigurationState.LOCALLY_CONFIGURED,
    reason: ReasonCode = ReasonCode.PROVIDER_VERIFICATION_NOT_RUN,
    capabilities: frozenset[Capability] = frozenset(Capability),
    receipt: ReceiptInspection | None = None,
) -> ProviderReadinessFacts:
    return ProviderReadinessFacts(
        provider=provider,
        configuration_state=configuration,
        reason_code=reason,
        candidate_capabilities=capabilities,
        credential_reference_type=(
            CredentialReferenceType.NONE
            if provider is ProviderName.BUILTIN_IMAGEGEN
            else CredentialReferenceType.OS_STORE
        ),
        receipt=receipt,
        fingerprint_sha256="f" * 64 if receipt is not None else None,
        evidence_refs=(f"config://{provider.value}",),
    )


def _render_action(intent: ActionIntent) -> PrimaryAction:
    action = CommandRenderer(ShellKind.POSIX).render(
        intent, cli_path="/opt/leo-ppt/bin/leo-ppt"
    )
    assert action is not None
    return action


def test_locally_configured_without_evidence_is_usable_and_can_start_task():
    report = build_config_report(
        [_facts()], selected_provider=ProviderName.OPENAI
    )

    assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert report.configuration_state is ConfigurationState.LOCALLY_CONFIGURED
    assert report.verification_state is VerificationState.NOT_RUN
    assert report.execution_eligibility is ExecutionEligibility.ALLOWED
    assert report.installation_readiness is InstallationReadiness.USABLE_UNVERIFIED
    assert report.readiness_scope.verified_capabilities == frozenset()
    assert report.readiness_scope.missing_capabilities == {Capability.GENERATE}
    assert report.primary_action is not None
    assert report.primary_action.kind.value == "start_task"


def test_ready_requires_every_scope_capability_to_have_current_evidence():
    receipt = _receipt(
        ProviderName.OPENAI, Capability.EDIT, Capability.MASK
    )
    ready = build_config_report(
        [_facts(receipt=receipt)],
        selected_provider=ProviderName.OPENAI,
        route=RouteName.DIRECT_EDITABLE,
        task_capabilities={Capability.MASK},
    )
    missing_reference = build_config_report(
        [_facts(receipt=receipt)],
        selected_provider=ProviderName.OPENAI,
        route=RouteName.DIRECT_EDITABLE,
        task_capabilities={Capability.MASK, Capability.REFERENCE},
    )

    assert ready.status is ConfigStatus.READY
    assert ready.verification_state is VerificationState.PASSED
    assert ready.readiness_scope.required_capabilities == {
        Capability.EDIT,
        Capability.MASK,
    }
    assert missing_reference.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert missing_reference.readiness_scope.missing_capabilities == {
        Capability.REFERENCE
    }


def test_static_provider_capabilities_do_not_create_readiness():
    report = build_config_report(
        [_facts(capabilities=frozenset(Capability))],
        selected_provider=ProviderName.OPENAI,
    )

    assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert report.readiness_scope.verified_capabilities == frozenset()


def test_live_host_coverage_can_make_scope_ready_without_external_receipt():
    report = build_config_report(
        [_facts()],
        selected_provider=ProviderName.OPENAI,
        host_capability_state=HostCapabilityState.AVAILABLE,
        host_capabilities={Capability.GENERATE},
    )

    assert report.status is ConfigStatus.READY
    assert report.verification_state is VerificationState.NOT_RUN
    assert report.readiness_scope.verified_capabilities == frozenset()
    assert report.readiness_scope.missing_capabilities == {Capability.GENERATE}


def test_live_host_must_cover_every_required_capability():
    report = build_config_report(
        [_facts()],
        selected_provider=ProviderName.OPENAI,
        route=RouteName.DIRECT_EDITABLE,
        task_capabilities={Capability.MASK},
        host_capability_state=HostCapabilityState.AVAILABLE,
        host_capabilities={Capability.EDIT},
    )

    assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert report.verification_state is VerificationState.NOT_RUN
    assert report.readiness_scope.missing_capabilities == {
        Capability.EDIT,
        Capability.MASK,
    }


def test_current_selected_provider_failure_is_degraded_but_history_is_not():
    operation = OperationContext(
        provider=ProviderName.OPENAI,
        reason_code=ReasonCode.PROVIDER_RATE_LIMITED,
        degraded=True,
        evidence_refs=("operation://rate-limit",),
    )
    degraded = build_config_report(
        [_facts()],
        selected_provider=ProviderName.OPENAI,
        operation_context=operation,
    )
    local_status = build_config_report(
        [_facts()], selected_provider=ProviderName.OPENAI
    )

    assert degraded.status is ConfigStatus.DEGRADED
    assert degraded.verification_state is VerificationState.FAILED
    assert degraded.execution_eligibility is ExecutionEligibility.RETRYABLE
    assert degraded.primary_action is not None
    assert degraded.primary_action.kind.value == "wait_and_retry"
    assert local_status.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert local_status.verification_state is VerificationState.NOT_RUN


def test_invalid_selected_provider_wins_over_operation_and_host_coverage():
    operation = OperationContext(
        provider=ProviderName.OPENAI,
        reason_code=ReasonCode.PROVIDER_TIMEOUT,
        degraded=True,
    )
    report = build_config_report(
        [
            _facts(
                configuration=ConfigurationState.INVALID,
                reason=ReasonCode.CONFIG_INVALID,
            )
        ],
        selected_provider=ProviderName.OPENAI,
        host_capability_state=HostCapabilityState.AVAILABLE,
        host_capabilities={Capability.GENERATE},
        operation_context=operation,
        action_materializer=_render_action,
    )

    assert report.status is ConfigStatus.INVALID
    assert report.reason_code == ReasonCode.CONFIG_INVALID.value
    assert report.execution_eligibility is ExecutionEligibility.BLOCKED
    assert report.primary_action is not None
    assert report.primary_action.kind.value == "run_cli"


def test_non_target_provider_error_stays_provider_local():
    operation = OperationContext(
        provider=ProviderName.ATLASCLOUD,
        reason_code=ReasonCode.PROVIDER_TIMEOUT,
        degraded=True,
    )
    report = build_config_report(
        [
            _facts(receipt=_receipt(ProviderName.OPENAI, Capability.GENERATE)),
            _facts(
                ProviderName.ATLASCLOUD,
                configuration=ConfigurationState.INVALID,
                reason=ReasonCode.PROVIDER_PROFILE_INVALID,
            ),
        ],
        selected_provider=ProviderName.OPENAI,
        operation_context=operation,
    )

    assert report.status is ConfigStatus.READY
    atlas = next(
        item for item in report.providers
        if item.provider is ProviderName.ATLASCLOUD
    )
    assert atlas.configuration_state is ConfigurationState.INVALID
    assert atlas.verification_state is VerificationState.FAILED
    assert atlas.reason_code == ReasonCode.PROVIDER_TIMEOUT.value


def test_expired_required_evidence_is_stale_and_remains_usable_unverified():
    receipt = _receipt(
        ProviderName.OPENAI,
        status="stale",
        expired=frozenset({Capability.GENERATE}),
    )
    report = build_config_report(
        [_facts(receipt=receipt)], selected_provider=ProviderName.OPENAI
    )

    assert report.verification_state is VerificationState.STALE
    assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert report.reason_code == ReasonCode.PROVIDER_VERIFICATION_STALE.value


def test_incompatible_selected_provider_is_invalid_for_target_scope():
    report = build_config_report(
        [
            _facts(
                ProviderName.ATLASCLOUD,
                capabilities=frozenset({Capability.GENERATE}),
            )
        ],
        selected_provider=ProviderName.ATLASCLOUD,
        route=RouteName.DIRECT_EDITABLE,
        action_materializer=_render_action,
    )

    assert report.status is ConfigStatus.INVALID
    assert report.configuration_state is ConfigurationState.INVALID
    assert report.providers[0].scope_compatible is False
    assert report.reason_code == ReasonCode.PROVIDER_PROFILE_INVALID.value


def test_blocked_action_must_be_materialized_from_catalog():
    facts = _facts(
        configuration=ConfigurationState.NOT_CONFIGURED,
        reason=ReasonCode.CREDENTIAL_ENVIRONMENT_MISSING,
    )

    with pytest.raises(ValueError, match="ActionMaterializer"):
        build_config_report([facts], selected_provider=ProviderName.OPENAI)

    report = build_config_report(
        [facts],
        selected_provider=ProviderName.OPENAI,
        action_materializer=_render_action,
    )
    assert report.primary_action is not None
    assert report.primary_action.kind.value == "run_cli"
    assert report.primary_action.command == (
        "'/opt/leo-ppt/bin/leo-ppt' 'config' 'repair'"
    )


def test_stale_fingerprint_evidence_cannot_make_scope_ready():
    receipt = _receipt(
        ProviderName.OPENAI,
        Capability.GENERATE,
        status="stale",
        fingerprint_matches=False,
    )

    report = build_config_report(
        [_facts(receipt=receipt)], selected_provider=ProviderName.OPENAI
    )

    assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert report.verification_state is VerificationState.STALE
    assert report.readiness_scope.verified_capabilities == frozenset()
    assert report.readiness_scope.missing_capabilities == {Capability.GENERATE}


def test_operation_context_must_reference_a_reported_provider():
    operation = OperationContext(
        provider=ProviderName.ATLASCLOUD,
        reason_code=ReasonCode.PROVIDER_TIMEOUT,
        degraded=True,
    )

    with pytest.raises(
        ValueError, match="operation_context provider must appear in providers"
    ):
        build_config_report(
            [_facts()],
            selected_provider=ProviderName.OPENAI,
            operation_context=operation,
        )