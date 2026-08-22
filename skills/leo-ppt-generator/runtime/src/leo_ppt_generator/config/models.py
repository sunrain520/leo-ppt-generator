"""Provider 配置领域模型与机器协议值对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping


class ProviderName(StrEnum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
    ATLASCLOUD = "atlascloud"
    BUILTIN_IMAGEGEN = "builtin-imagegen"


class RouteName(StrEnum):
    GENERATE = "generate"
    DIRECT_EDITABLE = "direct-editable"
    UPGRADE_FULL = "upgrade-full"
    UPGRADE_SELECTED = "upgrade-selected"


class Capability(StrEnum):
    GENERATE = "generate"
    EDIT = "edit"
    MASK = "mask"
    REFERENCE = "reference"


class ConfigurationState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    LOCALLY_CONFIGURED = "locally_configured"
    INVALID = "invalid"


class VerificationState(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    STALE = "stale"


class ConfigStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    READY = "ready"
    DEGRADED = "degraded"
    INVALID = "invalid"


class ExecutionEligibility(StrEnum):
    ALLOWED = "allowed"
    RETRYABLE = "retryable"
    BLOCKED = "blocked"


class InstallationReadiness(StrEnum):
    READY = "ready"
    USABLE_UNVERIFIED = "usable_unverified"
    INSTALLED_NOT_READY = "installed_not_ready"


class HostCapabilityState(StrEnum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class PrimaryActionKind(StrEnum):
    RUN_CLI = "run_cli"
    START_TASK = "start_task"
    RESUME_TASK = "resume_task"
    WAIT_AND_RETRY = "wait_and_retry"
    CONFIRM_NEW_REQUEST = "confirm_new_request"


class CredentialReferenceType(StrEnum):
    ENVIRONMENT = "environment-reference"
    OS_STORE = "os-store-reference"
    NOT_REQUIRED = "not-required"
    NONE = "none"


class VerificationSource(StrEnum):
    PROVIDER_SMOKE = "provider_smoke"
    BUSINESS_REQUEST = "business_request"


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _validated_refs(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _require_text(value, field_name)
    return values


@dataclass(frozen=True, slots=True)
class ReadinessScope:
    route: RouteName
    required_capabilities: frozenset[Capability]
    verified_capabilities: frozenset[Capability]
    missing_capabilities: frozenset[Capability]
    fingerprint_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.required_capabilities:
            raise ValueError("required_capabilities must not be empty")
        if self.verified_capabilities & self.missing_capabilities:
            raise ValueError("verified_capabilities and missing_capabilities must be disjoint")
        if self.verified_capabilities | self.missing_capabilities != self.required_capabilities:
            raise ValueError("verified and missing capabilities must partition required capabilities")
        if self.fingerprint_sha256 is not None:
            _require_sha256(self.fingerprint_sha256, "fingerprint_sha256")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "route": self.route.value,
            "required_capabilities": sorted(item.value for item in self.required_capabilities),
            "verified_capabilities": sorted(item.value for item in self.verified_capabilities),
            "missing_capabilities": sorted(item.value for item in self.missing_capabilities),
        }
        if self.fingerprint_sha256 is not None:
            result["fingerprint_sha256"] = self.fingerprint_sha256
        return result


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    sha256: str
    media_type: str
    size_bytes: int

    def __post_init__(self) -> None:
        _require_sha256(self.sha256, "artifact_digest.sha256")
        _require_text(self.media_type, "artifact_digest.media_type")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes <= 0
        ):
            raise ValueError("artifact_digest.size_bytes must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    capability: Capability
    verified_at: datetime
    expires_at: datetime
    operation_id: str
    verification_source: VerificationSource
    artifact_digest: ArtifactDigest

    def __post_init__(self) -> None:
        _require_utc(self.verified_at, "verified_at")
        _require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.verified_at:
            raise ValueError("expires_at must be later than verified_at")
        _require_text(self.operation_id, "operation_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "verified_at": _timestamp(self.verified_at),
            "expires_at": _timestamp(self.expires_at),
            "operation_id": self.operation_id,
            "verification_source": self.verification_source.value,
            "artifact_digest": self.artifact_digest.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class VerificationFingerprint:
    provider: ProviderName
    endpoint_origin: str | None
    model: str | None
    credential_version: str
    runtime_identity: str
    adapter_version: str
    verification_policy_version: int
    sha256: str

    def __post_init__(self) -> None:
        if self.provider is ProviderName.BUILTIN_IMAGEGEN:
            raise ValueError("host providers cannot have verification receipts")
        if self.endpoint_origin is not None:
            _require_text(self.endpoint_origin, "endpoint_origin")
        if self.model is not None:
            _require_text(self.model, "model")
        _require_text(self.credential_version, "credential_version")
        _require_text(self.runtime_identity, "runtime_identity")
        _require_text(self.adapter_version, "adapter_version")
        if (
            isinstance(self.verification_policy_version, bool)
            or not isinstance(self.verification_policy_version, int)
            or self.verification_policy_version < 1
        ):
            raise ValueError("verification_policy_version must be positive")
        _require_sha256(self.sha256, "verification_fingerprint")


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    fingerprint: VerificationFingerprint
    capability_evidence: Mapping[Capability, CapabilityEvidence]
    protocol: ClassVar[str] = "leo-ppt-verification-receipt/v1"
    schema_version: ClassVar[int] = 1

    def __post_init__(self) -> None:
        if not self.capability_evidence:
            raise ValueError("capability_evidence must not be empty")
        evidence = dict(self.capability_evidence)
        for capability, item in evidence.items():
            if capability is not item.capability:
                raise ValueError("capability evidence key must match its capability")
        object.__setattr__(self, "capability_evidence", MappingProxyType(evidence))

    def to_dict(self) -> dict[str, Any]:
        fingerprint = self.fingerprint
        return {
            "protocol": self.protocol,
            "schema_version": self.schema_version,
            "provider": fingerprint.provider.value,
            "endpoint_origin": fingerprint.endpoint_origin,
            "model": fingerprint.model,
            "credential_version": fingerprint.credential_version,
            "runtime_identity": fingerprint.runtime_identity,
            "adapter_version": fingerprint.adapter_version,
            "verification_policy_version": fingerprint.verification_policy_version,
            "verification_fingerprint": fingerprint.sha256,
            "capability_evidence": {
                capability.value: item.to_dict()
                for capability, item in sorted(self.capability_evidence.items(), key=lambda pair: pair[0].value)
            },
        }


@dataclass(frozen=True, slots=True)
class PrimaryAction:
    kind: PrimaryActionKind
    command: str | None = None
    resume_ref: str | None = None

    def __post_init__(self) -> None:
        if self.kind is PrimaryActionKind.RUN_CLI:
            if self.command is None:
                raise ValueError("run_cli action requires command")
            _require_text(self.command, "primary_action.command")
        elif self.command is not None:
            raise ValueError("only run_cli action may contain command")
        if self.resume_ref is not None:
            _require_text(self.resume_ref, "primary_action.resume_ref")

    def to_dict(self) -> dict[str, str]:
        result = {"kind": self.kind.value}
        if self.command is not None:
            result["command"] = self.command
        if self.resume_ref is not None:
            result["resume_ref"] = self.resume_ref
        return result


@dataclass(frozen=True, slots=True)
class ProviderReport:
    provider: ProviderName
    configuration_state: ConfigurationState
    verification_state: VerificationState
    candidate_capabilities: frozenset[Capability]
    scope_compatible: bool
    credential_reference_type: CredentialReferenceType
    reason_code: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_text(self.reason_code, "provider.reason_code")
        _validated_refs(self.evidence_refs, "provider.evidence_refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "configuration_state": self.configuration_state.value,
            "verification": {"status": self.verification_state.value},
            "candidate_capabilities": sorted(item.value for item in self.candidate_capabilities),
            "scope_compatible": self.scope_compatible,
            "credential_reference_type": self.credential_reference_type.value,
            "reason_code": self.reason_code,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class ConfigReport:
    stage: str
    status: ConfigStatus
    configuration_state: ConfigurationState
    verification_state: VerificationState
    execution_eligibility: ExecutionEligibility
    installation_readiness: InstallationReadiness
    readiness_scope: ReadinessScope
    reason_code: str
    selected_provider: ProviderName | None
    providers: tuple[ProviderReport, ...]
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    primary_action: PrimaryAction | None = None
    protocol: ClassVar[str] = "leo-ppt-config/v1"
    schema_version: ClassVar[int] = 1

    def __post_init__(self) -> None:
        _require_text(self.stage, "stage")
        _require_text(self.reason_code, "reason_code")
        _validated_refs(self.evidence_refs, "evidence_refs")
        provider_names = tuple(item.provider for item in self.providers)
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("providers must not contain duplicates")
        if self.selected_provider is not None and self.selected_provider not in provider_names:
            raise ValueError("selected_provider must appear in providers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "schema_version": self.schema_version,
            "stage": self.stage,
            "status": self.status.value,
            "configuration_state": self.configuration_state.value,
            "verification": {"status": self.verification_state.value},
            "execution_eligibility": self.execution_eligibility.value,
            "installation_readiness": self.installation_readiness.value,
            "readiness_scope": self.readiness_scope.to_dict(),
            "reason_code": self.reason_code,
            "selected_provider": self.selected_provider.value if self.selected_provider else None,
            "providers": [item.to_dict() for item in self.providers],
            "evidence_refs": list(self.evidence_refs),
            "primary_action": self.primary_action.to_dict() if self.primary_action else None,
        }


@dataclass(frozen=True, slots=True)
class VerificationScope:
    """一次真实验证意图的基础身份与规范化能力集合。"""

    fingerprint: VerificationFingerprint
    required_capabilities: frozenset[Capability]

    def __post_init__(self) -> None:
        if not self.required_capabilities:
            raise ValueError("required_capabilities must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_sha256": self.fingerprint.sha256,
            "required_capabilities": sorted(item.value for item in self.required_capabilities),
        }
