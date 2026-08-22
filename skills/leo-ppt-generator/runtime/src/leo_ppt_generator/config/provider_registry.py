"""Fail-closed、只读的 Provider 能力与验证策略注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Iterable, Mapping

from .models import Capability, ProviderName


DEFAULT_CAPABILITY_TTL = timedelta(days=7)
DEFAULT_POLICY_VERSION = 1
DEFAULT_ARTIFACT_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
DEFAULT_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024


class ProviderRegistryError(LookupError):
    """只携带稳定原因码的 Registry 查询错误。"""

    reason_code = "provider_registry_unknown"


class DeclarationState(StrEnum):
    """静态声明的三态；缺失声明必须按 UNKNOWN 处理。"""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


CapabilitySupport = DeclarationState
PolicySupport = DeclarationState


@dataclass(frozen=True)
class AdapterIdentity:
    name: str
    version: str
    backend_kind: str


@dataclass(frozen=True)
class SafeOperationPolicy:
    support: DeclarationState = DeclarationState.UNKNOWN
    endpoint_path: str | None = None
    free_of_charge: bool = False
    side_effect_free: bool = False

    @property
    def automatic(self) -> bool:
        return (
            self.support is DeclarationState.SUPPORTED
            and self.free_of_charge
            and self.side_effect_free
        )


@dataclass(frozen=True)
class IdempotencyPolicy:
    support: DeclarationState = DeclarationState.UNKNOWN
    key_header: str | None = None
    replay_safe_after_acceptance: bool = False
    request_not_accepted_evidence: DeclarationState = DeclarationState.UNKNOWN


@dataclass(frozen=True)
class RetryPolicy:
    support: DeclarationState = DeclarationState.UNKNOWN
    retryable_failures: frozenset[str] = frozenset()
    max_attempts: int = 1
    backoff_seconds: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("retry_max_attempts_invalid")
        if any(delay < 0 for delay in self.backoff_seconds):
            raise ValueError("retry_backoff_invalid")
        if len(self.backoff_seconds) > self.max_attempts - 1:
            raise ValueError("retry_backoff_invalid")


@dataclass(frozen=True)
class ArtifactPolicy:
    support: DeclarationState = DeclarationState.UNKNOWN
    media_types: frozenset[str] = frozenset()
    max_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.max_bytes is not None and self.max_bytes <= 0:
            raise ValueError("artifact_max_bytes_invalid")


@dataclass(frozen=True)
class VerificationPolicy:
    version: int
    auth_probe: SafeOperationPolicy
    model_discovery: SafeOperationPolicy
    idempotency: IdempotencyPolicy
    retry: RetryPolicy
    artifacts: ArtifactPolicy
    capability_ttls: Mapping[Capability, timedelta]

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("verification_policy_version_invalid")
        normalized = {
            capability: ttl
            for capability, ttl in self.capability_ttls.items()
            if ttl > timedelta(0)
        }
        if len(normalized) != len(self.capability_ttls):
            raise ValueError("capability_ttl_invalid")
        object.__setattr__(self, "capability_ttls", MappingProxyType(normalized))

    def ttl(self, capability: Capability | str) -> timedelta:
        try:
            normalized = Capability(capability)
        except ValueError:
            return DEFAULT_CAPABILITY_TTL
        return self.capability_ttls.get(normalized, DEFAULT_CAPABILITY_TTL)


@dataclass(frozen=True)
class ProviderDefinition:
    name: str
    adapter: AdapterIdentity
    capabilities: Mapping[Capability, DeclarationState]
    credential_environments: frozenset[str]
    default_model: str
    max_reference_images: int
    verification_policy: VerificationPolicy
    internal: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.default_model or self.max_reference_images < 0:
            raise ValueError("provider_definition_invalid")
        normalized = {
            Capability(capability): DeclarationState(state)
            for capability, state in self.capabilities.items()
        }
        object.__setattr__(self, "capabilities", MappingProxyType(normalized))

    def capability(self, capability: Capability | str) -> DeclarationState:
        try:
            normalized = Capability(capability)
        except ValueError:
            return DeclarationState.UNKNOWN
        return self.capabilities.get(normalized, DeclarationState.UNKNOWN)

    @property
    def supported_capabilities(self) -> frozenset[Capability]:
        return frozenset(
            capability
            for capability in Capability
            if self.capability(capability) is DeclarationState.SUPPORTED
        )


AuthProbePolicy = SafeOperationPolicy
ModelDiscoveryPolicy = SafeOperationPolicy


def _capabilities(
    *,
    supported: Iterable[Capability],
    unsupported: Iterable[Capability] = (),
) -> Mapping[Capability, DeclarationState]:
    values = {capability: DeclarationState.UNKNOWN for capability in Capability}
    values.update({capability: DeclarationState.SUPPORTED for capability in supported})
    values.update({capability: DeclarationState.UNSUPPORTED for capability in unsupported})
    return values


def _ttls() -> Mapping[Capability, timedelta]:
    return {capability: DEFAULT_CAPABILITY_TTL for capability in Capability}


def _artifact_policy() -> ArtifactPolicy:
    return ArtifactPolicy(
        support=DeclarationState.SUPPORTED,
        media_types=DEFAULT_ARTIFACT_MEDIA_TYPES,
        max_bytes=DEFAULT_MAX_ARTIFACT_BYTES,
    )


def _external_policy(
    *,
    auth_probe: SafeOperationPolicy | None = None,
    model_discovery: SafeOperationPolicy | None = None,
    idempotency: IdempotencyPolicy | None = None,
    retry: RetryPolicy | None = None,
) -> VerificationPolicy:
    return VerificationPolicy(
        version=DEFAULT_POLICY_VERSION,
        auth_probe=auth_probe or SafeOperationPolicy(),
        model_discovery=model_discovery or SafeOperationPolicy(),
        idempotency=idempotency or IdempotencyPolicy(),
        retry=retry or RetryPolicy(),
        artifacts=_artifact_policy(),
        capability_ttls=_ttls(),
    )


def _unsupported_host_policy() -> VerificationPolicy:
    unsupported_operation = SafeOperationPolicy(support=DeclarationState.UNSUPPORTED)
    return VerificationPolicy(
        version=DEFAULT_POLICY_VERSION,
        auth_probe=unsupported_operation,
        model_discovery=unsupported_operation,
        idempotency=IdempotencyPolicy(support=DeclarationState.UNSUPPORTED),
        retry=RetryPolicy(support=DeclarationState.UNSUPPORTED),
        artifacts=_artifact_policy(),
        capability_ttls=_ttls(),
    )


def _definitions() -> tuple[ProviderDefinition, ...]:
    all_capabilities = tuple(Capability)
    image_transient_failures = frozenset(
        {"rate_limited", "server_error", "network_error", "timeout"}
    )
    bounded_retry = RetryPolicy(
        support=DeclarationState.SUPPORTED,
        retryable_failures=image_transient_failures,
        max_attempts=3,
        backoff_seconds=(0.5, 1.0),
    )
    return (
        ProviderDefinition(
            name="fixture",
            adapter=AdapterIdentity("fixture", "fixture/v1", "openai-compatible"),
            capabilities=_capabilities(
                supported=(Capability.GENERATE, Capability.EDIT, Capability.REFERENCE),
                unsupported=(Capability.MASK,),
            ),
            credential_environments=frozenset(),
            default_model="fixture-model",
            max_reference_images=4,
            verification_policy=_external_policy(
                auth_probe=SafeOperationPolicy(support=DeclarationState.UNSUPPORTED),
                model_discovery=SafeOperationPolicy(support=DeclarationState.UNSUPPORTED),
                idempotency=IdempotencyPolicy(
                    support=DeclarationState.SUPPORTED,
                    key_header="Idempotency-Key",
                    replay_safe_after_acceptance=True,
                    request_not_accepted_evidence=DeclarationState.SUPPORTED,
                ),
                retry=bounded_retry,
            ),
            internal=True,
        ),
        ProviderDefinition(
            name=ProviderName.BUILTIN_IMAGEGEN.value,
            adapter=AdapterIdentity(
                "builtin-imagegen", "builtin-imagegen/v1", "builtin-imagegen"
            ),
            capabilities=_capabilities(supported=all_capabilities),
            credential_environments=frozenset(),
            default_model="gpt-image-2",
            max_reference_images=16,
            verification_policy=_unsupported_host_policy(),
        ),

        ProviderDefinition(
            name=ProviderName.OPENAI.value,
            adapter=AdapterIdentity("openai", "openai/v1", "openai-compatible"),
            capabilities=_capabilities(supported=all_capabilities),
            credential_environments=frozenset({"OPENAI_API_KEY"}),
            default_model="gpt-image-2",
            max_reference_images=16,
            verification_policy=_external_policy(
                auth_probe=SafeOperationPolicy(
                    support=DeclarationState.SUPPORTED,
                    endpoint_path="/v1/models",
                    free_of_charge=True,
                    side_effect_free=True,
                ),
                model_discovery=SafeOperationPolicy(
                    support=DeclarationState.SUPPORTED,
                    endpoint_path="/v1/models",
                    free_of_charge=True,
                    side_effect_free=True,
                ),
                idempotency=IdempotencyPolicy(
                    support=DeclarationState.UNKNOWN,
                    request_not_accepted_evidence=DeclarationState.SUPPORTED,
                ),
                retry=bounded_retry,
            ),
        ),
        ProviderDefinition(
            name=ProviderName.OPENAI_COMPATIBLE.value,
            adapter=AdapterIdentity(
                "openai-compatible", "openai-compatible/v1", "openai-compatible"
            ),
            capabilities=_capabilities(supported=all_capabilities),
            credential_environments=frozenset({"OPENAI_COMPATIBLE_API_KEY"}),
            default_model="gpt-image-2",
            max_reference_images=16,
            # 任意用户 endpoint 不得提升这些声明；保持 generic fail-closed。
            verification_policy=_external_policy(),
        ),
        ProviderDefinition(
            name=ProviderName.ATLASCLOUD.value,
            adapter=AdapterIdentity("atlascloud", "atlascloud/v1", "atlascloud"),
            capabilities=_capabilities(
                supported=(Capability.GENERATE, Capability.EDIT, Capability.REFERENCE),
                unsupported=(Capability.MASK,),
            ),
            credential_environments=frozenset({"ATLASCLOUD_API_KEY"}),
            default_model="gpt-image-2",
            max_reference_images=4,
            verification_policy=_external_policy(
                idempotency=IdempotencyPolicy(
                    support=DeclarationState.UNKNOWN,
                    request_not_accepted_evidence=DeclarationState.SUPPORTED,
                ),
                retry=bounded_retry,
            ),
        ),
    )


class ProviderRegistry:
    """Checked-in static registry；调用方只能查询，不能由用户配置覆盖。"""

    def __init__(self, definitions: Iterable[ProviderDefinition]) -> None:
        ordered = tuple(definitions)
        by_name = {definition.name: definition for definition in ordered}
        if len(by_name) != len(ordered):
            raise ValueError("duplicate_provider_definition")
        self._ordered = ordered
        self._by_name = MappingProxyType(by_name)

    @classmethod
    def default(cls) -> ProviderRegistry:
        return cls(_definitions())

    def provider(
        self,
        name: ProviderName | str,
        endpoint_origin: str | None = None,
    ) -> ProviderDefinition:
        del endpoint_origin  # v1 无 checked-in endpoint matcher；用户 origin 不能提升策略。
        key = name.value if isinstance(name, ProviderName) else str(name)
        try:
            return self._by_name[key]
        except KeyError as exc:
            raise ProviderRegistryError("unknown_provider") from exc

    def policy(
        self,
        name: ProviderName | str,
        endpoint_origin: str | None = None,
    ) -> VerificationPolicy:
        return self.provider(name, endpoint_origin).verification_policy

    def definitions(self, *, include_internal: bool = False) -> tuple[ProviderDefinition, ...]:
        return tuple(
            definition
            for definition in self._ordered
            if include_internal or not definition.internal
        )

    def snapshot(self, *, include_internal: bool = False) -> Mapping[str, ProviderDefinition]:
        return MappingProxyType(
            {
                definition.name: definition
                for definition in self.definitions(include_internal=include_internal)
            }
        )