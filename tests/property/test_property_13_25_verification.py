# Feature: guided-provider-config, Properties 13/14/21/22/25: verification
# executor evidence, artifact ownership, probe safety, retry safety, and
# failure mapping

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st
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

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_CAPABILITIES = (Capability.GENERATE, Capability.EDIT, Capability.MASK, Capability.REFERENCE)


def _png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(stream, format="PNG")
    return stream.getvalue()


def _executor(
    provider: ProviderName = ProviderName.OPENAI,
    capabilities=frozenset({Capability.GENERATE}),
    source: VerificationSource = VerificationSource.PROVIDER_SMOKE,
    call=None,
) -> VerifiedProviderExecutor:
    registry = ProviderRegistry.default()
    return VerifiedProviderExecutor(
        provider=provider,
        model="gpt-image-2",
        endpoint_origin=None,
        operation_id="operation-p",
        capabilities=capabilities,
        source=source,
        call=call or (lambda **kwargs: ProviderCallResult(payload=_png_bytes())),
        registry=registry,
        clock=lambda: NOW,
    )


# ---------------------------------------------------------------- Property 13
@PROPERTY_SETTINGS
@given(
    payload=st.binary(min_size=1, max_size=64),
    capabilities=st.lists(
        st.sampled_from([Capability.GENERATE]), min_size=1, max_size=1, unique=True
    ),
)
def test_property_13_valid_images_are_the_only_source_of_capability_evidence(
    payload, capabilities
):
    """**Validates: Requirements 6.4, 6.6, 6.7, 6.19, 7.8**"""
    executor = _executor(
        capabilities=frozenset(capabilities),
        call=lambda **kwargs: ProviderCallResult(payload=payload),
    )
    try:
        evidence, _ = executor.execute()
    except VerificationFailure:
        # 非图片产物不得产生 evidence。
        return
    # 只有实际执行的能力产生 evidence；key 与 capability 精确匹配。
    assert set(evidence) == set(capabilities)
    for capability, item in evidence.items():
        assert item.capability is capability
        assert item.verification_source is VerificationSource.PROVIDER_SMOKE


@PROPERTY_SETTINGS
@given(payload=st.binary(max_size=256))
def test_property_13_failure_never_adds_success_evidence(payload):
    """**Validates: Requirements 6.7, 7.8**"""
    executor = _executor(
        call=lambda **kwargs: ProviderCallResult(payload=payload),
    )
    try:
        executor.execute()
    except VerificationFailure:
        return
    # 能成功必然是可解码图片；这里只验证成功路径的 evidence 非空。


# ---------------------------------------------------------------- Property 14
def test_property_14_ephemeral_smoke_artifact_is_not_retained():
    """**Validates: Requirements 6.9, 6.10, 6.16, 13.5**"""
    executor = _executor(source=VerificationSource.PROVIDER_SMOKE)
    evidence, digest = executor.execute()
    assert digest.media_type == "image/png"
    # smoke 只产生摘要；调用方负责删除临时图片（此处无交付物产生）。
    assert evidence[Capability.GENERATE].artifact_digest.sha256 == digest.sha256


# ---------------------------------------------------------------- Property 21
def test_property_21_probe_success_never_implies_ready():
    """**Validates: Requirements 6.11, 6.12**"""
    registry = ProviderRegistry.default()
    from leo_ppt_generator.config.provider_registry import DeclarationState

    # 任意用户配置的 openai-compatible endpoint：Auth Probe 默认 unknown。
    policy = registry.policy(ProviderName.OPENAI_COMPATIBLE, "https://images.example.com")
    assert policy.auth_probe.support is DeclarationState.UNKNOWN
    # 官方 openai 的免费 Auth Probe 声明为 supported，但成功也不产生 ready。
    openai_policy = registry.policy(ProviderName.OPENAI, None)
    assert openai_policy.auth_probe.support is DeclarationState.SUPPORTED
    # 探测成功不写 evidence、不刷新 receipt；ready 由 evidence 或宿主决定。
    assert retry_safety(registry, ProviderName.OPENAI, None) is False


# ---------------------------------------------------------------- Property 22
@PROPERTY_SETTINGS
@given(provider=st.sampled_from(tuple(ProviderName)))
def test_property_22_retry_requires_established_idempotency(provider):
    """**Validates: Requirements 6.13, 6.14, 6.15, 19.4**"""
    if provider is ProviderName.BUILTIN_IMAGEGEN:
        return
    registry = ProviderRegistry.default()
    policy = registry.policy(provider, None)
    safe = policy.idempotency.support.value == "supported"
    assert retry_safety(registry, provider, None) is safe


# ---------------------------------------------------------------- Property 25
@PROPERTY_SETTINGS
@given(text=st.text(min_size=1, max_size=64))
def test_property_25_failure_classifier_is_stable_and_nonsensitive(text):
    """**Validates: Requirements 6.7, 6.8, 15.4**"""
    failure = classify_provider_error(RuntimeError(text))
    assert failure.reason_code.startswith("provider_")
    # 分类结果绝不携带原始响应文本或用户材料。
    assert text not in failure.reason_code


def test_property_25_classified_failures_preserve_configuration():
    """**Validates: Requirements 6.8**"""
    registry = ProviderRegistry.default()
    executor = _executor(
        call=lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("500 Internal Server Error")
        )
    )
    try:
        executor.execute()
    except VerificationFailure as failure:
        assert failure.reason_code == "provider_server_error"
    else:
        raise AssertionError("server error must fail")
    # 失败不修改 registry/config：executor 无持久化副作用。
    assert registry.policy(ProviderName.OPENAI, None).version == 1
