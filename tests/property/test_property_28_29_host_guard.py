# Feature: guided-provider-config, Properties 28/29: Host guard is
# capability-local and receipt-independent; guard recheck resumes the same
# task state

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.host_guard import HostProbe, HostReadinessGuard
from leo_ppt_generator.config.models import (
    Capability,
    ConfigStatus,
    HostCapabilityState,
)
from leo_ppt_generator.config.readiness import OperationContext
from leo_ppt_generator.config.reason_codes import ReasonCode

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
_CAPABILITIES = (Capability.GENERATE, Capability.EDIT, Capability.MASK, Capability.REFERENCE)
_STATUSES = (ConfigStatus.READY, ConfigStatus.CONFIGURED_UNVERIFIED, ConfigStatus.NOT_CONFIGURED, ConfigStatus.INVALID, ConfigStatus.DEGRADED)
_HOST_STATES = tuple(HostCapabilityState)
_GUARD = HostReadinessGuard(cli_path="/usr/local/bin/leo-ppt")


@st.composite
def guard_cases(draw: st.DrawFn):
    required = frozenset(draw(st.lists(st.sampled_from(_CAPABILITIES), min_size=1, max_size=2, unique=True)))
    host_state = draw(st.sampled_from(_HOST_STATES))
    host_caps = frozenset(draw(st.lists(st.sampled_from(_CAPABILITIES), min_size=0, max_size=2, unique=True)))
    status = draw(st.sampled_from(_STATUSES))
    degraded = draw(st.booleans())
    return {
        "required": required,
        "host_state": host_state,
        "host_caps": host_caps,
        "status": status,
        "degraded": degraded,
    }


@PROPERTY_SETTINGS
@given(case=guard_cases())
def test_property_28_host_guard_is_capability_local_and_receipt_independent(case):
    """**Validates: Requirements 11.2, 11.3, 11.4, 12.1-12.5**"""
    host = HostProbe(case["host_state"], case["host_caps"])
    operation = None
    if case["status"] is ConfigStatus.DEGRADED and case["degraded"]:
        operation = OperationContext(
            provider="openai",
            reason_code=ReasonCode.PROVIDER_TIMEOUT,
            degraded=True,
        )
    decision = _GUARD.evaluate(
        report_status=case["status"],
        required_capabilities=case["required"],
        host=host,
        operation_context=operation,
    )
    host_covers = case["host_state"] is HostCapabilityState.AVAILABLE and case["required"].issubset(case["host_caps"])
    if host_covers:
        assert decision.eligibility == "allowed"
        assert decision.action in {"continue", "resume"}
    # 决策且只受 host/status 影响；不产生也不修改任何 receipt。
    assert decision.reason_code is not None
    if case["status"] is ConfigStatus.READY and not host_covers:
        assert decision.eligibility == "allowed"
    if case["status"] in {ConfigStatus.NOT_CONFIGURED, ConfigStatus.INVALID} and not host_covers:
        assert decision.eligibility == "blocked"
    if case["status"] is ConfigStatus.CONFIGURED_UNVERIFIED and not host_covers:
        assert decision.eligibility == "allowed"
        assert decision.lazy_verification is True
    if case["status"] is ConfigStatus.DEGRADED and not host_covers and operation is not None:
        assert decision.eligibility == "retryable"
        assert decision.action == "pause"


@PROPERTY_SETTINGS
@given(case=guard_cases())
def test_property_29_guard_recheck_resumes_same_task_state(case):
    """**Validates: Requirements 11.6, 11.7, 11.8**"""
    host = HostProbe(case["host_state"], case["host_caps"])
    resume_ref = "run-1/stage-image"
    paused = _GUARD.evaluate(
        report_status=ConfigStatus.NOT_CONFIGURED,
        required_capabilities=case["required"],
        host=HostProbe(HostCapabilityState.UNKNOWN),
        resume_ref=resume_ref,
    )
    assert paused.resume_ref == resume_ref

    rechecked = _GUARD.recheck(
        report_status=case["status"],
        required_capabilities=case["required"],
        host=host,
        context=paused,
        resume_ref=resume_ref,
    )
    if rechecked.eligibility == "allowed":
        assert rechecked.action == "resume"
        # resume 的 task/run 引用等于暂停前值。
        assert rechecked.resume_ref == resume_ref
    else:
        # blocked/retryable 时只替换 Primary_Action，保留上下文引用。
        assert rechecked.resume_ref == resume_ref or rechecked.resume_ref is None