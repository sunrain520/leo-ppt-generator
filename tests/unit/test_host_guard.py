"""Host_Readiness_Guard 与任务恢复的单元测试。"""

from __future__ import annotations

import pytest

from leo_ppt_generator.config.host_guard import HostProbe, HostReadinessGuard
from leo_ppt_generator.config.models import (
    Capability,
    ConfigStatus,
    HostCapabilityState,
)
from leo_ppt_generator.config.readiness import OperationContext
from leo_ppt_generator.config.reason_codes import ReasonCode

REQUIRED = frozenset({Capability.GENERATE})
ALL = frozenset(Capability)


def _guard() -> HostReadinessGuard:
    return HostReadinessGuard(cli_path="/usr/local/bin/leo-ppt")


def test_host_available_covers_and_allows():
    decision = _guard().evaluate(
        report_status=ConfigStatus.NOT_CONFIGURED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.AVAILABLE, ALL),
    )
    assert decision.action == "continue"
    assert decision.eligibility == "allowed"


def test_host_unavailable_with_ready_external_allows():
    decision = _guard().evaluate(
        report_status=ConfigStatus.READY,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
    )
    assert decision.action == "continue"
    assert decision.eligibility == "allowed"


def test_unverified_allows_with_lazy_verification():
    decision = _guard().evaluate(
        report_status=ConfigStatus.CONFIGURED_UNVERIFIED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
    )
    assert decision.action == "continue"
    assert decision.eligibility == "allowed"
    assert decision.lazy_verification is True


def test_not_configured_blocks_with_cli_action():
    decision = _guard().evaluate(
        report_status=ConfigStatus.NOT_CONFIGURED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
    )
    assert decision.action == "blocked_invalid"
    assert decision.eligibility == "blocked"
    assert decision.primary_action is not None
    assert decision.primary_action["kind"] == "run_cli"
    assert "config" in decision.primary_action["command"]


def test_invalid_blocks_with_repair_action():
    decision = _guard().evaluate(
        report_status=ConfigStatus.INVALID,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
    )
    assert decision.action == "blocked_invalid"
    assert decision.eligibility == "blocked"
    assert decision.primary_action is not None
    assert "repair" in decision.primary_action["command"]


def test_degraded_pauses_and_keeps_context():
    operation = OperationContext(
        provider="openai",
        reason_code=ReasonCode.PROVIDER_TIMEOUT,
        degraded=True,
        resume_ref="run-1/stage-image",
    )
    decision = _guard().evaluate(
        report_status=ConfigStatus.DEGRADED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
        operation_context=operation,
        reason_code="provider_timeout",
    )
    assert decision.action == "pause"
    assert decision.eligibility == "retryable"
    assert decision.primary_action is not None
    assert decision.primary_action["kind"] == "wait_and_retry"


def test_recheck_resumes_same_task_state():
    guard = _guard()
    paused = guard.evaluate(
        report_status=ConfigStatus.NOT_CONFIGURED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
        resume_ref="run-1/stage-image",
    )
    assert paused.action == "blocked_invalid"

    rechecked = guard.recheck(
        report_status=ConfigStatus.CONFIGURED_UNVERIFIED,
        required_capabilities=REQUIRED,
        host=HostProbe(HostCapabilityState.UNKNOWN),
        context=paused,
        resume_ref="run-1/stage-image",
    )
    assert rechecked.action == "resume"
    assert rechecked.eligibility == "allowed"
    assert rechecked.resume_ref == "run-1/stage-image"


def test_host_state_change_never_mutates_external_receipt():
    """改变 host 状态不得改变 External Verification_State（receipt bytes 不变）。"""
    guard = _guard()
    for host in (
        HostProbe(HostCapabilityState.UNKNOWN),
        HostProbe(HostCapabilityState.AVAILABLE, ALL),
        HostProbe(HostCapabilityState.UNAVAILABLE),
    ):
        decision = guard.evaluate(
            report_status=ConfigStatus.CONFIGURED_UNVERIFIED,
            required_capabilities=REQUIRED,
            host=host,
        )
        # host 状态只影响 action/eligibility，不隐含 External ready。
        assert decision.reason_code == "provider_verification_not_run"