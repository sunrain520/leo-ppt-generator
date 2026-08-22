# Feature: guided-provider-config, Properties 15-18: receipt merge, fingerprint
# identity, capability expiry, and explicit re-verification

from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import (
    FileReceiptStore,
    ReceiptInspection,
    ReceiptStoreError,
    compute_verification_fingerprint,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_CAPABILITIES = tuple(Capability)
_REGISTRY = ProviderRegistry.default()
_RUNTIME_IDENTITY = "leo-ppt-generator/test"


def _fingerprint(*, credential_version: str = "generation:1", adapter: str = "openai/v1") -> object:
    return compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=None,
        model="gpt-image-2",
        credential_version=credential_version,
        runtime_identity=_RUNTIME_IDENTITY,
        adapter_version=adapter,
        verification_policy_version=1,
    )


def _digest(seed: str) -> ArtifactDigest:
    return ArtifactDigest(
        sha256=hashlib.sha256(seed.encode()).hexdigest(),
        media_type="image/png",
        size_bytes=len(seed),
    )


def _evidence(
    capability: Capability,
    *,
    offset_hours: int = 0,
    seed: str | None = None,
    source: VerificationSource = VerificationSource.PROVIDER_SMOKE,
) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        verified_at=NOW + timedelta(hours=offset_hours),
        expires_at=NOW + timedelta(days=7, hours=offset_hours),
        operation_id=f"operation-{capability.value}-{seed or offset_hours}",
        verification_source=source,
        artifact_digest=_digest(seed or f"{capability.value}-{offset_hours}"),
    )


def _store(home: Path, *, now: datetime = NOW) -> FileReceiptStore:
    return FileReceiptStore(home, _REGISTRY, clock=lambda: now)


# ---------------------------------------------------------------- Property 15
@PROPERTY_SETTINGS
@given(
    initial=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=0, max_size=3, unique=True
    ),
    added=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=1, max_size=3, unique=True
    ),
)
def test_property_15_receipt_merge_is_atomic_and_capability_preserving(initial, added):
    """**Validates: Requirements 6.5, 6.6, 7.9, 13.5**"""
    with tempfile.TemporaryDirectory() as directory:
        store = _store(Path(directory))
        fingerprint = _fingerprint()
        if initial:
            store.merge(
                fingerprint,
                {cap: _evidence(cap, seed=f"initial-{cap.value}") for cap in initial},
            )
        result = store.merge(
            fingerprint,
            {cap: _evidence(cap, seed=f"added-{cap.value}") for cap in added},
        )
        merged = frozenset(result.capability_evidence)
        assert merged == frozenset(initial) | frozenset(added)
        for cap in added:
            assert result.capability_evidence[cap].operation_id.startswith(
                f"operation-{cap.value}-added-"
            )
        # 持久化后读取一致。
        inspection = store.inspect(fingerprint.provider, fingerprint, NOW)
        assert inspection.valid_evidence.keys() == merged

        # 不同 fingerprint 不合并旧证据。
        other = _fingerprint(credential_version="generation:2")
        replaced = store.merge(
            other, {Capability.GENERATE: _evidence(Capability.GENERATE)}
        )
        assert frozenset(replaced.capability_evidence) == {Capability.GENERATE}


@PROPERTY_SETTINGS
@given(
    initial=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=1, max_size=3, unique=True
    ),
    added=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=1, max_size=3, unique=True
    ),
)
def test_property_15_merge_failure_preserves_old_bytes(initial, added):
    """**Validates: Requirements 6.5, 13.5**"""
    with tempfile.TemporaryDirectory() as directory:
        store = _store(Path(directory))
        fingerprint = _fingerprint()
        store.merge(
            fingerprint,
            {cap: _evidence(cap, seed=f"i-{cap.value}") for cap in initial},
        )
        path = store.receipt_path(fingerprint.provider)
        before = path.read_bytes()

        def failing_writer(_target, _value) -> None:
            raise OSError("injected write failure")

        broken = FileReceiptStore(
            Path(directory), _REGISTRY, clock=lambda: NOW, writer=failing_writer
        )
        try:
            broken.merge(
                fingerprint,
                {cap: _evidence(cap, seed=f"a-{cap.value}") for cap in added},
            )
        except (ReceiptStoreError, OSError):
            pass
        else:
            raise AssertionError("failing writer must not silently succeed")
        # 旧 receipt 字节保持完整；当前 Route 不得因写入失败而 ready。
        assert path.read_bytes() == before
        inspection = store.inspect(fingerprint.provider, fingerprint, NOW)
        assert inspection.valid_evidence.keys() == frozenset(initial)


# ---------------------------------------------------------------- Property 16
@PROPERTY_SETTINGS
@given(
    credential_version=st.text(min_size=1, max_size=16),
    adapter=st.text(min_size=1, max_size=16),
    endpoint=st.one_of(st.none(), st.text(min_size=1, max_size=32)),
    model=st.one_of(st.none(), st.text(min_size=1, max_size=16)),
)
def test_property_16_fingerprint_changes_exactly_with_base_identity(
    credential_version, adapter, endpoint, model
):
    """**Validates: Requirements 4.6, 7.3, 7.5, 19.7**"""
    base = compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=endpoint,
        model=model,
        credential_version=credential_version,
        runtime_identity=_RUNTIME_IDENTITY,
        adapter_version=adapter,
        verification_policy_version=1,
    )
    variants = {
        "provider": compute_verification_fingerprint(
            provider=ProviderName.ATLASCLOUD,
            endpoint_origin=endpoint,
            model=model,
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter,
            verification_policy_version=1,
        ),
        "endpoint": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=(endpoint or "") + "x",
            model=model,
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter,
            verification_policy_version=1,
        ),
        "model": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=endpoint,
            model=(model or "") + "x",
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter,
            verification_policy_version=1,
        ),
        "credential": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=endpoint,
            model=model,
            credential_version=credential_version + "x",
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter,
            verification_policy_version=1,
        ),
        "adapter": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=endpoint,
            model=model,
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter + "x",
            verification_policy_version=1,
        ),
        "policy": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=endpoint,
            model=model,
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY,
            adapter_version=adapter,
            verification_policy_version=2,
        ),
        "runtime": compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=endpoint,
            model=model,
            credential_version=credential_version,
            runtime_identity=_RUNTIME_IDENTITY + "x",
            adapter_version=adapter,
            verification_policy_version=1,
        ),
    }
    for name, variant in variants.items():
        if name == "endpoint" and endpoint is None:
            continue
        assert variant.sha256 != base.sha256, name
    # 基础身份不变时 fingerprint 稳定。
    again = compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=endpoint,
        model=model,
        credential_version=credential_version,
        runtime_identity=_RUNTIME_IDENTITY,
        adapter_version=adapter,
        verification_policy_version=1,
    )
    assert again.sha256 == base.sha256


# ---------------------------------------------------------------- Property 17
@PROPERTY_SETTINGS
@given(
    capabilities=st.lists(
        st.sampled_from(_CAPABILITIES), min_size=2, max_size=3, unique=True
    ),
)
def test_property_17_capability_expiry_is_independent_and_policy_bounded(
    capabilities,
):
    """**Validates: Requirements 7.4, 7.10**"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        fingerprint = _fingerprint()
        first, *rest = capabilities

        # 第一项证据在 7 天前验证：恰好今天过期；其余证据今天验证、7 天后过期。
        policy = _REGISTRY.policy(ProviderName.OPENAI, None)
        ttl = policy.ttl(first)
        evidence = {
            first: CapabilityEvidence(
                capability=first,
                verified_at=NOW - ttl,
                expires_at=NOW,
                operation_id=f"op-{first.value}",
                verification_source=VerificationSource.BUSINESS_REQUEST,
                artifact_digest=_digest(first.value),
            )
        }
        for cap in rest:
            evidence[cap] = CapabilityEvidence(
                capability=cap,
                verified_at=NOW,
                expires_at=NOW + policy.ttl(cap),
                operation_id=f"op-{cap.value}",
                verification_source=VerificationSource.BUSINESS_REQUEST,
                artifact_digest=_digest(cap.value),
            )
        # TTL 由 Registry 策略约束：生成的 expires_at 不得晚于 policy TTL。
        for cap, item in evidence.items():
            assert item.expires_at - item.verified_at <= policy.ttl(cap)

        store = _store(home, now=NOW)
        store.merge(fingerprint, evidence)
        inspection = store.inspect(fingerprint.provider, fingerprint, NOW)
        # 已过期的一项失效，其余项保持有效；互不影响。
        assert first not in inspection.valid_evidence
        assert frozenset(inspection.valid_evidence) == frozenset(rest)
        assert inspection.expired_capabilities == frozenset({first})


# ---------------------------------------------------------------- Property 18
@PROPERTY_SETTINGS
@given(
    extra=st.lists(
        st.sampled_from([Capability.EDIT, Capability.MASK, Capability.REFERENCE]),
        min_size=1,
        max_size=3,
        unique=True,
    )
)
def test_property_18_explicit_reverification_refreshes_generate_only(extra):
    """**Validates: Requirements 7.6**"""
    with tempfile.TemporaryDirectory() as directory:
        store = _store(Path(directory))
        fingerprint = _fingerprint()
        existing = {Capability.GENERATE: _evidence(Capability.GENERATE, seed="old")}
        existing.update({cap: _evidence(cap, seed=f"e-{cap.value}") for cap in extra})
        store.merge(fingerprint, existing)
        before = store.inspect(fingerprint.provider, fingerprint, NOW)

        # 显式 verify 只刷新 generate 证据。
        refreshed = _evidence(Capability.GENERATE, seed="new", source=VerificationSource.PROVIDER_SMOKE)
        store.merge(fingerprint, {Capability.GENERATE: refreshed})
        after = store.inspect(fingerprint.provider, fingerprint, NOW)

        assert (
            after.valid_evidence[Capability.GENERATE].operation_id
            == refreshed.operation_id
        )
        for cap in extra:
            assert (
                after.valid_evidence[cap].operation_id
                == before.valid_evidence[cap].operation_id
            )
