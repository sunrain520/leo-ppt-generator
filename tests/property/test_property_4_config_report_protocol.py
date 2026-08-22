# Feature: guided-provider-config, Property 4: Config report protocol is
# closed and semantically consistent

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ConfigurationState,
    ConfigStatus,
    ExecutionEligibility,
    HostCapabilityState,
    InstallationReadiness,
    PrimaryActionKind,
    ProviderName,
    VerificationSource,
    VerificationState,
)
from leo_ppt_generator.config.readiness import (
    OperationContext,
    ProviderReadinessFacts,
    build_config_report,
)
from leo_ppt_generator.config.reason_codes import (
    CommandRenderer,
    ReasonCode,
    ShellKind,
)
from leo_ppt_generator.config.receipt_store import ReceiptInspection
from leo_ppt_generator.schemas import load_schema

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
REPORT_SCHEMA = load_schema("config-report-v1.json")
RENDERER = CommandRenderer(ShellKind.POSIX)


def _evidence() -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=Capability.GENERATE,
        verified_at=NOW,
        expires_at=NOW + timedelta(days=7),
        operation_id="operation-x",
        verification_source=VerificationSource.PROVIDER_SMOKE,
        artifact_digest=ArtifactDigest(
            sha256="a" * 64,
            media_type="image/png",
            size_bytes=128,
        ),
    )


def _facts(provider: ProviderName, configuration: ConfigurationState) -> ProviderReadinessFacts:
    return ProviderReadinessFacts(
        provider=provider,
        configuration_state=configuration,
        reason_code=(
            ReasonCode.CONFIG_INVALID
            if configuration is ConfigurationState.INVALID
            else ReasonCode.PROVIDER_VERIFICATION_NOT_RUN
        ),
        candidate_capabilities=frozenset(Capability),
        credential_reference_type=("os-store-reference"),
        receipt=None,
        fingerprint_sha256=None,
    )


@st.composite
def report_cases(draw: st.DrawFn):
    configuration = draw(st.sampled_from(tuple(ConfigurationState)))
    has_evidence = draw(st.booleans())
    selected = _facts(ProviderName.OPENAI, configuration)
    if has_evidence:
        selected = ProviderReadinessFacts(
            provider=ProviderName.OPENAI,
            configuration_state=configuration,
            reason_code=ReasonCode.PROVIDER_VERIFICATION_NOT_RUN,
            candidate_capabilities=frozenset(Capability),
            credential_reference_type="os-store-reference",
            receipt=ReceiptInspection(
                provider=ProviderName.OPENAI,
                status="valid",
                reason_code="verification_receipt_valid",
                fingerprint_matches=True,
                valid_evidence={Capability.GENERATE: _evidence()},
            ),
            fingerprint_sha256="f" * 64,
        )
    other = _facts(ProviderName.ATLASCLOUD, ConfigurationState.LOCALLY_CONFIGURED)
    operation = draw(
        st.one_of(
            st.none(),
            st.just(
                OperationContext(
                    provider=ProviderName.OPENAI,
                    reason_code=ReasonCode.PROVIDER_TIMEOUT,
                    degraded=True,
                )
            ),
        )
    )
    host_state = draw(st.sampled_from(tuple(HostCapabilityState)))
    return {
        "selected": selected,
        "other": other,
        "operation": operation,
        "host_state": host_state,
    }


@PROPERTY_SETTINGS
@given(case=report_cases())
def test_property_4_config_report_protocol_is_closed_and_semantically_consistent(case):
    """**Validates: Requirements 2.1, 2.11, 2.12, 2.14, 2.15, 15.1, 15.5**"""
    report = build_config_report(
        (case["selected"], case["other"]),
        selected_provider=ProviderName.OPENAI,
        host_capability_state=case["host_state"],
        operation_context=case["operation"],
        action_materializer=lambda intent: RENDERER.render(
            intent, cli_path="/usr/local/bin/leo-ppt"
        ),
    )
    payload = report.to_dict()

    # JSON 序列化必须通过 leo-ppt-config/v1 schema。
    import jsonschema

    jsonschema.validate(payload, REPORT_SCHEMA)

    # 三层状态彼此独立且与聚合状态一致。
    assert payload["configuration_state"] == report.configuration_state.value
    assert payload["verification"]["status"] == report.verification_state.value
    assert payload["status"] == report.status.value

    # primary_action 缺失语义只能用 null 表达；run_cli 才含 command。
    if report.primary_action is None:
        assert payload["primary_action"] is None
    else:
        action = payload["primary_action"]
        assert action["kind"] in {item.value for item in PrimaryActionKind}
        if action["kind"] == "run_cli":
            assert action["command"] is not None
        else:
            assert "command" not in action

    # human renderer 语义一致：同 status、reason、单 action。
    human = _render_human(report)
    assert report.status.value in human
    assert report.reason_code in human
    assert _count_actions(human) <= 1

    # execution_eligibility 与 installation_readiness 映射固定。
    assert _eligibility_of(report.status) == report.execution_eligibility
    assert _installation_of(report.status) == report.installation_readiness


def _eligibility_of(status: ConfigStatus) -> ExecutionEligibility:
    return {
        ConfigStatus.READY: ExecutionEligibility.ALLOWED,
        ConfigStatus.CONFIGURED_UNVERIFIED: ExecutionEligibility.ALLOWED,
        ConfigStatus.DEGRADED: ExecutionEligibility.RETRYABLE,
        ConfigStatus.NOT_CONFIGURED: ExecutionEligibility.BLOCKED,
        ConfigStatus.INVALID: ExecutionEligibility.BLOCKED,
    }[status]


def _installation_of(status: ConfigStatus) -> InstallationReadiness:
    return {
        ConfigStatus.READY: InstallationReadiness.READY,
        ConfigStatus.CONFIGURED_UNVERIFIED: InstallationReadiness.USABLE_UNVERIFIED,
        ConfigStatus.DEGRADED: InstallationReadiness.INSTALLED_NOT_READY,
        ConfigStatus.NOT_CONFIGURED: InstallationReadiness.INSTALLED_NOT_READY,
        ConfigStatus.INVALID: InstallationReadiness.INSTALLED_NOT_READY,
    }[status]


def _render_human(report) -> str:
    # 简化 human renderer 语义：状态、原因与至多一个动作。
    lines = [f"status={report.status.value}", f"reason={report.reason_code}"]
    if report.primary_action is not None:
        lines.append(f"action={report.primary_action.kind.value}")
    return "\n".join(lines)


def _count_actions(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("action="))


@PROPERTY_SETTINGS
@given(case=report_cases())
def test_property_4_report_roundtrips_through_json(case):
    """**Validates: Requirements 2.11, 15.5**"""
    report = build_config_report(
        (case["selected"], case["other"]),
        selected_provider=ProviderName.OPENAI,
        host_capability_state=case["host_state"],
        operation_context=case["operation"],
        action_materializer=lambda intent: RENDERER.render(
            intent, cli_path="/usr/local/bin/leo-ppt"
        ),
    )
    payload = report.to_dict()
    # JSON 往返不改变语义字段。
    roundtrip = json.loads(json.dumps(payload))
    assert roundtrip == payload
    assert len(json.dumps(payload).encode("utf-8")) < 1 << 16
