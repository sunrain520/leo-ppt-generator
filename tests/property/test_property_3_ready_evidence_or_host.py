from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.application.routes import (
    ROUTE_CAPABILITY_RESOLVER,
    TASK_CAPABILITIES,
)
from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ConfigurationState,
    ConfigStatus,
    CredentialReferenceType,
    HostCapabilityState,
    ProviderName,
    RouteName,
    VerificationSource,
    VerificationState,
)
from leo_ppt_generator.config.readiness import (
    ProviderReadinessFacts,
    build_config_report,
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
_CAPABILITIES = tuple(Capability)
_TASK_CAPABILITIES = tuple(sorted(TASK_CAPABILITIES, key=lambda item: item.value))


@dataclass(frozen=True)
class EvidenceCase:
    receipt: ReceiptInspection | None
    current_capabilities: frozenset[Capability]


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


@st.composite
def evidence_cases(draw: st.DrawFn) -> EvidenceCase:
    mode = draw(st.sampled_from(("none", "matching", "mismatched")))
    if mode == "none":
        return EvidenceCase(receipt=None, current_capabilities=frozenset())
    if mode == "mismatched":
        return EvidenceCase(
            receipt=ReceiptInspection(
                provider=ProviderName.OPENAI,
                status="stale",
                reason_code="verification_fingerprint_stale",
                fingerprint_matches=False,
                valid_evidence={},
                fingerprint_ref="a" * 12,
            ),
            current_capabilities=frozenset(),
        )

    stored = draw(
        st.frozensets(st.sampled_from(_CAPABILITIES), min_size=1)
    )
    current = draw(st.frozensets(st.sampled_from(tuple(stored))))
    expired = stored - current
    return EvidenceCase(
        receipt=ReceiptInspection(
            provider=ProviderName.OPENAI,
            status="valid" if current else "stale",
            reason_code=(
                "verification_receipt_valid"
                if current
                else "verification_evidence_expired"
            ),
            fingerprint_matches=True,
            valid_evidence={item: _evidence(item) for item in current},
            expired_capabilities=expired,
            fingerprint_ref="a" * 12,
        ),
        current_capabilities=current,
    )


def _facts(
    candidate_capabilities: frozenset[Capability],
    receipt: ReceiptInspection | None,
) -> ProviderReadinessFacts:
    return ProviderReadinessFacts(
        provider=ProviderName.OPENAI,
        configuration_state=ConfigurationState.LOCALLY_CONFIGURED,
        reason_code=ReasonCode.PROVIDER_VERIFICATION_NOT_RUN,
        candidate_capabilities=candidate_capabilities,
        credential_reference_type=CredentialReferenceType.OS_STORE,
        receipt=receipt,
        fingerprint_sha256="f" * 64,
    )


@PROPERTY_SETTINGS
@given(
    route=st.sampled_from(tuple(RouteName)),
    task_capabilities=st.frozensets(st.sampled_from(_TASK_CAPABILITIES)),
    evidence_case=evidence_cases(),
    host_state=st.sampled_from(tuple(HostCapabilityState)),
    host_capabilities=st.frozensets(st.sampled_from(_CAPABILITIES)),
    static_extras=st.frozensets(st.sampled_from(_CAPABILITIES)),
)
def test_property_3_ready_requires_current_evidence_or_live_host_coverage(
    route: RouteName,
    task_capabilities: frozenset[Capability],
    evidence_case: EvidenceCase,
    host_state: HostCapabilityState,
    host_capabilities: frozenset[Capability],
    static_extras: frozenset[Capability],
) -> None:
    """**Validates: Requirements 2.6, 2.16, 7.4, 16.3, 19.5**"""
    required = ROUTE_CAPABILITY_RESOLVER.resolve(route, task_capabilities)
    static_capabilities = required | static_extras
    report = build_config_report(
        [_facts(static_capabilities, evidence_case.receipt)],
        selected_provider=ProviderName.OPENAI,
        route=route,
        task_capabilities=task_capabilities,
        host_capability_state=host_state,
        host_capabilities=host_capabilities,
    )

    evidence_covers = required.issubset(evidence_case.current_capabilities)
    live_host_covers = (
        host_state is HostCapabilityState.AVAILABLE
        and required.issubset(host_capabilities)
    )
    expected_ready = evidence_covers or live_host_covers

    assert (report.status is ConfigStatus.READY) is expected_ready
    assert report.readiness_scope.verified_capabilities == (
        required & evidence_case.current_capabilities
    )
    assert report.readiness_scope.missing_capabilities == (
        required - evidence_case.current_capabilities
    )
    assert (
        report.verification_state is VerificationState.PASSED
    ) is evidence_covers
    if not expected_ready:
        assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED

    minimal_static_report = build_config_report(
        [_facts(required, evidence_case.receipt)],
        selected_provider=ProviderName.OPENAI,
        route=route,
        task_capabilities=task_capabilities,
        host_capability_state=host_state,
        host_capabilities=host_capabilities,
    )
    assert minimal_static_report.status is report.status
    assert minimal_static_report.verification_state is report.verification_state
    assert minimal_static_report.readiness_scope == report.readiness_scope

    static_only_report = build_config_report(
        [_facts(static_capabilities, None)],
        selected_provider=ProviderName.OPENAI,
        route=route,
        task_capabilities=task_capabilities,
        host_capability_state=HostCapabilityState.UNKNOWN,
        host_capabilities=(),
    )
    assert static_only_report.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert static_only_report.readiness_scope.verified_capabilities == frozenset()
