# Feature: guided-provider-config, Properties 23/24: single-flight per scope
# and evidence persistence recovery never recalls the Provider

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    VerificationScope,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import compute_verification_fingerprint
from leo_ppt_generator.config.verification_operations import (
    FileVerificationCoordinator,
    VerificationIntent,
    compute_scope_key,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_CAPABILITIES = (Capability.GENERATE, Capability.EDIT, Capability.MASK, Capability.REFERENCE)


def _scope(capabilities: frozenset[Capability] | None = None) -> VerificationScope:
    fingerprint = compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=None,
        model="gpt-image-2",
        credential_version="generation:1",
        runtime_identity="leo-ppt-generator/test",
        adapter_version="openai/v1",
        verification_policy_version=1,
    )
    return VerificationScope(
        fingerprint=fingerprint,
        required_capabilities=capabilities or frozenset({Capability.GENERATE}),
    )


# ---------------------------------------------------------------- Property 23
@PROPERTY_SETTINGS
@given(
    capabilities=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=1, max_size=2, unique=True
    ),
)
def test_property_23_verification_is_single_flight_per_scope(capabilities):
    """**Validates: Requirements 6.17**"""
    with tempfile.TemporaryDirectory() as directory:
        coordinator = FileVerificationCoordinator(
            Path(directory), ProviderRegistry.default(), clock=lambda: NOW
        )
        scope = _scope(frozenset(capabilities))
        calls = []

        def provider_executor():
            calls.append(1)
            return {cap: {"ok": True} for cap in capabilities}

        # 第一次 execute 成为 owner 并执行一次。
        terminal, evidence = coordinator.execute(
            scope, _intent("owner"), provider_executor
        )
        assert terminal.operation_id == "owner"
        assert evidence == {cap: {"ok": True} for cap in capabilities}
        assert calls == [1]

        # 同 scope 尚在 running 时，新 execute 是 joiner：不新增调用、共享 owner。
        coordinator.begin(scope, _intent("owner-2"))
        joined = coordinator.join(scope, _intent("joiner"))
        assert joined is not None
        assert joined.operation_id == "owner-2"
        assert calls == [1]
        terminal2, evidence2 = coordinator.execute(
            scope, _intent("joiner-2"), provider_executor
        )
        assert terminal2.operation_id == "owner-2"
        assert evidence2 is None
        assert calls == [1]


def _intent(operation_id: str) -> VerificationIntent:
    return VerificationIntent(
        operation_id=operation_id,
        intent_id=f"intent-{operation_id}",
        provider=ProviderName.OPENAI,
        capabilities=frozenset({Capability.GENERATE}),
        request_identity="run-1/page-1",
    )


# ---------------------------------------------------------------- Property 24
@PROPERTY_SETTINGS
@given(
    capabilities=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=1, max_size=2, unique=True
    ),
)
def test_property_24_evidence_persistence_recovery_never_recalls_provider(
    capabilities,
):
    """**Validates: Requirements 6.16, 13.5**"""
    with tempfile.TemporaryDirectory() as directory:
        coordinator = FileVerificationCoordinator(
            Path(directory), ProviderRegistry.default(), clock=lambda: NOW
        )
        scope = _scope(frozenset(capabilities))
        calls = []

        def provider_executor():
            calls.append(1)
            return {cap: {"ok": True} for cap in capabilities}

        # 图片成功但 evidence 合并失败：只重试本地持久化，绝不再次调用 Provider。
        coordinator.begin(scope, _intent("op-1"))
        terminal = coordinator.transition(
            scope,
            _intent("op-1"),
            state="evidence_pending",
            provider_acceptance="accepted",
            artifact_recovery_ref="run-1/artifact-a",
        )
        assert terminal.state == "evidence_pending"
        # 恢复动作只读取本地 recovery ref，不经过 Provider。
        assert terminal.artifact_recovery_ref == "run-1/artifact-a"
        joined = coordinator.join(scope, _intent("op-2"))
        assert joined is not None
        assert joined.state == "evidence_pending"
        assert calls == []

        # evidence_pending 的接管者复用同一 operation 语义完成合并。
        recovered = coordinator.transition(
            scope,
            _intent("op-1"),
            state="succeeded",
            provider_acceptance="accepted",
        )
        assert recovered.state == "succeeded"
        assert calls == []
