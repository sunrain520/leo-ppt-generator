"""smoke 与首张业务图片共用的真实验证包装器。

VerifiedProviderExecutor 是 Provider_Smoke 与真实业务图片惰性验证的
唯一验证包装器：产物校验、错误分类、evidence 生成与重试安全性都在这里，
业务执行器与 Config verify 复用同一实现。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from PIL import Image

from ..config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ProviderName,
    VerificationSource,
)
from ..config.provider_registry import (
    DeclarationState,
    ProviderRegistry,
)
from ..config.reason_codes import ReasonCode


class VerificationFailure(Exception):
    """稳定的验证失败；只携带 Reason_Code，不含原始响应。"""

    reason_code: str = "verification_failed"

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ArtifactPolicyLimits:
    media_types: frozenset[str]
    max_bytes: int

    def accepts(self, media_type: str | None, size_bytes: int) -> bool:
        if media_type is not None and media_type not in self.media_types:
            return False
        return size_bytes <= self.max_bytes


@dataclass(frozen=True)
class ProviderCallResult:
    """一次 Provider 调用的最小产物结果（已脱敏）。"""

    payload: bytes
    media_type: str | None = None
    accepted: bool = True


class ProviderCall(Protocol):
    """可注入的真实 Provider 调用；fake 测试实现同一协议。"""

    def __call__(
        self,
        *,
        provider: ProviderName,
        model: str,
        endpoint_origin: str | None,
        operation_id: str,
        idempotency_key: str | None,
        capabilities: frozenset[Capability],
        timeout_seconds: int,
        retries: int,
    ) -> ProviderCallResult: ...


@dataclass
class VerifiedProviderExecutor:
    """执行一次真实验证；每个意图一个实例。"""

    provider: ProviderName
    model: str
    endpoint_origin: str | None
    operation_id: str
    capabilities: frozenset[Capability]
    source: VerificationSource
    call: ProviderCall
    registry: ProviderRegistry
    clock: Callable[[], datetime] = field(
        default_factory=lambda: lambda: datetime.now(UTC)
    )
    limits: ArtifactPolicyLimits | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not self.capabilities:
            raise VerificationFailure("verification_evidence_empty")
        policy = self.registry.policy(self.provider, self.endpoint_origin)
        definition = self.registry.provider(self.provider, self.endpoint_origin)
        # 每次调用只为 Registry 声明支持的 capability 生成 evidence。
        supported = definition.supported_capabilities
        if not self.capabilities.issubset(supported):
            unsupported = sorted(
                capability.value
                for capability in self.capabilities - supported
            )
            raise VerificationFailure(
                f"provider_capability_unsupported:{','.join(unsupported)}"
            )
        if self.limits is None:
            self.limits = ArtifactPolicyLimits(
                media_types=policy.artifacts.media_types,
                max_bytes=policy.artifacts.max_bytes,
            )

    def execute(self, payload: bytes | None = None) -> tuple[Mapping[Capability, CapabilityEvidence], ArtifactDigest]:
        """发起调用、校验产物并生成 evidence。

        返回 (evidence, digest)；调用方决定如何持久化与保留产物。
        payload 非 None 时使用本地产物（业务图片已生成），跳过 Provider 调用。
        """

        if payload is not None:
            digest = self._validate_payload(payload)
        else:
            policy = self.registry.policy(self.provider, self.endpoint_origin)
            try:
                result = self.call(
                    provider=self.provider,
                    model=self.model,
                    endpoint_origin=self.endpoint_origin,
                    operation_id=self.operation_id,
                    idempotency_key=self.idempotency_key,
                    capabilities=self.capabilities,
                    timeout_seconds=policy.retry.max_attempts * 10,
                    retries=policy.retry.max_attempts,
                )
            except VerificationFailure:
                raise
            except Exception as error:
                raise classify_provider_error(error) from error
            digest = self._validate_payload(result.payload)
        now = self.clock()
        policy = self.registry.policy(self.provider, self.endpoint_origin)
        evidence: dict[Capability, CapabilityEvidence] = {}
        for capability in sorted(self.capabilities, key=lambda item: item.value):
            evidence[capability] = CapabilityEvidence(
                capability=capability,
                verified_at=now,
                expires_at=now + policy.ttl(capability),
                operation_id=self.operation_id,
                verification_source=self.source,
                artifact_digest=digest,
            )
        return evidence, digest

    def _validate_payload(self, payload: bytes) -> ArtifactDigest:
        if not isinstance(payload, bytes) or not payload:
            raise VerificationFailure("provider_artifact_empty")
        if self.limits is not None and len(payload) > self.limits.max_bytes:
            raise VerificationFailure("provider_artifact_unreadable")
        try:
            image = Image.open(BytesIO(payload))
            image.load()
        except Exception as exc:
            raise VerificationFailure("provider_artifact_unreadable") from exc
        format_name = (image.format or "").lower()
        media_type = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "jpg": "image/jpeg",
            "webp": "image/webp",
        }.get(format_name)
        if media_type is None or (
            self.limits is not None
            and not self.limits.accepts(media_type, len(payload))
        ):
            raise VerificationFailure("provider_artifact_media_type_unsupported")
        digest = hashlib.sha256(payload).hexdigest()
        return ArtifactDigest(
            sha256=digest,
            media_type=media_type,
            size_bytes=len(payload),
        )


def classify_provider_error(error: BaseException) -> VerificationFailure:
    """把底层 Provider/网络异常归一为稳定 VerificationFailure。"""

    if isinstance(error, VerificationFailure):
        return error
    text = str(error)
    lowered = text.lower()
    if any(marker in lowered for marker in ("401", "authentication", "unauthorized", "invalid api key")):
        return VerificationFailure(ReasonCode.PROVIDER_AUTHENTICATION_FAILED.value)
    if any(marker in lowered for marker in ("403", "permission", "forbidden")):
        return VerificationFailure(ReasonCode.PROVIDER_PERMISSION_DENIED.value)
    if any(marker in lowered for marker in ("404", "not found", "model not found")):
        return VerificationFailure(ReasonCode.PROVIDER_MODEL_NOT_FOUND.value)
    if any(marker in lowered for marker in ("429", "rate limit", "quota")):
        return VerificationFailure(ReasonCode.PROVIDER_RATE_LIMITED.value)
    if any(marker in lowered for marker in ("5", "server error", "internal")):
        return VerificationFailure(ReasonCode.PROVIDER_SERVER_ERROR.value)
    if any(marker in lowered for marker in ("timeout", "timed out")):
        return VerificationFailure(ReasonCode.PROVIDER_TIMEOUT.value)
    if any(marker in lowered for marker in ("dns", "connection", "network", "tls", "ssl")):
        return VerificationFailure(ReasonCode.PROVIDER_NETWORK_ERROR.value)
    return VerificationFailure(ReasonCode.PROVIDER_OUTCOME_UNKNOWN.value)


def retry_safety(
    registry: ProviderRegistry,
    provider: ProviderName,
    endpoint_origin: str | None,
) -> bool:
    """按 Registry 幂等声明决定结果不确定后是否可自动重试。"""

    policy = registry.policy(provider, endpoint_origin)
    return policy.idempotency.support is DeclarationState.SUPPORTED


@dataclass(frozen=True)
class PaidVerificationConsent:
    """对当前一次独立 Provider_Smoke 的肯定授权。

    只代表一次操作；不得持久化或由安装器/宿主构造。默认“否”由
    调用方（wizard/CLI）保证，本类型只承载已获授权的状态。
    """

    operation_id: str
    provider: ProviderName
    granted: bool = True

    def __post_init__(self) -> None:
        if not self.operation_id or not self.operation_id.strip():
            raise VerificationFailure("verification_operation_id_invalid")
        if not isinstance(self.granted, bool):
            raise VerificationFailure("verification_consent_invalid")


class ProviderSmokeExecutor:
    """显式 generate-only Provider_Smoke；绝不刷新 edit/mask/reference。

    - 只接受一次性 PaidVerificationConsent，未授权直接失败；
    - 忽略现有 generate evidence 但保留其他能力证据（merge 语义由调用方）；
    - 仅 Registry 明确声明免费且无副作用时运行 Auth Probe / model discovery；
    - 临时 smoke 图片校验后删除，只保留非敏感摘要。
    """

    def __init__(
        self,
        *,
        consent: PaidVerificationConsent,
        executor: VerifiedProviderExecutor,
        registry: ProviderRegistry,
    ) -> None:
        if not consent.granted:
            raise VerificationFailure("verification_consent_denied")
        if consent.provider is not executor.provider:
            raise VerificationFailure("verification_operation_id_invalid")
        if executor.source is not VerificationSource.PROVIDER_SMOKE:
            raise VerificationFailure("verification_source_invalid")
        if executor.capabilities != frozenset({Capability.GENERATE}):
            raise VerificationFailure("verification_capability_scope_invalid")
        self.consent = consent
        self.executor = executor
        self.registry = registry

    def run(self) -> tuple[Mapping[Capability, CapabilityEvidence], ArtifactDigest]:
        """执行 generate-only smoke；调用方负责 merge evidence 与删除图片。"""

        return self.executor.execute()

    def safe_probe_available(self) -> bool:
        """仅 Registry 明确声明无费用且无实质副作用时允许自动 Auth Probe。"""

        policy = self.registry.policy(
            self.consent.provider, self.executor.endpoint_origin
        )
        return policy.auth_probe.automatic and policy.model_discovery.automatic

    def probe_endpoints(self) -> tuple[str | None, str | None]:
        """返回 Auth Probe / model discovery 的 endpoint 路径（仅安全时）。"""

        policy = self.registry.policy(
            self.consent.provider, self.executor.endpoint_origin
        )
        return (
            policy.auth_probe.endpoint_path if policy.auth_probe.automatic else None,
            (
                policy.model_discovery.endpoint_path
                if policy.model_discovery.automatic
                else None
            ),
        )


__all__ = [
    "ArtifactPolicyLimits",
    "PaidVerificationConsent",
    "ProviderCall",
    "ProviderCallResult",
    "ProviderSmokeExecutor",
    "VerificationFailure",
    "VerifiedProviderExecutor",
    "classify_provider_error",
    "retry_safety",
]
