"""Config 事务：凭据覆盖、profile 更新与 Provider change 的崩溃一致性。

事务状态机：prepared → receipt_invalidated → credential_written →
config_committed → completed。每一步原子写非敏感 checkpoint；凭据覆盖
严格先失效 receipt，再写 Credential_Store，最后 CAS 提交 generation。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from filelock import FileLock

from ..credentials import SecretBuffer
from ..storage import atomic_write_json, canonical_json, fsync_directory
from .models import ProviderName
from .runtime_config import ConfigStore, RuntimeConfig, RuntimeConfigError
from . import models as domain

TRANSACTION_PROTOCOL = "leo-ppt-config-transaction/v1"
TRANSACTION_DIRECTORY = "config-operations"
TRANSACTION_STATES = (
    "prepared",
    "receipt_invalidated",
    "credential_written",
    "config_committed",
    "completed",
)


class ConfigTransactionError(ValueError):
    reason_code = "credential_transaction_inconsistent"

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TransactionCheckpoint:
    operation_id: str
    provider: ProviderName
    step: str
    old_config_digest: str | None = None
    new_config_digest: str | None = None
    target_generation: int | None = None
    credential_write_id: str | None = None
    profile_digest: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", ProviderName(self.provider))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": TRANSACTION_PROTOCOL,
            "schema_version": 1,
            "operation_id": self.operation_id,
            "provider": self.provider.value,
            "step": self.step,
            "old_config_digest": self.old_config_digest,
            "new_config_digest": self.new_config_digest,
            "target_generation": self.target_generation,
            "credential_write_id": self.credential_write_id,
            "profile_digest": self.profile_digest,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConfigTransactionJournal:
    """config-operations 目录下的原子 checkpoint journal。"""

    def __init__(
        self,
        home: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        writer: Callable[[str | Path, Any], None] = atomic_write_json,
    ) -> None:
        self._directory = Path(home).resolve() / TRANSACTION_DIRECTORY
        self._clock = clock or (lambda: datetime.now(UTC))
        self._writer = writer

    def path(self, operation_id: str) -> Path:
        return self._directory / f"{operation_id}.json"

    def _lock(self, operation_id: str) -> FileLock:
        return FileLock(
            str(self._directory / f".{operation_id}.json.lock"),
            is_singleton=True,
        )

    def write(
        self,
        operation_id: str,
        *,
        provider: ProviderName,
        step: str,
        old_config_digest: str | None = None,
        new_config_digest: str | None = None,
        target_generation: int | None = None,
        credential_write_id: str | None = None,
        profile_digest: str | None = None,
    ) -> TransactionCheckpoint:
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or "/" in operation_id
            or "\x00" in operation_id
            or "\\" in operation_id
        ):
            raise ConfigTransactionError("config_transaction_operation_id_invalid")
        if step not in TRANSACTION_STATES:
            raise ConfigTransactionError("config_transaction_step_invalid")
        checkpoint = TransactionCheckpoint(
            operation_id=operation_id,
            provider=provider,
            step=step,
            old_config_digest=old_config_digest,
            new_config_digest=new_config_digest,
            target_generation=target_generation,
            credential_write_id=credential_write_id,
            profile_digest=profile_digest,
            updated_at=self._clock(),
        )
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock(operation_id):
            self._writer(self.path(operation_id), checkpoint.to_dict())
            fsync_directory(self._directory)
        return checkpoint

    def read(self, operation_id: str) -> TransactionCheckpoint | None:
        try:
            value = json.loads(self.path(operation_id).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return _parse_checkpoint(value)

    def advance(
        self,
        operation_id: str,
        *,
        step: str,
        **updates: Any,
    ) -> TransactionCheckpoint:
        with self._lock(operation_id):
            current = self.read(operation_id)
            if current is None:
                raise ConfigTransactionError("config_transaction_missing")
            current_index = TRANSACTION_STATES.index(current.step)
            next_index = TRANSACTION_STATES.index(step)
            if next_index < current_index:
                raise ConfigTransactionError("config_transaction_step_invalid")
            checkpoint = TransactionCheckpoint(
                operation_id=current.operation_id,
                provider=current.provider,
                step=step,
                old_config_digest=updates.get(
                    "old_config_digest", current.old_config_digest
                ),
                new_config_digest=updates.get(
                    "new_config_digest", current.new_config_digest
                ),
                target_generation=updates.get(
                    "target_generation", current.target_generation
                ),
                credential_write_id=updates.get(
                    "credential_write_id", current.credential_write_id
                ),
                profile_digest=updates.get("profile_digest", current.profile_digest),
                updated_at=self._clock(),
            )
            self._writer(self.path(operation_id), checkpoint.to_dict())
            fsync_directory(self._directory)
            return checkpoint


class ConfigTransactionCoordinator:
    """提交一次完整的 Provider 配置事务。

    journal 永远只记录非敏感摘要。新凭据先写受保护 store，再以 CAS 提交
    引用它的 profile；若提交被中断，下一次向导会通过 existing-store 通道
    复用已经安全保存的凭据，而不会要求再次粘贴。
    """

    def __init__(
        self,
        config_store: ConfigStore,
        credential_store: Any,
        receipt_store: Any,
        *,
        journal: ConfigTransactionJournal | None = None,
    ) -> None:
        self.config_store = config_store
        self.credential_store = credential_store
        self.receipt_store = receipt_store
        self.journal = journal or ConfigTransactionJournal(config_store.home)

    def configure(
        self,
        *,
        provider: ProviderName | str,
        profile: Mapping[str, Any],
        operation_id: str,
        secret: Any | None = None,
        allow_credential_overwrite: bool = False,
    ) -> RuntimeConfig:
        provider_name = ProviderName(provider)
        previous_secret: SecretBuffer | None = None
        if secret is not None:
            existing = self.credential_store.status(provider_name.value)
            existing_status = (
                existing.get("status") if isinstance(existing, Mapping) else existing
            )
            if existing_status == "available":
                if not allow_credential_overwrite:
                    raise ConfigTransactionError(
                        "credential_overwrite_confirmation_required"
                    )
                try:
                    previous_secret = SecretBuffer(
                        self.credential_store.read(provider_name.value)
                    )
                except Exception as error:
                    raise ConfigTransactionError(
                        "credential_transaction_inconsistent"
                    ) from error

        snapshot = self.config_store.read()
        candidate = copy.deepcopy(snapshot.document)
        profiles = dict(candidate.get("provider_profiles", {}))
        profiles[provider_name.value] = dict(profile)
        candidate["provider_profiles"] = profiles
        if candidate.get("selected_provider") is None:
            candidate["selected_provider"] = provider_name.value

        profile_digest = _digest(profile)
        target_generation = profile.get("credential_generation")
        credential_write_id = uuid.uuid4().hex if secret is not None else None
        credential_write_attempted = False
        config_committed = False
        try:
            self.journal.write(
                operation_id,
                provider=provider_name,
                step="prepared",
                old_config_digest=snapshot.canonical_digest,
                target_generation=target_generation,
                credential_write_id=credential_write_id,
                profile_digest=profile_digest,
            )

            self.receipt_store.invalidate(
                provider_name,
                "provider_configuration_changed",
                operation_id,
            )
            self.journal.advance(operation_id, step="receipt_invalidated")

            if secret is not None:
                credential_write_attempted = True
                self.credential_store.write(provider_name.value, secret)
            self.journal.advance(
                operation_id,
                step="credential_written",
                credential_write_id=credential_write_id,
            )

            committed = self.config_store.compare_and_swap(
                snapshot.canonical_digest,
                candidate,
            )
            config_committed = True
            self.journal.advance(
                operation_id,
                step="config_committed",
                new_config_digest=committed.canonical_digest,
            )
            self.journal.advance(operation_id, step="completed")
            return committed
        except BaseException:
            if (
                previous_secret is not None
                and credential_write_attempted
                and not config_committed
            ):
                try:
                    self.credential_store.write(
                        provider_name.value, previous_secret
                    )
                except BaseException as rollback_error:
                    raise ConfigTransactionError(
                        "credential_transaction_inconsistent"
                    ) from rollback_error
            raise
        finally:
            if previous_secret is not None:
                previous_secret.close()


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_checkpoint(value: Any) -> TransactionCheckpoint:
    if not isinstance(value, dict) or value.get("protocol") != TRANSACTION_PROTOCOL:
        raise ConfigTransactionError("config_transaction_invalid")
    return TransactionCheckpoint(
        operation_id=str(value["operation_id"]),
        provider=ProviderName(value["provider"]),
        step=str(value["step"]),
        old_config_digest=value.get("old_config_digest"),
        new_config_digest=value.get("new_config_digest"),
        target_generation=value.get("target_generation"),
        credential_write_id=value.get("credential_write_id"),
        profile_digest=value.get("profile_digest"),
    )


ConfigTransaction = ConfigTransactionJournal

__all__ = [
    "ConfigTransaction",
    "ConfigTransactionCoordinator",
    "ConfigTransactionError",
    "ConfigTransactionJournal",
    "TransactionCheckpoint",
    "TRANSACTION_STATES",
]
