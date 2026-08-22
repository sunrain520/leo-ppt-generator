"""VerifiedProviderExecutor 与错误分类的示例型单元测试。"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.verification import (
    ProviderCallResult,
    VerificationFailure,
    VerifiedProviderExecutor,
    classify_provider_error,
    retry_safety,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(stream, format="PNG")
    return stream.getvalue()


def _executor(
    call=None,
    *,
    provider: ProviderName = ProviderName.OPENAI,
    capabilities=frozenset({Capability.GENERATE}),
    source: VerificationSource = VerificationSource.PROVIDER_SMOKE,
) -> VerifiedProviderExecutor:
    registry = ProviderRegistry.default()
    return VerifiedProviderExecutor(
        provider=provider,
        model="gpt-image-2",
        endpoint_origin=None,
        operation_id="operation-1",
        capabilities=capabilities,
        source=source,
        call=call or (lambda **kwargs: ProviderCallResult(payload=_png_bytes())),
        registry=registry,
        clock=lambda: NOW,
    )


def test_execute_generates_evidence_for_generate_only():
    executor = _executor()
    evidence, digest = executor.execute()
    assert set(evidence) == {Capability.GENERATE}
    item = evidence[Capability.GENERATE]
    assert item.operation_id == "operation-1"
    assert item.verification_source is VerificationSource.PROVIDER_SMOKE
    assert item.expires_at == item.verified_at + timedelta(days=7)
    assert digest.sha256 and digest.media_type == "image/png"


def test_execute_with_local_payload_skips_provider_call():
    calls = []

    def counting_call(**kwargs):
        calls.append(kwargs)
        return ProviderCallResult(payload=b"")

    executor = _executor(counting_call)
    evidence, _ = executor.execute(payload=_png_bytes())
    assert calls == []
    assert set(evidence) == {Capability.GENERATE}


def test_empty_payload_is_artifact_error():
    executor = _executor(call=lambda **kwargs: ProviderCallResult(payload=b""))
    with pytest.raises(VerificationFailure) as captured:
        executor.execute()
    assert captured.value.reason_code == "provider_artifact_empty"


def test_corrupt_payload_is_unreadable():
    executor = _executor(
        call=lambda **kwargs: ProviderCallResult(payload=b"not-an-image")
    )
    with pytest.raises(VerificationFailure) as captured:
        executor.execute()
    assert captured.value.reason_code == "provider_artifact_unreadable"


def test_unsupported_capability_is_rejected_at_construction():
    from leo_ppt_generator.config.verification import VerifiedProviderExecutor

    registry = ProviderRegistry.default()
    # atlascloud 声明支持 generate/reference 但 mask 是 unknown/unsupported。
    with pytest.raises(VerificationFailure) as captured:
        VerifiedProviderExecutor(
            provider=ProviderName.ATLASCLOUD,
            model="gpt-image-2",
            endpoint_origin=None,
            operation_id="op-2",
            capabilities=frozenset({Capability.MASK}),
            source=VerificationSource.BUSINESS_REQUEST,
            call=lambda **kwargs: ProviderCallResult(payload=_png_bytes()),
            registry=registry,
            clock=lambda: NOW,
        )
    assert "provider_capability_unsupported" in str(captured.value)


def test_classify_provider_error_maps_stable_codes():
    cases = {
        "401 Unauthorized": "provider_authentication_failed",
        "403 Forbidden": "provider_permission_denied",
        "404 model not found": "provider_model_not_found",
        "429 Too Many Requests": "provider_rate_limited",
        "500 Internal Server Error": "provider_server_error",
        "request timed out": "provider_timeout",
        "connection refused": "provider_network_error",
        "mystery failure": "provider_outcome_unknown",
    }
    for text, expected in cases.items():
        assert classify_provider_error(RuntimeError(text)).reason_code == expected


def test_retry_safety_follows_registry_idempotency():
    registry = ProviderRegistry.default()
    # 默认 generic openai-compatible endpoint 幂等 unknown -> 不自动重试。
    assert retry_safety(registry, ProviderName.OPENAI, None) is False


def test_paid_consent_denied_blocks_smoke():
    from leo_ppt_generator.config.verification import (
        PaidVerificationConsent,
        ProviderSmokeExecutor,
    )

    consent = PaidVerificationConsent(
        operation_id="op-1", provider=ProviderName.OPENAI, granted=False
    )
    registry = ProviderRegistry.default()
    executor = _executor()
    with pytest.raises(VerificationFailure) as captured:
        ProviderSmokeExecutor(
            consent=consent, executor=executor, registry=registry
        )
    assert captured.value.reason_code == "verification_consent_denied"


def test_smoke_requires_generate_only_scope():
    from leo_ppt_generator.config.verification import (
        PaidVerificationConsent,
        ProviderSmokeExecutor,
    )

    consent = PaidVerificationConsent(
        operation_id="op-1", provider=ProviderName.OPENAI
    )
    # edit capability 的 executor 不能用于 v1 smoke。
    registry = ProviderRegistry.default()
    executor = VerifiedProviderExecutor(
        provider=ProviderName.OPENAI,
        model="gpt-image-2",
        endpoint_origin=None,
        operation_id="op-1",
        capabilities=frozenset({Capability.EDIT}),
        source=VerificationSource.PROVIDER_SMOKE,
        call=lambda **kwargs: ProviderCallResult(payload=_png_bytes()),
        registry=registry,
        clock=lambda: NOW,
    )
    with pytest.raises(VerificationFailure):
        ProviderSmokeExecutor(
            consent=consent, executor=executor, registry=registry
        )


def test_smoke_generates_only_generate_evidence():
    from leo_ppt_generator.config.verification import (
        PaidVerificationConsent,
        ProviderSmokeExecutor,
    )

    registry = ProviderRegistry.default()
    executor = _executor()
    consent = PaidVerificationConsent(
        operation_id="operation-1", provider=ProviderName.OPENAI
    )
    smoke = ProviderSmokeExecutor(
        consent=consent, executor=executor, registry=registry
    )
    evidence, digest = smoke.run()
    # v1 smoke 只产生 generate evidence。
    assert set(evidence) == {Capability.GENERATE}
    assert digest.media_type == "image/png"


def test_smoke_probe_availability_follows_registry():
    from leo_ppt_generator.config.verification import (
        PaidVerificationConsent,
        ProviderSmokeExecutor,
    )

    registry = ProviderRegistry.default()
    executor = _executor(provider=ProviderName.OPENAI_COMPATIBLE)
    executor = VerifiedProviderExecutor(
        provider=ProviderName.OPENAI_COMPATIBLE,
        model="gpt-image-2",
        endpoint_origin="https://images.example.com",
        operation_id="op-1",
        capabilities=frozenset({Capability.GENERATE}),
        source=VerificationSource.PROVIDER_SMOKE,
        call=lambda **kwargs: ProviderCallResult(payload=_png_bytes()),
        registry=registry,
        clock=lambda: NOW,
    )
    consent = PaidVerificationConsent(
        operation_id="op-1", provider=ProviderName.OPENAI_COMPATIBLE
    )
    smoke = ProviderSmokeExecutor(
        consent=consent, executor=executor, registry=registry
    )
    # 任意用户配置的 openai-compatible endpoint：probe 默认不安全。
    assert smoke.safe_probe_available() is False
    assert smoke.probe_endpoints() == (None, None)
