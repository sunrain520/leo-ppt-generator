"""配置应用层可依赖的无 I/O 实现细节 ports。"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol, TypeVar

from .models import (
    Capability,
    CapabilityEvidence,
    ProviderName,
    RouteName,
    VerificationFingerprint,
    VerificationReceipt,
    VerificationScope,
)


ConfigSnapshotT = TypeVar("ConfigSnapshotT", covariant=True)
ConfigDocumentT = TypeVar("ConfigDocumentT", contravariant=True)
CredentialMetadataT = TypeVar("CredentialMetadataT", covariant=True)
ProviderDefinitionT = TypeVar("ProviderDefinitionT", covariant=True)
VerificationPolicyT = TypeVar("VerificationPolicyT", covariant=True)
ReceiptInspectionT = TypeVar("ReceiptInspectionT", covariant=True)
VerificationIntentT = TypeVar("VerificationIntentT", contravariant=True)
ProviderRequestT = TypeVar("ProviderRequestT", contravariant=True)
VerificationResultT = TypeVar("VerificationResultT", covariant=True)


class SecretBuffer(Protocol):
    """最小 secret handle；实现必须提供显式清零生命周期。"""

    def close(self) -> None: ...


SecretBufferT = TypeVar("SecretBufferT", bound=SecretBuffer)


class RouteCapabilityResolver(Protocol):
    def resolve(
        self,
        route: RouteName,
        task_capabilities: frozenset[Capability],
    ) -> frozenset[Capability]: ...


class ProviderRegistry(Protocol[ProviderDefinitionT, VerificationPolicyT]):
    def provider(
        self,
        name: ProviderName,
        endpoint_origin: str | None,
    ) -> ProviderDefinitionT: ...

    def policy(
        self,
        name: ProviderName,
        endpoint_origin: str | None,
    ) -> VerificationPolicyT: ...


class ConfigStore(Protocol[ConfigSnapshotT, ConfigDocumentT]):
    def read(self) -> ConfigSnapshotT: ...

    def compare_and_swap(
        self,
        expected_digest: str | None,
        candidate: ConfigDocumentT,
    ) -> ConfigSnapshotT: ...


class CredentialStore(Protocol[CredentialMetadataT, SecretBufferT]):
    def inspect(self, provider: ProviderName) -> CredentialMetadataT: ...

    def write_envelope(
        self,
        provider: ProviderName,
        secret: SecretBufferT,
        generation: int,
        write_id: str,
    ) -> CredentialMetadataT: ...

    def resolve(
        self,
        credential_ref: str,
        expected_generation: int | None,
    ) -> SecretBufferT: ...

    def fingerprint_key(self, create: bool) -> SecretBufferT | None: ...


class ReceiptStore(Protocol[ReceiptInspectionT]):
    def inspect(
        self,
        provider: ProviderName,
        fingerprint: VerificationFingerprint,
        now: datetime,
    ) -> ReceiptInspectionT: ...

    def merge(
        self,
        fingerprint: VerificationFingerprint,
        evidence: Mapping[Capability, CapabilityEvidence],
    ) -> VerificationReceipt: ...

    def invalidate(
        self,
        provider: ProviderName,
        cause: str,
        operation_id: str,
    ) -> None: ...


class VerificationCoordinator(
    Protocol[VerificationIntentT, ProviderRequestT, VerificationResultT]
):
    def execute(
        self,
        scope: VerificationScope,
        intent: VerificationIntentT,
        request: ProviderRequestT,
    ) -> VerificationResultT: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
