"""确定性的 Provider 配置 readiness 与 ConfigReport 组装内核。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterable

from ..application.routes import ROUTE_CAPABILITY_RESOLVER
from .models import (
    Capability,
    ConfigurationState,
    ConfigReport,
    ConfigStatus,
    CredentialReferenceType,
    ExecutionEligibility,
    HostCapabilityState,
    InstallationReadiness,
    PrimaryAction,
    PrimaryActionKind,
    ProviderName,
    ProviderReport,
    ReadinessScope,
    RouteName,
    VerificationState,
)
from .reason_codes import ActionIntent, ReasonCode, reason_definition
from .receipt_store import ReceiptInspection


ActionMaterializer = Callable[[ActionIntent], PrimaryAction]


@dataclass(frozen=True, slots=True)
class ProviderReadinessFacts:
    """一个 Provider 的本地事实；不包含任何聚合状态规则。"""

    provider: ProviderName
    configuration_state: ConfigurationState
    reason_code: ReasonCode
    candidate_capabilities: frozenset[Capability]
    credential_reference_type: CredentialReferenceType
    receipt: ReceiptInspection | None = None
    fingerprint_sha256: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", ProviderName(self.provider))
        object.__setattr__(
            self, "configuration_state", ConfigurationState(self.configuration_state)
        )
        object.__setattr__(self, "reason_code", ReasonCode(self.reason_code))
        object.__setattr__(
            self,
            "candidate_capabilities",
            frozenset(Capability(item) for item in self.candidate_capabilities),
        )
        object.__setattr__(
            self,
            "credential_reference_type",
            CredentialReferenceType(self.credential_reference_type),
        )
        if self.receipt is not None and self.receipt.provider is not self.provider:
            raise ValueError("receipt provider must match provider facts")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("provider evidence_refs must not contain duplicates")


@dataclass(frozen=True, slots=True)
class OperationContext:
    """仅描述当前 Provider 操作；历史失败不得构造该对象。"""

    provider: ProviderName
    reason_code: ReasonCode
    degraded: bool
    resume_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", ProviderName(self.provider))
        object.__setattr__(self, "reason_code", ReasonCode(self.reason_code))
        if not isinstance(self.degraded, bool):
            raise ValueError("degraded must be a boolean")
        if self.resume_ref is not None and not self.resume_ref.strip():
            raise ValueError("resume_ref must not be empty")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("operation evidence_refs must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ReadinessDecision:
    status: ConfigStatus
    configuration_state: ConfigurationState
    verification_state: VerificationState
    execution_eligibility: ExecutionEligibility
    installation_readiness: InstallationReadiness
    readiness_scope: ReadinessScope
    reason_code: ReasonCode
    selected_provider: ProviderName | None
    providers: tuple[ProviderReport, ...]
    evidence_refs: tuple[str, ...]
    action_intent: ActionIntent | None


def _current_verified_capabilities(
    receipt: ReceiptInspection | None,
) -> frozenset[Capability]:
    """只接受 ReceiptStore 已确认属于当前 fingerprint 的有效证据。"""

    if (
        receipt is None
        or receipt.status != "valid"
        or not receipt.fingerprint_matches
    ):
        return frozenset()
    return receipt.verified_capabilities


def build_readiness_scope(
    *,
    route: RouteName | str | None = None,
    task_capabilities: Iterable[Capability | str] = (),
    receipt: ReceiptInspection | None = None,
    fingerprint_sha256: str | None = None,
) -> ReadinessScope:
    """从 Route owner 与有效 receipt evidence 构造当前 scope。"""

    selected_route = RouteName.GENERATE if route is None else RouteName(route)
    required = ROUTE_CAPABILITY_RESOLVER.resolve(selected_route, task_capabilities)
    verified = required & _current_verified_capabilities(receipt)
    return ReadinessScope(
        route=selected_route,
        required_capabilities=required,
        verified_capabilities=verified,
        missing_capabilities=required - verified,
        fingerprint_sha256=fingerprint_sha256,
    )


def _verification_state(
    scope: ReadinessScope,
    receipt: ReceiptInspection | None,
    operation: OperationContext | None,
) -> VerificationState:
    if operation is not None:
        return VerificationState.FAILED
    if not scope.missing_capabilities:
        return VerificationState.PASSED
    if receipt is None:
        return VerificationState.NOT_RUN
    fingerprint_stale = receipt.status == "stale" and not receipt.fingerprint_matches
    required_evidence_expired = bool(
        scope.required_capabilities & receipt.expired_capabilities
    )
    if fingerprint_stale or required_evidence_expired:
        return VerificationState.STALE
    return VerificationState.NOT_RUN


def _effective_configuration(
    facts: ProviderReadinessFacts,
    scope_compatible: bool,
) -> ConfigurationState:
    if (
        facts.configuration_state is ConfigurationState.LOCALLY_CONFIGURED
        and not scope_compatible
    ):
        return ConfigurationState.INVALID
    return facts.configuration_state


def _provider_report(
    facts: ProviderReadinessFacts,
    route: RouteName,
    required: frozenset[Capability],
    operation: OperationContext | None,
) -> ProviderReport:
    compatible = required.issubset(facts.candidate_capabilities)
    configuration = _effective_configuration(facts, compatible)
    verified = required & _current_verified_capabilities(facts.receipt)
    scope = ReadinessScope(
        route=route,
        required_capabilities=required,
        verified_capabilities=verified,
        missing_capabilities=required - verified,
        fingerprint_sha256=facts.fingerprint_sha256,
    )
    verification = _verification_state(scope, facts.receipt, operation)
    if operation is not None:
        reason = operation.reason_code.value
    elif configuration is ConfigurationState.INVALID and facts.configuration_state is not ConfigurationState.INVALID:
        reason = ReasonCode.PROVIDER_PROFILE_INVALID.value
    elif verification is VerificationState.PASSED:
        reason = ReasonCode.CONFIGURATION_READY.value
    elif verification is VerificationState.STALE:
        reason = ReasonCode.PROVIDER_VERIFICATION_STALE.value
    else:
        reason = facts.reason_code.value
    refs = _evidence_refs(facts, operation)
    return ProviderReport(
        provider=facts.provider,
        configuration_state=configuration,
        verification_state=verification,
        candidate_capabilities=facts.candidate_capabilities,
        scope_compatible=compatible,
        credential_reference_type=facts.credential_reference_type,
        reason_code=reason,
        evidence_refs=refs,
    )


def _evidence_refs(
    facts: ProviderReadinessFacts,
    operation: OperationContext | None,
) -> tuple[str, ...]:
    receipt_refs: tuple[str, ...] = ()
    if facts.receipt is not None:
        receipt_refs = tuple(facts.receipt.to_dict()["evidence_refs"])
    operation_refs = operation.evidence_refs if operation is not None else ()
    return tuple(dict.fromkeys((*facts.evidence_refs, *receipt_refs, *operation_refs)))


def _eligibility(status: ConfigStatus) -> ExecutionEligibility:
    if status in {ConfigStatus.READY, ConfigStatus.CONFIGURED_UNVERIFIED}:
        return ExecutionEligibility.ALLOWED
    if status is ConfigStatus.DEGRADED:
        return ExecutionEligibility.RETRYABLE
    return ExecutionEligibility.BLOCKED


def _installation_readiness(
    status: ConfigStatus,
    eligibility: ExecutionEligibility,
) -> InstallationReadiness:
    if status is ConfigStatus.READY:
        return InstallationReadiness.READY
    if status is ConfigStatus.CONFIGURED_UNVERIFIED:
        return InstallationReadiness.USABLE_UNVERIFIED
    if eligibility in {ExecutionEligibility.BLOCKED, ExecutionEligibility.RETRYABLE}:
        return InstallationReadiness.INSTALLED_NOT_READY
    raise ValueError("installation readiness mapping is incomplete")


def _action_intent(
    reason_code: ReasonCode,
    operation: OperationContext | None,
) -> ActionIntent | None:
    intent = reason_definition(reason_code).default_action
    if intent is not None and operation is not None and operation.resume_ref is not None:
        if intent.kind is PrimaryActionKind.RESUME_TASK:
            intent = replace(intent, resume_ref=operation.resume_ref)
    return intent


def evaluate_readiness(
    providers: Iterable[ProviderReadinessFacts],
    *,
    selected_provider: ProviderName | str | None,
    route: RouteName | str | None = None,
    task_capabilities: Iterable[Capability | str] = (),
    host_capability_state: HostCapabilityState = HostCapabilityState.UNKNOWN,
    host_capabilities: Iterable[Capability | str] = (),
    operation_context: OperationContext | None = None,
) -> ReadinessDecision:
    """按合同优先级聚合一次确定性的 readiness 决策。"""

    ordered = tuple(sorted(providers, key=lambda item: item.provider.value))
    by_provider = {item.provider: item for item in ordered}
    if len(by_provider) != len(ordered):
        raise ValueError("providers must not contain duplicates")
    selected = None if selected_provider is None else ProviderName(selected_provider)
    if selected is not None and selected not in by_provider:
        raise ValueError("selected_provider must appear in providers")
    if operation_context is not None and operation_context.provider not in by_provider:
        raise ValueError("operation_context provider must appear in providers")
    selected_facts = by_provider.get(selected) if selected is not None else None
    selected_receipt = selected_facts.receipt if selected_facts is not None else None
    scope = build_readiness_scope(
        route=route,
        task_capabilities=task_capabilities,
        receipt=selected_receipt,
        fingerprint_sha256=(
            selected_facts.fingerprint_sha256 if selected_facts is not None else None
        ),
    )
    host_state = HostCapabilityState(host_capability_state)
    live_host_capabilities = frozenset(Capability(item) for item in host_capabilities)
    host_covers = (
        host_state is HostCapabilityState.AVAILABLE
        and scope.required_capabilities.issubset(live_host_capabilities)
    )
    selected_operation = (
        operation_context
        if selected is not None and operation_context is not None
        and operation_context.provider is selected
        else None
    )

    verification = _verification_state(scope, selected_receipt, selected_operation)
    compatible = (
        selected_facts is not None
        and scope.required_capabilities.issubset(
            selected_facts.candidate_capabilities
        )
    )
    configuration = (
        ConfigurationState.NOT_CONFIGURED
        if selected_facts is None
        else _effective_configuration(selected_facts, compatible)
    )

    # 优先级：invalid → not_configured → operation-local degraded → ready → unverified。
    if configuration is ConfigurationState.INVALID:
        status = ConfigStatus.INVALID
        reason = (
            selected_facts.reason_code
            if selected_facts is not None
            and selected_facts.configuration_state is ConfigurationState.INVALID
            else ReasonCode.PROVIDER_PROFILE_INVALID
        )
    elif configuration is not ConfigurationState.LOCALLY_CONFIGURED and not host_covers:
        status = ConfigStatus.NOT_CONFIGURED
        reason = (
            selected_facts.reason_code
            if selected_facts is not None
            else ReasonCode.PROVIDER_SELECTION_REQUIRED
        )
    elif selected_operation is not None and selected_operation.degraded:
        status = ConfigStatus.DEGRADED
        reason = selected_operation.reason_code
    elif not scope.missing_capabilities or host_covers:
        status = ConfigStatus.READY
        reason = ReasonCode.CONFIGURATION_READY
    else:
        status = ConfigStatus.CONFIGURED_UNVERIFIED
        reason = (
            ReasonCode.PROVIDER_VERIFICATION_STALE
            if verification is VerificationState.STALE
            else ReasonCode.PROVIDER_VERIFICATION_NOT_RUN
        )

    eligibility = _eligibility(status)
    provider_reports = tuple(
        _provider_report(
            facts,
            scope.route,
            scope.required_capabilities,
            operation_context
            if operation_context is not None
            and operation_context.provider is facts.provider
            else None,
        )
        for facts in ordered
    )
    refs = (
        _evidence_refs(selected_facts, selected_operation)
        if selected_facts is not None
        else (operation_context.evidence_refs if selected_operation is not None else ())
    )
    return ReadinessDecision(
        status=status,
        configuration_state=configuration,
        verification_state=verification,
        execution_eligibility=eligibility,
        installation_readiness=_installation_readiness(status, eligibility),
        readiness_scope=scope,
        reason_code=reason,
        selected_provider=selected,
        providers=provider_reports,
        evidence_refs=refs,
        action_intent=_action_intent(reason, selected_operation),
    )


def _materialize_action(
    intent: ActionIntent | None,
    materializer: ActionMaterializer | None,
) -> PrimaryAction | None:
    if intent is None:
        return None
    if materializer is None:
        if intent.kind is PrimaryActionKind.RUN_CLI:
            raise ValueError("run_cli action requires an ActionMaterializer")
        action = PrimaryAction(kind=intent.kind, resume_ref=intent.resume_ref)
    else:
        action = materializer(intent)
    if action.kind is not intent.kind:
        raise ValueError("materialized action kind must match reason catalog")
    if action.resume_ref != intent.resume_ref:
        raise ValueError("materialized action resume_ref must match reason catalog")
    return action


def build_config_report(
    providers: Iterable[ProviderReadinessFacts],
    *,
    selected_provider: ProviderName | str | None,
    route: RouteName | str | None = None,
    task_capabilities: Iterable[Capability | str] = (),
    host_capability_state: HostCapabilityState = HostCapabilityState.UNKNOWN,
    host_capabilities: Iterable[Capability | str] = (),
    operation_context: OperationContext | None = None,
    action_materializer: ActionMaterializer | None = None,
) -> ConfigReport:
    """从同一决策一次性组装机器协议；renderer 不得重新计算状态。"""

    decision = evaluate_readiness(
        providers,
        selected_provider=selected_provider,
        route=route,
        task_capabilities=task_capabilities,
        host_capability_state=host_capability_state,
        host_capabilities=host_capabilities,
        operation_context=operation_context,
    )
    return ConfigReport(
        stage=reason_definition(decision.reason_code).stage.value,
        status=decision.status,
        configuration_state=decision.configuration_state,
        verification_state=decision.verification_state,
        execution_eligibility=decision.execution_eligibility,
        installation_readiness=decision.installation_readiness,
        readiness_scope=decision.readiness_scope,
        reason_code=decision.reason_code.value,
        selected_provider=decision.selected_provider,
        providers=decision.providers,
        evidence_refs=decision.evidence_refs,
        primary_action=_materialize_action(
            decision.action_intent, action_materializer
        ),
    )


__all__ = [
    "ActionMaterializer",
    "OperationContext",
    "ProviderReadinessFacts",
    "ReadinessDecision",
    "build_config_report",
    "build_readiness_scope",
    "evaluate_readiness",
]
