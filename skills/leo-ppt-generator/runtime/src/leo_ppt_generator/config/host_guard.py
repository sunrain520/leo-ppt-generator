"""Host_Readiness_Guard：宿主首次调用前的就绪检查与任务恢复。

Guard 是 capability-local 且 receipt-independent：只有当前宿主现场确认的
Host_Provider 能覆盖能力；改变 host 状态不得改变 External Verification_State
或 receipt bytes。pause 保留任务上下文；recheck allowed 后 resume 同一节点。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..config.models import Capability, ConfigStatus, HostCapabilityState
from ..config.reason_codes import (
    ActionIntent,
    CommandRenderer,
    PrimaryActionKind,
    ReasonCode,
    ShellKind,
)
from ..config.readiness import OperationContext


class HostGuardError(ValueError):
    reason_code = "host_guard_error"


@dataclass(frozen=True)
class HostProbe:
    """宿主现场能力探测的只读事实。"""

    state: HostCapabilityState
    capabilities: frozenset[Capability] = frozenset()

    @classmethod
    def unknown(cls) -> "HostProbe":
        return cls(HostCapabilityState.UNKNOWN)

    @property
    def requires_host_check(self) -> bool:
        return self.state is HostCapabilityState.UNKNOWN

    def covers(self, required: frozenset[Capability]) -> bool:
        return (
            self.state is HostCapabilityState.AVAILABLE
            and required.issubset(self.capabilities)
        )


@dataclass(frozen=True)
class GuardDecision:
    """Host guard 的一次确定性决策。"""

    action: str  # continue | pause | blocked_invalid
    eligibility: str  # allowed | retryable | blocked
    reason_code: str
    primary_action: Mapping[str, Any] | None = None
    lazy_verification: bool = False
    resume_ref: str | None = None


class HostReadinessGuard:
    """把 config report 与宿主现场能力组合成 guard 决策。"""

    def __init__(
        self,
        *,
        renderer: CommandRenderer | None = None,
        status_provider: Callable[[str], ConfigStatus] | None = None,
        cli_path: str | None = None,
        shell: ShellKind | str = ShellKind.POSIX,
    ) -> None:
        self.renderer = renderer or CommandRenderer(shell)
        self.status_provider = status_provider
        self.cli_path = cli_path

    def evaluate(
        self,
        *,
        report_status: ConfigStatus | str,
        required_capabilities: frozenset[Capability],
        host: HostProbe,
        operation_context: OperationContext | None = None,
        reason_code: str | None = None,
        resume_ref: str | None = None,
    ) -> GuardDecision:
        """按合同优先级决策：invalid → not_configured → degraded → ready/配置未验证。"""

        status = ConfigStatus(report_status)
        result_reason = reason_code or _reason_for(status)

        # host 现场覆盖能力：继续，不要求外部 Key。
        if host.covers(required_capabilities):
            return GuardDecision(
                action="continue",
                eligibility="allowed",
                reason_code=result_reason,
                resume_ref=resume_ref,
            )

        if status is ConfigStatus.INVALID or status is ConfigStatus.NOT_CONFIGURED:
            return GuardDecision(
                action="blocked_invalid",
                eligibility="blocked",
                reason_code=result_reason,
                primary_action=_run_cli_action(
                    self.renderer,
                    self.cli_path,
                    ReasonCode.CONFIG_INVALID
                    if status is ConfigStatus.INVALID
                    else ReasonCode.PROVIDER_SELECTION_REQUIRED,
                ),
                resume_ref=resume_ref,
            )

        if status is ConfigStatus.DEGRADED:
            return GuardDecision(
                action="pause",
                eligibility="retryable",
                reason_code=result_reason,
                primary_action=_operation_action(
                    self.renderer, self.cli_path, operation_context
                ),
                resume_ref=resume_ref,
            )

        if status is ConfigStatus.READY:
            return GuardDecision(
                action="continue",
                eligibility="allowed",
                reason_code=result_reason,
                resume_ref=resume_ref,
            )

        # configured_unverified：继续到首张业务图片，完成惰性验证。
        return GuardDecision(
            action="continue",
            eligibility="allowed",
            reason_code=result_reason,
            lazy_verification=True,
            resume_ref=resume_ref,
        )

    def recheck(
        self,
        *,
        report_status: ConfigStatus | str,
        required_capabilities: frozenset[Capability],
        host: HostProbe,
        context: GuardDecision | None = None,
        reason_code: str | None = None,
        resume_ref: str | None = None,
    ) -> GuardDecision:
        """用户完成配置后复查；allowed 转 resume，blocked/retryable 更新唯一动作。"""

        decision = self.evaluate(
            report_status=report_status,
            required_capabilities=required_capabilities,
            host=host,
            reason_code=reason_code,
            resume_ref=resume_ref or (context.resume_ref if context else None),
        )
        if decision.eligibility == "allowed" and context is not None:
            return GuardDecision(
                action="resume",
                eligibility="allowed",
                reason_code=decision.reason_code,
                primary_action=decision.primary_action,
                lazy_verification=decision.lazy_verification,
                resume_ref=resume_ref or context.resume_ref,
            )
        return decision


def _reason_for(status: ConfigStatus) -> str:
    return {
        ConfigStatus.INVALID: ReasonCode.CONFIG_INVALID.value,
        ConfigStatus.NOT_CONFIGURED: ReasonCode.PROVIDER_SELECTION_REQUIRED.value,
        ConfigStatus.DEGRADED: ReasonCode.PROVIDER_TIMEOUT.value,
        ConfigStatus.READY: ReasonCode.CONFIGURATION_READY.value,
        ConfigStatus.CONFIGURED_UNVERIFIED: ReasonCode.PROVIDER_VERIFICATION_NOT_RUN.value,
    }.get(status, ReasonCode.CONFIG_PROTOCOL_INVALID.value)


def _run_cli_action(
    renderer: CommandRenderer,
    cli_path: str | None,
    reason: ReasonCode,
) -> Mapping[str, Any] | None:
    if cli_path is None:
        return {"kind": PrimaryActionKind.RUN_CLI.value, "command": None}
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=reason,
        command_verb=_verb_for(reason),
    )
    action = renderer.render(intent, cli_path=cli_path)
    return action.to_dict() if action is not None else None


def _verb_for(reason: ReasonCode):
    from ..config.reason_codes import ConfigCommandVerb

    if reason is ReasonCode.CONFIG_INVALID:
        return ConfigCommandVerb.REPAIR
    return ConfigCommandVerb.CONFIG


def _operation_action(
    renderer: CommandRenderer,
    cli_path: str | None,
    operation_context: OperationContext | None,
) -> Mapping[str, Any] | None:
    if operation_context is None:
        return None
    return {
        "kind": PrimaryActionKind.WAIT_AND_RETRY.value
        if operation_context.degraded
        else PrimaryActionKind.RESUME_TASK.value,
        "command": None,
        "resume_ref": operation_context.resume_ref,
    }


__all__ = [
    "GuardDecision",
    "HostGuardError",
    "HostProbe",
    "HostReadinessGuard",
]