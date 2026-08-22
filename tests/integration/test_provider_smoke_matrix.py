"""Provider、generate-only smoke 与故障矩阵集成测试（5.9）。

使用 fake ProviderCall 覆盖全部稳定失败类别；断言 smoke 只产生
generate evidence，且 edit/mask/reference 永不出现。
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.verification import (
    PaidVerificationConsent,
    ProviderCallResult,
    ProviderSmokeExecutor,
    VerificationFailure,
    VerifiedProviderExecutor,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)
_REGISTRY = ProviderRegistry.default()


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), color=(0, 0, 255)).save(stream, format="PNG")
    return stream.getvalue()


def _smoke(call, *, provider: ProviderName = ProviderName.OPENAI) -> ProviderSmokeExecutor:
    executor = VerifiedProviderExecutor(
        provider=provider,
        model="gpt-image-2",
        endpoint_origin=None,
        operation_id="operation-smoke",
        capabilities=frozenset({Capability.GENERATE}),
        source=VerificationSource.PROVIDER_SMOKE,
        call=call,
        registry=_REGISTRY,
        clock=lambda: NOW,
    )
    consent = PaidVerificationConsent(
        operation_id="operation-smoke", provider=provider
    )
    return ProviderSmokeExecutor(
        consent=consent, executor=executor, registry=_REGISTRY
    )


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (b"", "provider_artifact_empty"),
        (b"not-an-image", "provider_artifact_unreadable"),
    ],
)
def test_smoke_failure_matrix_invalid_artifacts(payload, expected_code):
    smoke = _smoke(lambda **kwargs: ProviderCallResult(payload=payload))
    with pytest.raises(VerificationFailure) as captured:
        smoke.run()
    assert captured.value.reason_code == expected_code


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        ("401 Unauthorized", "provider_authentication_failed"),
        ("403 Forbidden", "provider_permission_denied"),
        ("404 model not found", "provider_model_not_found"),
        ("429 rate limit exceeded", "provider_rate_limited"),
        ("500 Internal Server Error", "provider_server_error"),
        ("connection timed out", "provider_timeout"),
        ("connection refused", "provider_network_error"),
        ("mystery", "provider_outcome_unknown"),
    ],
)
def test_smoke_failure_matrix_provider_errors(text, expected_code):
    def failing_call(**kwargs):
        raise RuntimeError(text)

    smoke = _smoke(failing_call)
    with pytest.raises(VerificationFailure) as captured:
        smoke.run()
    assert captured.value.reason_code == expected_code


def test_smoke_success_generates_only_generate_evidence():
    smoke = _smoke(lambda **kwargs: ProviderCallResult(payload=_png()))
    evidence, digest = smoke.run()
    assert set(evidence) == {Capability.GENERATE}
    for capability in (Capability.EDIT, Capability.MASK, Capability.REFERENCE):
        assert capability not in evidence
    assert digest.media_type == "image/png"


def test_smoke_uses_stable_operation_id_and_idempotency_key():
    captured = {}

    def recording_call(**kwargs):
        captured.update(kwargs)
        return ProviderCallResult(payload=_png())

    smoke = _smoke(recording_call)
    smoke.run()
    assert captured["operation_id"] == "operation-smoke"
    assert captured["capabilities"] == frozenset({Capability.GENERATE})
    # Registry 默认不声明幂等键：不自动注入幂等键（unknown 不假设）。
    assert captured["idempotency_key"] is None


def test_smoke_atlascloud_uses_same_verification_path():
    smoke = _smoke(
        lambda **kwargs: ProviderCallResult(payload=_png()),
        provider=ProviderName.ATLASCLOUD,
    )
    evidence, _ = smoke.run()
    assert set(evidence) == {Capability.GENERATE}
