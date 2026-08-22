from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st

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
    ProviderName,
    VerificationSource,
    VerificationState,
)
from leo_ppt_generator.config.readiness import (
    OperationContext,
    ProviderReadinessFacts,
    evaluate_readiness,
)
from leo_ppt_generator.config.reason_codes import ReasonCode
from leo_ppt_generator.config.receipt_store import ReceiptInspection

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
EVIDENCE_MODES = ("none", "valid_missing", "valid_covering", "expired", "fingerprint_stale")
OPERATION_MODES = (
    "none",
    "selected_degraded",
    "selected_non_degraded",
    "other_degraded",
    "other_non_degraded",
)


def _evidence() -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=Capability.GENERATE,
        verified_at=NOW,
        expires_at=NOW + timedelta(days=7),
        operation_id="property-2-generate",
        verification_source=VerificationSource.BUSINESS_REQUEST,
        artifact_digest=ArtifactDigest(
            sha256=hashlib.sha256(b"property-2").hexdigest(),
            media_type="image/png",
            size_bytes=128,
        ),
    )


def _receipt(mode: str) -> ReceiptInspection | None:
    if mode == "none":
        return None
    valid_evidence = (
        {Capability.GENERATE: _evidence()}
        if mode in {"valid_covering", "fingerprint_stale"}
        else {}
    )
    return ReceiptInspection(
        provider=ProviderName.OPENAI,
        status="valid" if mode.startswith("valid_") else "stale",
        reason_code="verification_receipt_valid",
        fingerprint_matches=mode != "fingerprint_stale",
        valid_evidence=valid_evidence,
        expired_capabilities=(
            frozenset({Capability.GENERATE})
            if mode == "expired"
            else frozenset()
        ),
        fingerprint_ref="a" * 12,
    )


def _facts(
    provider: ProviderName,
    configuration: ConfigurationState,
    *,
    candidate_has_required: bool = True,
    receipt: ReceiptInspection | None = None,
) -> ProviderReadinessFacts:
    candidates = frozenset(Capability)
    if not candidate_has_required:
        candidates -= {Capability.GENERATE}
    return ProviderReadinessFacts(
        provider=provider,
        configuration_state=configuration,
        reason_code=(
            ReasonCode.CONFIG_INVALID
            if configuration is ConfigurationState.INVALID
            else ReasonCode.PROVIDER_VERIFICATION_NOT_RUN
        ),
        candidate_capabilities=candidates,
        credential_reference_type=CredentialReferenceType.OS_STORE,
        receipt=receipt,
        fingerprint_sha256="f" * 64 if receipt is not None else None,
    )


def _operation(mode: str) -> OperationContext | None:
    if mode == "none":
        return None
    return OperationContext(
        provider=(
            ProviderName.OPENAI
            if mode.startswith("selected_")
            else ProviderName.ATLASCLOUD
        ),
        reason_code=ReasonCode.PROVIDER_TIMEOUT,
        degraded=mode.endswith("degraded") and not mode.endswith("non_degraded"),
    )


def _expected_status(
    configuration: ConfigurationState,
    *,
    evidence_covers: bool,
    host_covers: bool,
    selected_operation_degraded: bool,
) -> ConfigStatus:
    if configuration is ConfigurationState.INVALID:
        return ConfigStatus.INVALID
    if configuration is not ConfigurationState.LOCALLY_CONFIGURED and not host_covers:
        return ConfigStatus.NOT_CONFIGURED
    if selected_operation_degraded:
        return ConfigStatus.DEGRADED
    if evidence_covers or host_covers:
        return ConfigStatus.READY
    return ConfigStatus.CONFIGURED_UNVERIFIED


@st.composite
def aggregate_cases(draw: st.DrawFn):
    case = {
        "configuration": draw(st.sampled_from(tuple(ConfigurationState))),
        "candidate_has_required": draw(st.booleans()),
        "evidence_mode": draw(st.sampled_from(EVIDENCE_MODES)),
        "host_state": draw(st.sampled_from(tuple(HostCapabilityState))),
        "host_has_required": draw(st.booleans()),
        "operation_mode": draw(st.sampled_from(OPERATION_MODES)),
    }
    if case["operation_mode"] == "selected_degraded":
        # 合同语义（flow.md §5.1）：degraded 表示“本地有效，当前外部调用暂时失败”，
        # 因此当前 Provider 必须本地配置完整；不生成合同不允许的组合。
        case = {**case, "configuration": ConfigurationState.LOCALLY_CONFIGURED}
    return case


@PROPERTY_SETTINGS
@given(case=aggregate_cases())
def test_property_2_aggregate_status_is_deterministic_and_priority_safe(case):
    """**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.18**"""

    receipt = _receipt(case["evidence_mode"])
    selected = _facts(
        ProviderName.OPENAI,
        case["configuration"],
        candidate_has_required=case["candidate_has_required"],
        receipt=receipt,
    )
    other = _facts(ProviderName.ATLASCLOUD, ConfigurationState.LOCALLY_CONFIGURED)
    operation = _operation(case["operation_mode"])
    host_capabilities = (
        {Capability.GENERATE} if case["host_has_required"] else set()
    )
    arguments = {
        "selected_provider": ProviderName.OPENAI,
        "host_capability_state": case["host_state"],
        "host_capabilities": host_capabilities,
        "operation_context": operation,
    }

    decision = evaluate_readiness((selected, other), **arguments)
    repeated = evaluate_readiness((selected, other), **arguments)
    reordered = evaluate_readiness((other, selected), **arguments)
    assert decision == repeated == reordered

    compatible = case["candidate_has_required"]
    effective_configuration = case["configuration"]
    if effective_configuration is ConfigurationState.LOCALLY_CONFIGURED and not compatible:
        effective_configuration = ConfigurationState.INVALID
    evidence_covers = case["evidence_mode"] == "valid_covering"
    host_covers = (
        case["host_state"] is HostCapabilityState.AVAILABLE
        and case["host_has_required"]
    )
    selected_operation = case["operation_mode"].startswith("selected_")
    selected_degraded = case["operation_mode"] == "selected_degraded"

    if selected_operation:
        expected_verification = VerificationState.FAILED
    elif evidence_covers:
        expected_verification = VerificationState.PASSED
    elif case["evidence_mode"] in {"expired", "fingerprint_stale"}:
        expected_verification = VerificationState.STALE
    else:
        expected_verification = VerificationState.NOT_RUN

    expected_status = _expected_status(
        effective_configuration,
        evidence_covers=evidence_covers,
        host_covers=host_covers,
        selected_operation_degraded=selected_degraded,
    )
    expected_eligibility = {
        ConfigStatus.READY: ExecutionEligibility.ALLOWED,
        ConfigStatus.CONFIGURED_UNVERIFIED: ExecutionEligibility.ALLOWED,
        ConfigStatus.DEGRADED: ExecutionEligibility.RETRYABLE,
        ConfigStatus.NOT_CONFIGURED: ExecutionEligibility.BLOCKED,
        ConfigStatus.INVALID: ExecutionEligibility.BLOCKED,
    }[expected_status]
    expected_installation = {
        ConfigStatus.READY: InstallationReadiness.READY,
        ConfigStatus.CONFIGURED_UNVERIFIED: InstallationReadiness.USABLE_UNVERIFIED,
        ConfigStatus.DEGRADED: InstallationReadiness.INSTALLED_NOT_READY,
        ConfigStatus.NOT_CONFIGURED: InstallationReadiness.INSTALLED_NOT_READY,
        ConfigStatus.INVALID: InstallationReadiness.INSTALLED_NOT_READY,
    }[expected_status]

    assert decision.configuration_state is effective_configuration
    assert decision.verification_state is expected_verification
    assert decision.status is expected_status
    assert decision.execution_eligibility is expected_eligibility
    assert decision.installation_readiness is expected_installation

    if decision.status is ConfigStatus.DEGRADED:
        assert selected_degraded
        assert effective_configuration is ConfigurationState.LOCALLY_CONFIGURED

    local_decision = evaluate_readiness(
        (selected, other),
        **{**arguments, "operation_context": None},
    )
    assert local_decision.status is not ConfigStatus.DEGRADED
    if case["operation_mode"].startswith("other_"):
        assert decision.status is local_decision.status
        assert decision.verification_state is local_decision.verification_state
