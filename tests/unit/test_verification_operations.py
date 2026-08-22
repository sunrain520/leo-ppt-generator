"""VerificationCoordinator 与 operation journal 的单元测试。"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    VerificationOperationError,
    compute_scope_key,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _scope() -> VerificationScope:
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
        required_capabilities=frozenset({Capability.GENERATE}),
    )


def _intent(operation_id: str = "operation-1") -> VerificationIntent:
    return VerificationIntent(
        operation_id=operation_id,
        intent_id=f"intent-{operation_id}",
        provider=ProviderName.OPENAI,
        capabilities=frozenset({Capability.GENERATE}),
        request_identity="run-1/page-1",
    )


def _coordinator(home: Path) -> FileVerificationCoordinator:
    return FileVerificationCoordinator(
        home, ProviderRegistry.default(), clock=lambda: NOW
    )


def test_scope_key_is_deterministic_and_capability_sensitive():
    scope = _scope()
    key1 = compute_scope_key(scope.fingerprint, scope.required_capabilities)
    key2 = compute_scope_key(scope.fingerprint, scope.required_capabilities)
    assert key1 == key2
    other = compute_scope_key(
        scope.fingerprint, frozenset({Capability.EDIT})
    )
    assert other != key1


def test_begin_writes_journal_and_join_shares_same_owner():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        coordinator = _coordinator(home)
        scope = _scope()
        owner = coordinator.begin(scope, _intent("op-owner"))
        assert owner.state == "running"
        assert owner.operation_id == "op-owner"
        # 同 scope 新 intent 作为 joiner 返回同一 owner。
        joined = coordinator.join(scope, _intent("op-joiner"))
        assert joined is not None
        assert joined.operation_id == "op-owner"
        # journal 持久化且不含 secret。
        payload = json.loads(
            coordinator.journal_path(owner.scope_key).read_text()
        )
        assert payload["protocol"] == "leo-ppt-verification-operation/v1"
        assert "secret" not in json.dumps(payload).lower()


def test_join_returns_none_without_running_journal():
    with tempfile.TemporaryDirectory() as directory:
        coordinator = _coordinator(Path(directory))
        assert coordinator.join(_scope(), _intent()) is None


def test_transition_to_terminal_state_and_reuse():
    with tempfile.TemporaryDirectory() as directory:
        coordinator = _coordinator(Path(directory))
        scope = _scope()
        coordinator.begin(scope, _intent("op-1"))
        terminal = coordinator.transition(
            scope,
            _intent("op-1"),
            state="succeeded",
            provider_acceptance="accepted",
        )
        assert terminal.state == "succeeded"
        # 新 intent 在 terminal 后不能复用同一 journal 的 operation id。
        coordinator.begin(scope, _intent("op-2"))
        with pytest.raises(VerificationOperationError):
            coordinator.transition(scope, _intent("op-1"), state="failed")


def test_transition_rejects_unknown_state():
    with tempfile.TemporaryDirectory() as directory:
        coordinator = _coordinator(Path(directory))
        scope = _scope()
        coordinator.begin(scope, _intent("op-1"))
        with pytest.raises(VerificationOperationError):
            coordinator.transition(scope, _intent("op-1"), state="bogus")


def test_execute_single_flight_calls_provider_once():
    with tempfile.TemporaryDirectory() as directory:
        coordinator = _coordinator(Path(directory))
        scope = _scope()
        calls = []

        def provider_executor():
            calls.append(1)
            return {Capability.GENERATE: {"ok": True}}

        terminal, evidence = coordinator.execute(scope, _intent("op-1"), provider_executor)
        assert terminal.state == "succeeded"
        assert evidence == {Capability.GENERATE: {"ok": True}}
        assert len(calls) == 1

        # 已 terminal 的 scope：新 intent 可以重新 begin（合法，非并发）。
        new_terminal, new_evidence = coordinator.execute(
            scope, _intent("op-2"), provider_executor
        )
        assert new_terminal.operation_id == "op-2"
        assert new_evidence == {Capability.GENERATE: {"ok": True}}
        assert len(calls) == 2

        # 并发在途：第二个 intent 作为 joiner 共享 owner，不产生新调用。
        coordinator.begin(scope, _intent("op-3"))
        joined = coordinator.join(scope, _intent("op-4"))
        assert joined is not None
        assert joined.operation_id == "op-3"


def test_execute_failure_records_reason_and_acceptance():
    with tempfile.TemporaryDirectory() as directory:
        coordinator = _coordinator(Path(directory))
        scope = _scope()

        def failing_executor():
            raise RuntimeError("500 Internal Server Error")

        with pytest.raises(RuntimeError):
            coordinator.execute(scope, _intent("op-1"), failing_executor)
        entry = coordinator.read_journal(
            compute_scope_key(scope.fingerprint, scope.required_capabilities)
        )
        assert entry is not None
        assert entry.state == "failed"
        assert entry.provider_acceptance == "accepted"
