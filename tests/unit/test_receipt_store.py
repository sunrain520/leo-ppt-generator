from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

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
    ReceiptStoreError,
    compute_verification_fingerprint,
    fingerprint_from_registry,
)
from leo_ppt_generator.storage import canonical_json


NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _fingerprint(
    provider: ProviderName = ProviderName.OPENAI,
    *,
    credential_version: str = "generation:secret-version-123456789",
):
    registry = ProviderRegistry.default()
    return fingerprint_from_registry(
        registry,
        provider=provider,
        endpoint_origin=(
            "https://relay.example.com"
            if provider is ProviderName.OPENAI_COMPATIBLE
            else None
        ),
        model="gpt-image-2",
        credential_version=credential_version,
        runtime_identity="leo-ppt-generator/0.1.0",
    )


def _evidence(
    capability: Capability,
    *,
    verified_at: datetime = NOW,
    lifetime: timedelta = timedelta(days=7),
    media_type: str = "image/png",
    operation_id: str = "operation-1",
) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        verified_at=verified_at,
        expires_at=verified_at + lifetime,
        operation_id=operation_id,
        verification_source=VerificationSource.BUSINESS_REQUEST,
        artifact_digest=ArtifactDigest(
            sha256=hashlib.sha256(operation_id.encode()).hexdigest(),
            media_type=media_type,
            size_bytes=128,
        ),
    )


def test_fingerprint_uses_only_canonical_base_identity():
    fingerprint = compute_verification_fingerprint(
        provider=ProviderName.OPENAI_COMPATIBLE,
        endpoint_origin="https://relay.example.com",
        model="gpt-image-2",
        credential_version="generation:2",
        runtime_identity="leo-ppt-generator/0.1.0",
        adapter_version="openai-compatible/v1",
        verification_policy_version=1,
    )
    payload = {
        "provider": "openai-compatible",
        "endpoint_origin": "https://relay.example.com",
        "model": "gpt-image-2",
        "credential_version": "generation:2",
        "runtime_identity": "leo-ppt-generator/0.1.0",
        "adapter_version": "openai-compatible/v1",
        "verification_policy_version": 1,
    }
    assert fingerprint.sha256 == hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()


def test_merge_preserves_only_current_unexpired_capabilities(tmp_path):
    registry = ProviderRegistry.default()
    fingerprint = _fingerprint()
    store = FileReceiptStore(tmp_path, registry, clock=lambda: NOW)
    still_valid = _evidence(
        Capability.EDIT,
        verified_at=NOW - timedelta(days=1),
        operation_id="edit-old",
    )
    expires_before_merge = _evidence(
        Capability.MASK,
        verified_at=NOW - timedelta(days=7),
        operation_id="mask-old",
    )
    store.merge(
        fingerprint,
        {Capability.EDIT: still_valid, Capability.MASK: expires_before_merge},
    )

    refreshed = _evidence(Capability.GENERATE, operation_id="generate-new")
    receipt = store.merge(fingerprint, {Capability.GENERATE: refreshed})

    assert receipt.capability_evidence == {
        Capability.EDIT: still_valid,
        Capability.GENERATE: refreshed,
    }
    inspection = store.inspect(ProviderName.OPENAI, fingerprint, NOW)
    assert inspection.verified_capabilities == {
        Capability.EDIT,
        Capability.GENERATE,
    }


def test_different_fingerprint_and_provider_never_inherit_evidence(tmp_path):
    registry = ProviderRegistry.default()
    store = FileReceiptStore(tmp_path, registry, clock=lambda: NOW)
    original = _fingerprint()
    store.merge(original, {Capability.EDIT: _evidence(Capability.EDIT)})

    rotated = _fingerprint(credential_version="generation:rotated")
    receipt = store.merge(
        rotated, {Capability.GENERATE: _evidence(Capability.GENERATE)}
    )
    atlas = _fingerprint(ProviderName.ATLASCLOUD)
    store.merge(atlas, {Capability.GENERATE: _evidence(Capability.GENERATE)})

    assert set(receipt.capability_evidence) == {Capability.GENERATE}
    assert store.receipt_path(ProviderName.OPENAI) != store.receipt_path(
        ProviderName.ATLASCLOUD
    )
    assert store.inspect(ProviderName.ATLASCLOUD, atlas, NOW).status == "valid"


def test_registry_ttl_and_artifact_policy_are_enforced(tmp_path):
    store = FileReceiptStore(
        tmp_path, ProviderRegistry.default(), clock=lambda: NOW
    )
    fingerprint = _fingerprint()

    with pytest.raises(ReceiptStoreError, match="ttl_exceeded"):
        store.merge(
            fingerprint,
            {
                Capability.GENERATE: _evidence(
                    Capability.GENERATE, lifetime=timedelta(days=7, seconds=1)
                )
            },
        )
    with pytest.raises(ReceiptStoreError, match="artifact_digest_invalid"):
        store.merge(
            fingerprint,
            {
                Capability.GENERATE: _evidence(
                    Capability.GENERATE, media_type="text/plain"
                )
            },
        )


def test_inspection_rejects_non_utc_or_unknown_schema_without_leaking_version(
    tmp_path,
):
    registry = ProviderRegistry.default()
    fingerprint = _fingerprint()
    store = FileReceiptStore(tmp_path, registry, clock=lambda: NOW)
    store.merge(
        fingerprint, {Capability.GENERATE: _evidence(Capability.GENERATE)}
    )
    path = store.receipt_path(ProviderName.OPENAI)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["capability_evidence"]["generate"]["verified_at"] = "2026-01-08T00:00:00"
    payload["unexpected"] = "not-allowed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    inspection = store.inspect(ProviderName.OPENAI, fingerprint, NOW)
    rendered = json.dumps(inspection.to_dict())
    assert inspection.status == "invalid"
    assert fingerprint.credential_version not in rendered
    assert "credential_version" not in rendered


def test_atomic_write_failure_preserves_previous_receipt_bytes(tmp_path):
    registry = ProviderRegistry.default()
    fingerprint = _fingerprint()
    store = FileReceiptStore(tmp_path, registry, clock=lambda: NOW)
    store.merge(
        fingerprint, {Capability.GENERATE: _evidence(Capability.GENERATE)}
    )
    path = store.receipt_path(ProviderName.OPENAI)
    previous = path.read_bytes()

    def fail_before_replace(_path, _value):
        raise OSError("injected write failure")

    failing_store = FileReceiptStore(
        tmp_path, registry, clock=lambda: NOW, writer=fail_before_replace
    )
    with pytest.raises(OSError, match="injected write failure"):
        failing_store.merge(
            fingerprint, {Capability.EDIT: _evidence(Capability.EDIT)}
        )

    assert path.read_bytes() == previous


def test_invalidate_is_provider_local_and_has_no_sensitive_result(tmp_path):
    registry = ProviderRegistry.default()
    store = FileReceiptStore(tmp_path, registry, clock=lambda: NOW)
    openai = _fingerprint()
    atlas = _fingerprint(ProviderName.ATLASCLOUD)
    store.merge(openai, {Capability.GENERATE: _evidence(Capability.GENERATE)})
    store.merge(atlas, {Capability.GENERATE: _evidence(Capability.GENERATE)})

    result = store.invalidate(
        ProviderName.OPENAI,
        cause="credential_rotated",
        operation_id="invalidate-1",
    )

    assert result is None
    assert store.inspect(ProviderName.OPENAI, openai, NOW).status == "missing"
    assert store.inspect(ProviderName.ATLASCLOUD, atlas, NOW).status == "valid"
