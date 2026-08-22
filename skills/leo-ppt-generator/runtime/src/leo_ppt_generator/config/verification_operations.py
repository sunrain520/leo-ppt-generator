"""Verification_Scope 的跨进程 single-flight 协调与 operation journal。

同一 Verification_Scope 在有效 evidence 覆盖目标能力前最多一个可能计费
请求在途；joiner 等待同一结果，不自行创建付费调用。崩溃恢复按 journal
phase 与 Registry 幂等声明决定继续、共享或禁止重试。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from filelock import FileLock

from ..storage import atomic_write_json, fsync_directory
from .models import (
    Capability,
    ProviderName,
    VerificationFingerprint,
    VerificationScope,
)
from .provider_registry import ProviderRegistry
from .reason_codes import ReasonCode

OPERATION_PROTOCOL = "leo-ppt-verification-operation/v1"
OPERATION_DIRECTORY = "verification-operations"

OPERATION_STATES = ("running", "succeeded", "failed", "outcome_unknown", "evidence_pending")
ACCEPTANCE_STATES = ("not_sent", "accepted", "unknown")


class VerificationOperationError(ValueError):
    reason_code = "verification_operation_error"

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class VerificationIntent:
    """一次验证意图；同 scope 的重试与恢复复用同一 intent。"""

    operation_id: str
    intent_id: str
    provider: ProviderName
    capabilities: frozenset[Capability]
    request_identity: str  # 非敏感调用方意图标识（如 run id / page id）


@dataclass(frozen=True)
class JournalEntry:
    scope_key: str
    operation_id: str
    intent_id: str
    state: str
    attempt: int
    provider_acceptance: str
    required_capabilities: frozenset[Capability]
    reason_code: str | None = None
    artifact_recovery_ref: str | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": OPERATION_PROTOCOL,
            "schema_version": 1,
            "scope_key": self.scope_key,
            "operation_id": self.operation_id,
            "intent_id": self.intent_id,
            "state": self.state,
            "attempt": self.attempt,
            "provider_acceptance": self.provider_acceptance,
            "required_capabilities": sorted(
                capability.value for capability in self.required_capabilities
            ),
            "reason_code": self.reason_code,
            "artifact_recovery_ref": self.artifact_recovery_ref,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def compute_scope_key(
    fingerprint: VerificationFingerprint,
    capabilities: frozenset[Capability],
) -> str:
    """Verification_Scope 协调键：fingerprint + 排序去重能力集合。"""

    payload = {
        "fingerprint_sha256": fingerprint.sha256,
        "required_capabilities": sorted(
            capability.value for capability in capabilities
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class FileVerificationCoordinator:
    """以 scope FileLock 与原子 journal 协调 owner/joiner。"""

    def __init__(
        self,
        home: str | Path,
        registry: ProviderRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
        writer: Callable[[str | Path, Any], None] = atomic_write_json,
    ) -> None:
        self._directory = Path(home).resolve() / OPERATION_DIRECTORY
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))
        self._writer = writer

    def journal_path(self, scope_key: str) -> Path:
        return self._directory / f"{scope_key}.json"

    def _lock(self, scope_key: str) -> FileLock:
        return FileLock(
            str(self._directory / f".{scope_key}.json.lock"),
            is_singleton=True,
        )

    def _now(self) -> datetime:
        return self._clock()

    def read_journal(self, scope_key: str) -> JournalEntry | None:
        path = self.journal_path(scope_key)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return _parse_journal(value, scope_key)

    def begin(
        self,
        scope: VerificationScope,
        intent: VerificationIntent,
    ) -> JournalEntry:
        """以 owner 身份创建或复用 journal；返回当前 entry。"""

        scope_key = compute_scope_key(scope.fingerprint, scope.required_capabilities)
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock(scope_key):
            existing = self.read_journal(scope_key)
            if existing is not None:
                if existing.state not in {"succeeded", "failed", "outcome_unknown"}:
                    return existing
            entry = JournalEntry(
                scope_key=scope_key,
                operation_id=intent.operation_id,
                intent_id=intent.intent_id,
                state="running",
                attempt=1,
                provider_acceptance="not_sent",
                required_capabilities=frozenset(scope.required_capabilities),
                updated_at=self._now(),
            )
            self._writer(self.journal_path(scope_key), entry.to_dict())
            fsync_directory(self._directory)
            return entry

    def join(
        self,
        scope: VerificationScope,
        intent: VerificationIntent,
    ) -> JournalEntry | None:
        """以 joiner 身份读取现有 journal；无在途请求返回 None。"""

        scope_key = compute_scope_key(scope.fingerprint, scope.required_capabilities)
        entry = self.read_journal(scope_key)
        if entry is None or entry.state not in {"running", "evidence_pending"}:
            return None
        return entry

    def transition(
        self,
        scope: VerificationScope,
        intent: VerificationIntent,
        *,
        state: str,
        reason_code: str | None = None,
        provider_acceptance: str | None = None,
        artifact_recovery_ref: str | None = None,
    ) -> JournalEntry:
        if state not in OPERATION_STATES:
            raise VerificationOperationError("verification_operation_state_invalid")
        if provider_acceptance is not None and provider_acceptance not in ACCEPTANCE_STATES:
            raise VerificationOperationError("verification_acceptance_invalid")
        scope_key = compute_scope_key(scope.fingerprint, scope.required_capabilities)
        with self._lock(scope_key):
            current = self.read_journal(scope_key)
            if current is None:
                raise VerificationOperationError("verification_operation_missing")
            if current.operation_id != intent.operation_id:
                raise VerificationOperationError("verification_operation_id_invalid")
            entry = JournalEntry(
                scope_key=current.scope_key,
                operation_id=current.operation_id,
                intent_id=current.intent_id,
                state=state,
                attempt=current.attempt + (1 if state == "running" else 0),
                provider_acceptance=(
                    provider_acceptance or current.provider_acceptance
                ),
                required_capabilities=current.required_capabilities,
                reason_code=reason_code if reason_code is not None else current.reason_code,
                artifact_recovery_ref=(
                    artifact_recovery_ref
                    if artifact_recovery_ref is not None
                    else current.artifact_recovery_ref
                ),
                updated_at=self._now(),
            )
            self._writer(self.journal_path(scope_key), entry.to_dict())
            fsync_directory(self._directory)
            return entry

    def execute(
        self,
        scope: VerificationScope,
        intent: VerificationIntent,
        provider_executor: Callable[[], Mapping[Capability, Any]],
    ) -> tuple[JournalEntry, Mapping[Capability, Any] | None]:
        """single-flight 执行：owner 调用 provider，joiner 共享结果。

        锁只在 begin/transition 的原子检查区间持有；Provider 调用本身在
        锁外执行，使并发 joiner 能在 owner 在途时读到 running journal。
        """

        scope_key = compute_scope_key(scope.fingerprint, scope.required_capabilities)
        owner = self.begin(scope, intent)
        if owner.operation_id != intent.operation_id:
            # 已有其他 owner 在途：共享其结果（不发起新付费调用）。
            return owner, None
        try:
            evidence = provider_executor()
            terminal = self.transition(
                scope,
                intent,
                state="succeeded",
                provider_acceptance="accepted",
            )
            return terminal, evidence
        except Exception as error:
            reason = str(error) or getattr(
                error, "reason_code", ReasonCode.PROVIDER_OUTCOME_UNKNOWN.value
            )
            terminal = self.transition(
                scope,
                intent,
                state="failed",
                reason_code=reason,
                provider_acceptance="accepted",
            )
            raise


def _parse_journal(value: Any, expected_scope_key: str) -> JournalEntry:
    if not isinstance(value, dict) or value.get("protocol") != OPERATION_PROTOCOL:
        raise VerificationOperationError("verification_operation_invalid")
    if value.get("scope_key") != expected_scope_key:
        raise VerificationOperationError("verification_operation_invalid")
    state = value.get("state")
    if state not in OPERATION_STATES:
        raise VerificationOperationError("verification_operation_state_invalid")
    required = frozenset(
        Capability(item) for item in value.get("required_capabilities", [])
    )
    return JournalEntry(
        scope_key=expected_scope_key,
        operation_id=str(value["operation_id"]),
        intent_id=str(value["intent_id"]),
        state=state,
        attempt=int(value.get("attempt", 1)),
        provider_acceptance=str(value.get("provider_acceptance", "unknown")),
        required_capabilities=required,
        reason_code=value.get("reason_code"),
        artifact_recovery_ref=value.get("artifact_recovery_ref"),
    )


VerificationCoordinator = FileVerificationCoordinator

__all__ = [
    "FileVerificationCoordinator",
    "JournalEntry",
    "VerificationCoordinator",
    "VerificationIntent",
    "VerificationOperationError",
    "compute_scope_key",
]
