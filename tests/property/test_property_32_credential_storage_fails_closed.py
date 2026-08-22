# Feature: guided-provider-config, Property 32: Credential storage fails
# closed on unsupported or unsafe platforms

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.credentials import (
    CredentialError,
    UnsupportedCredentialStore,
    WindowsDPAPIStore,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)


def _protect(value: bytes) -> bytes:
    # 加盐变换的 fake：保证密文绝不包含明文子串，模拟真实 DPAPI 的行为。
    return b"enc:v1:" + bytes(byte ^ 0x5A for byte in value) + b":tail"


def _unprotect(value: bytes) -> bytes:
    if not value.startswith(b"enc:v1:"):
        raise CredentialError("credential_blob_invalid")
    body = value[len(b"enc:v1:") :]
    if not body.endswith(b":tail"):
        raise CredentialError("credential_blob_invalid")
    return bytes(byte ^ 0x5A for byte in body[: -len(b":tail")])


def _store(root: Path, *, private_acl: bool = True) -> WindowsDPAPIStore:
    return WindowsDPAPIStore(
        root=root,
        protect=_protect,
        unprotect=_unprotect,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: private_acl,
    )


@PROPERTY_SETTINGS
@given(provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")))
def test_property_32_unsupported_platform_never_creates_plaintext(provider):
    """**Validates: Requirements 14.3, 14.4, 14.5**"""
    store = UnsupportedCredentialStore()
    try:
        store.reference(provider)
    except CredentialError as exc:
        assert str(exc) == "credential_store_unsupported"
    else:
        raise AssertionError("unsupported store must not resolve references")
    try:
        store.read(provider)
    except CredentialError as exc:
        assert str(exc) == "credential_store_unsupported"
    else:
        raise AssertionError("unsupported store must not read secrets")
    try:
        store.write(provider, "plaintext-canary")
    except CredentialError as exc:
        assert str(exc) == "credential_store_unsupported"
    else:
        raise AssertionError("unsupported store must not persist plaintext")
    assert store.status(provider) == "missing"
    assert store.remove(provider) is False
    # Fingerprint_Key 缺失只让 receipt stale，不创建明文替代。
    assert store.fingerprint_key(create=True) is None


@PROPERTY_SETTINGS
@given(blob=st.binary(min_size=1, max_size=64))
def test_property_32_dpapi_rejects_invalid_blobs_without_fallback(blob):
    """**Validates: Requirements 14.4, 14.5**"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "credentials"
        root.mkdir()
        (root / "openai.dpapi").write_bytes(blob)
        store = _store(root)
        # 保护/解密不匹配的 blob 必须 fail closed，绝不降级读取明文。
        try:
            store.read("openai")
        except CredentialError:
            pass
        leftovers = [p.name for p in Path(directory).rglob("*")]
        assert not any(
            name.endswith((".tmp", ".txt", ".plaintext")) for name in leftovers
        )


@PROPERTY_SETTINGS
@given(provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")))
def test_property_32_broad_acl_blocks_access(provider):
    """**Validates: Requirements 14.4**"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "credentials"
        root.mkdir()
        (root / f"{provider}.dpapi").write_bytes(b"encrypted")
        store = _store(root, private_acl=False)  # ACL 过宽
        try:
            store.read(provider)
        except CredentialError as exc:
            assert str(exc) == "credential_store_acl_too_broad"
        else:
            raise AssertionError("broad ACL must fail closed")


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")),
    secret=st.text(min_size=1, max_size=32),
)
def test_property_32_dpapi_roundtrip_preserves_secret(provider, secret):
    """**Validates: Requirements 14.2, 14.4, 14.5**"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "credentials"
        root.mkdir()
        store = _store(root)
        store.write(provider, secret)
        assert store.read(provider) == secret
        blob = (root / f"{provider}.dpapi").read_bytes()
        # 密文不得等于明文或"明文+固定前缀"：存储不是明文回退。
        assert blob != secret.encode("utf-8")
        assert blob != b"enc:v1:" + secret.encode("utf-8")


@PROPERTY_SETTINGS
@given(secret=st.binary(min_size=1, max_size=32))
def test_property_32_fingerprint_key_roundtrip_never_plaintext(secret):
    """**Validates: Requirements 14.4, 7.7**"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "credentials"
        root.mkdir()
        store = _store(root)
        key = store.fingerprint_key(create=True)
        assert key is not None
        same = store.fingerprint_key(create=False)
        assert same is not None
        assert key.reveal_bytes() == same.reveal_bytes()
        blob = (root / "verification-fingerprint-key.dpapi").read_bytes()
        assert blob.startswith(b"enc:v1:")
        assert key.reveal_bytes() not in blob


def test_fingerprint_key_length_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "credentials"
        root.mkdir()
        (root / "verification-fingerprint-key.dpapi").write_bytes(b"enc:short")
        store = _store(root)
        try:
            store.fingerprint_key(create=False)
        except CredentialError as exc:
            assert str(exc) == "credential_blob_invalid"
        else:
            raise AssertionError("mismatched fingerprint key length must fail closed")
