# Feature: guided-provider-config, Property 33: Provider and Route isolation
# is order-independent

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
    ProviderName,
    RouteName,
    VerificationSource,
)
from leo_ppt_generator.config.readiness import (
    ProviderReadinessFacts,
    build_config_report,
)
from leo_ppt_generator.config.reason_codes import (
    CommandRenderer,
    ReasonCode,
    ShellKind,
)
from leo_ppt_generator.config.receipt_store import ReceiptInspection

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
RENDERER = CommandRenderer(ShellKind.POSIX)
_PROVIDERS = (ProviderName.OPENAI, ProviderName.OPENAI_COMPATIBLE, ProviderName.ATLASCLOUD)


def _digest(seed: str) -> ArtifactDigest:
    return ArtifactDigest(
        sha256=hashlib.sha256(seed.encode()).hexdigest(),
        media_type="image/png",
        size_bytes=4,
    )


def _evidence(capability: Capability) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        verified_at=NOW,
        expires_at=NOW + timedelta(days=7),
        operation_id=f"op-{capability.value}",
        verification_source=VerificationSource.BUSINESS_REQUEST,
        artifact_digest=_digest(capability.value),
    )


def _facts(
    provider: ProviderName,
    *,
    configuration: ConfigurationState = ConfigurationState.LOCALLY_CONFIGURED,
    verified: frozenset[Capability] = frozenset(),
    candidate: frozenset[Capability] = frozenset(Capability),
) -> ProviderReadinessFacts:
    receipt = None
    if verified:
        receipt = ReceiptInspection(
            provider=provider,
            status="valid",
            reason_code="verification_receipt_valid",
            fingerprint_matches=True,
            valid_evidence={cap: _evidence(cap) for cap in verified},
        )
    return ProviderReadinessFacts(
        provider=provider,
        configuration_state=configuration,
        reason_code=(
            ReasonCode.CONFIG_INVALID
            if configuration is ConfigurationState.INVALID
            else ReasonCode.PROVIDER_VERIFICATION_NOT_RUN
        ),
        candidate_capabilities=candidate,
        credential_reference_type=CredentialReferenceType.OS_STORE,
        receipt=receipt,
        fingerprint_sha256="f" * 64 if verified else None,
    )


@st.composite
def provider_state_cases(draw: st.DrawFn):
    broken_provider = draw(st.sampled_from(_PROVIDERS))
    selected_provider = draw(st.sampled_from(_PROVIDERS))
    route = draw(st.sampled_from(tuple(RouteName)))
    verified = draw(st.sampled_from((frozenset(), frozenset({Capability.GENERATE}))))
    return {
        "broken_provider": broken_provider,
        "selected_provider": selected_provider,
        "route": route,
        "verified": verified,
    }


@PROPERTY_SETTINGS
@given(case=provider_state_cases())
def test_property_33_provider_and_route_isolation_is_order_independent(case):
    """**Validates: Requirements 10.8, 16.5, 16.6, 16.7**"""
    providers = tuple(
        _facts(
            provider,
            configuration=(
                ConfigurationState.INVALID
                if provider is case["broken_provider"]
                else ConfigurationState.LOCALLY_CONFIGURED
            ),
            verified=(
                case["verified"]
                if provider is case["selected_provider"]
                else frozenset()
            ),
        )
        for provider in _PROVIDERS
    )
    selected = case["selected_provider"]
    route = case["route"]

    def report(ordered):
        return build_config_report(
            ordered,
            selected_provider=selected,
            route=route,
            action_materializer=lambda intent: RENDERER.render(
                intent, cli_path="/usr/local/bin/leo-ppt"
            ),
        )

    forward = report(providers)
    reversed_report = report(tuple(reversed(providers)))
    assert forward.status is reversed_report.status
    assert forward.configuration_state is reversed_report.configuration_state
    assert forward.verification_state is reversed_report.verification_state
    assert forward.readiness_scope.to_dict() == reversed_report.readiness_scope.to_dict()
    assert forward.primary_action == reversed_report.primary_action

    # 非目标 Provider 损坏不得抬升全局 invalid：目标 Provider 仍可决定 readiness。
    if selected is not case["broken_provider"]:
        assert forward.status is not ConfigStatus.INVALID
        # OpenAI-compatible 与其余 External Provider 使用相同归并规则。
        assert len(forward.providers) == len(_PROVIDERS)
        broken_reports = [
            item for item in forward.providers if item.provider is case["broken_provider"]
        ]
        assert len(broken_reports) == 1
        assert broken_reports[0].configuration_state is ConfigurationState.INVALID

    # 可用/不可用 Route partition 完整且不重叠。
    assert (
        forward.readiness_scope.required_capabilities
        == forward.readiness_scope.verified_capabilities
        | forward.readiness_scope.missing_capabilities
    )
    assert (
        forward.readiness_scope.verified_capabilities
        & forward.readiness_scope.missing_capabilities
        == frozenset()
    )
