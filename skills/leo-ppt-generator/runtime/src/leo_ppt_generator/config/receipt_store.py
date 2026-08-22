"""Provider 隔离的 Verification Receipt 持久化与新鲜度校验。"""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from filelock import FileLock

from ..storage import atomic_write_json, canonical_json, fsync_directory
from .models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ProviderName,
    VerificationFingerprint,
    VerificationReceipt,
    VerificationSource,
)
from .provider_registry import ProviderRegistry, VerificationPolicy

_RECEIPT_DIRECTORY = "verification-receipts"
_MAX_RECEIPT_BYTES = 1024 * 1024
_ROOT_FIELDS = frozenset(
    {
        "protocol",
        "schema_version",
        "provider",
        "endpoint_origin",
        "model",
        "credential_version",
        "runtime_identity",
        "adapter_version",
        "verification_policy_version",
        "verification_fingerprint",
        "capability_evidence",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "capability",
        "verified_at",
        "expires_at",
        "operation_id",
        "verification_source",
        "artifact_digest",
    }
)
_DIGEST_FIELDS = frozenset({"sha256", "media_type", "size_bytes"})


class ReceiptStoreError(ValueError):
    """不携带原始 receipt 内容的稳定错误。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class ReceiptInspection:
    """只暴露 readiness 所需的非敏感 receipt 派生事实。"""

    provider: ProviderName
    status: str
    reason_code: str
    fingerprint_matches: bool
    valid_evidence: Mapping[Capability, CapabilityEvidence]
    expired_capabilities: frozenset[Capability] = frozenset()
    fingerprint_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "valid_evidence", MappingProxyType(dict(self.valid_evidence))
        )

    @property
    def verified_capabilities(self) -> frozenset[Capability]:
        return frozenset(self.valid_evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "status": self.status,
            "reason_code": self.reason_code,
            "fingerprint_matches": self.fingerprint_matches,
            "verified_capabilities": sorted(
                capability.value for capability in self.valid_evidence
            ),
            "expired_capabilities": sorted(
                capability.value for capability in self.expired_capabilities
            ),
            "fingerprint_ref": self.fingerprint_ref,
            "evidence_refs": [
                f"receipt://{self.provider.value}/{capability.value}/"
                f"{evidence.artifact_digest.sha256[:12]}"
                for capability, evidence in sorted(
                    self.valid_evidence.items(), key=lambda item: item[0].value
                )
            ],
        }


def compute_verification_fingerprint(
    *,
    provider: ProviderName,
    endpoint_origin: str | None,
    model: str | None,
    credential_version: str,
    runtime_identity: str,
    adapter_version: str,
    verification_policy_version: int,
) -> VerificationFingerprint:
    """按基础身份的 UTF-8 canonical JSON 计算 SHA-256。"""

    payload = {
        "provider": provider.value,
        "endpoint_origin": endpoint_origin,
        "model": model,
        "credential_version": credential_version,
        "runtime_identity": runtime_identity,
        "adapter_version": adapter_version,
        "verification_policy_version": verification_policy_version,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return VerificationFingerprint(
        provider=provider,
        endpoint_origin=endpoint_origin,
        model=model,
        credential_version=credential_version,
        runtime_identity=runtime_identity,
        adapter_version=adapter_version,
        verification_policy_version=verification_policy_version,
        sha256=digest,
    )


def fingerprint_from_registry(
    registry: ProviderRegistry,
    *,
    provider: ProviderName,
    endpoint_origin: str | None,
    model: str | None,
    credential_version: str,
    runtime_identity: str,
) -> VerificationFingerprint:
    """从 Registry owner 获取 adapter/policy 版本，避免调用方复制策略。"""

    definition = registry.provider(provider, endpoint_origin)
    policy = registry.policy(provider, endpoint_origin)
    return compute_verification_fingerprint(
        provider=provider,
        endpoint_origin=endpoint_origin,
        model=model,
        credential_version=credential_version,
        runtime_identity=runtime_identity,
        adapter_version=definition.adapter.version,
        verification_policy_version=policy.version,
    )


def _require_exact_fields(
    value: Any, expected: frozenset[str], reason_code: str
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != expected:
        raise ReceiptStoreError(reason_code)
    return value


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ReceiptStoreError("verification_receipt_time_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptStoreError("verification_receipt_time_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ReceiptStoreError("verification_receipt_time_invalid")
    return parsed.astimezone(UTC)


def _parse_evidence(
    key: str, value: Any, policy: VerificationPolicy
) -> CapabilityEvidence:
    item = _require_exact_fields(
        value, _EVIDENCE_FIELDS, "verification_receipt_schema_invalid"
    )
    if item.get("capability") != key:
        raise ReceiptStoreError("verification_receipt_capability_mismatch")
    digest_value = _require_exact_fields(
        item.get("artifact_digest"),
        _DIGEST_FIELDS,
        "verification_receipt_artifact_digest_invalid",
    )
    try:
        capability = Capability(key)
        evidence = CapabilityEvidence(
            capability=capability,
            verified_at=_parse_utc(item.get("verified_at")),
            expires_at=_parse_utc(item.get("expires_at")),
            operation_id=item.get("operation_id"),
            verification_source=VerificationSource(item.get("verification_source")),
            artifact_digest=ArtifactDigest(
                sha256=digest_value.get("sha256"),
                media_type=digest_value.get("media_type"),
                size_bytes=digest_value.get("size_bytes"),
            ),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ReceiptStoreError):
            raise
        raise ReceiptStoreError("verification_receipt_schema_invalid") from exc
    _validate_evidence(evidence, policy)
    return evidence


def _validate_evidence(
    evidence: CapabilityEvidence, policy: VerificationPolicy
) -> None:
    if evidence.expires_at > evidence.verified_at + policy.ttl(evidence.capability):
        raise ReceiptStoreError("verification_receipt_ttl_exceeded")
    artifact_policy = policy.artifacts
    digest = evidence.artifact_digest
    if (
        digest.media_type not in artifact_policy.media_types
        or artifact_policy.max_bytes is None
        or digest.size_bytes > artifact_policy.max_bytes
    ):
        raise ReceiptStoreError("verification_receipt_artifact_digest_invalid")


def _parse_receipt(
    value: Any,
    *,
    expected_provider: ProviderName,
    registry: ProviderRegistry,
) -> VerificationReceipt:
    root = _require_exact_fields(
        value, _ROOT_FIELDS, "verification_receipt_schema_invalid"
    )
    if (
        root.get("protocol") != VerificationReceipt.protocol
        or root.get("schema_version") != VerificationReceipt.schema_version
        or root.get("provider") != expected_provider.value
    ):
        raise ReceiptStoreError("verification_receipt_schema_invalid")
    try:
        fingerprint = compute_verification_fingerprint(
            provider=ProviderName(root.get("provider")),
            endpoint_origin=root.get("endpoint_origin"),
            model=root.get("model"),
            credential_version=root.get("credential_version"),
            runtime_identity=root.get("runtime_identity"),
            adapter_version=root.get("adapter_version"),
            verification_policy_version=root.get("verification_policy_version"),
        )
    except (TypeError, ValueError) as exc:
        raise ReceiptStoreError("verification_receipt_schema_invalid") from exc
    if fingerprint.sha256 != root.get("verification_fingerprint"):
        raise ReceiptStoreError("verification_receipt_fingerprint_invalid")
    raw_evidence = root.get("capability_evidence")
    if not isinstance(raw_evidence, dict) or not raw_evidence:
        raise ReceiptStoreError("verification_receipt_schema_invalid")
    policy = registry.policy(expected_provider, fingerprint.endpoint_origin)
    try:
        evidence = {
            Capability(key): _parse_evidence(key, item, policy)
            for key, item in raw_evidence.items()
        }
    except ValueError as exc:
        if isinstance(exc, ReceiptStoreError):
            raise
        raise ReceiptStoreError("verification_receipt_schema_invalid") from exc
    try:
        return VerificationReceipt(
            fingerprint=fingerprint, capability_evidence=evidence
        )
    except ValueError as exc:
        raise ReceiptStoreError("verification_receipt_schema_invalid") from exc


class FileReceiptStore:
    """以每个 Provider 一个文件、一个锁维护原子 receipt merge。"""

    def __init__(
        self,
        home: str | Path,
        registry: ProviderRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
        writer: Callable[[str | Path, Any], None] = atomic_write_json,
    ) -> None:
        self._directory = Path(home).resolve() / _RECEIPT_DIRECTORY
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))
        self._writer = writer

    def receipt_path(self, provider: ProviderName) -> Path:
        if provider is ProviderName.BUILTIN_IMAGEGEN:
            raise ReceiptStoreError("verification_receipt_host_provider_forbidden")
        return self._directory / f"{provider.value}.json"

    def _lock(self, provider: ProviderName) -> FileLock:
        return FileLock(str(self._directory / f".{provider.value}.json.lock"))

    @staticmethod
    def _now(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ReceiptStoreError("verification_receipt_time_invalid")
        return value.astimezone(UTC)

    def _read(self, provider: ProviderName) -> VerificationReceipt | None:
        path = self.receipt_path(provider)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise ReceiptStoreError("verification_receipt_file_invalid")
        if metadata.st_size > _MAX_RECEIPT_BYTES:
            raise ReceiptStoreError("verification_receipt_file_invalid")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReceiptStoreError("verification_receipt_schema_invalid") from exc
        return _parse_receipt(
            value, expected_provider=provider, registry=self._registry
        )

    def inspect(
        self,
        provider: ProviderName,
        fingerprint: VerificationFingerprint,
        now: datetime,
    ) -> ReceiptInspection:
        current = self._now(now)
        try:
            receipt = self._read(provider)
        except (ReceiptStoreError, ValueError, TypeError):
            return ReceiptInspection(
                provider=provider,
                status="invalid",
                reason_code="verification_receipt_invalid",
                fingerprint_matches=False,
                valid_evidence={},
            )
        if receipt is None:
            return ReceiptInspection(
                provider=provider,
                status="missing",
                reason_code="verification_receipt_missing",
                fingerprint_matches=False,
                valid_evidence={},
            )
        if receipt.fingerprint.sha256 != fingerprint.sha256:
            return ReceiptInspection(
                provider=provider,
                status="stale",
                reason_code="verification_fingerprint_stale",
                fingerprint_matches=False,
                valid_evidence={},
                fingerprint_ref=receipt.fingerprint.sha256[:12],
            )
        valid = {
            capability: evidence
            for capability, evidence in receipt.capability_evidence.items()
            if evidence.expires_at > current
        }
        expired = frozenset(receipt.capability_evidence).difference(valid)
        return ReceiptInspection(
            provider=provider,
            status="valid" if valid else "stale",
            reason_code=(
                "verification_receipt_valid"
                if valid
                else "verification_evidence_expired"
            ),
            fingerprint_matches=True,
            valid_evidence=valid,
            expired_capabilities=frozenset(expired),
            fingerprint_ref=receipt.fingerprint.sha256[:12],
        )


    def merge(
        self,
        fingerprint: VerificationFingerprint,
        evidence: Mapping[Capability, CapabilityEvidence],
    ) -> VerificationReceipt:
        if not evidence:
            raise ReceiptStoreError("verification_evidence_empty")
        provider = fingerprint.provider
        current = self._now(self._clock())
        policy = self._registry.policy(provider, fingerprint.endpoint_origin)
        candidate_evidence = dict(evidence)
        for capability, item in candidate_evidence.items():
            if capability is not item.capability:
                raise ReceiptStoreError("verification_receipt_capability_mismatch")
            _validate_evidence(item, policy)
        path = self.receipt_path(provider)
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock(provider):
            existing: VerificationReceipt | None
            try:
                existing = self._read(provider)
            except ReceiptStoreError:
                existing = None
            merged: dict[Capability, CapabilityEvidence] = {}
            if (
                existing is not None
                and existing.fingerprint.sha256 == fingerprint.sha256
            ):
                merged.update(
                    {
                        capability: item
                        for capability, item in existing.capability_evidence.items()
                        if item.expires_at > current
                    }
                )
            merged.update(candidate_evidence)
            receipt = VerificationReceipt(
                fingerprint=fingerprint, capability_evidence=merged
            )
            self._writer(path, receipt.to_dict())
            return receipt

    def invalidate(
        self,
        provider: ProviderName,
        cause: str,
        operation_id: str,
    ) -> None:
        if not isinstance(cause, str) or not cause.strip():
            raise ReceiptStoreError("verification_invalidation_cause_invalid")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ReceiptStoreError("verification_operation_id_invalid")
        path = self.receipt_path(provider)
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock(provider):
            path.unlink(missing_ok=True)
            fsync_directory(self._directory)


ReceiptStore = FileReceiptStore

__all__ = [
    "FileReceiptStore",
    "ReceiptInspection",
    "ReceiptStore",
    "ReceiptStoreError",
    "compute_verification_fingerprint",
    "fingerprint_from_registry",
]
