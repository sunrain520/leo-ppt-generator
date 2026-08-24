# Feature: guided-provider-config, Property 19: Environment credential
# versions are keyed and rotation-sensitive

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.credentials import (
    CREDENTIAL_VERSION_PREFIX,
    CredentialError,
    SecretBuffer,
    credential_version_reference,
    environment_credential_version,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)

PROVIDERS = ("openai", "openai-compatible", "atlascloud")
ENV_NAMES = {
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
    "atlascloud": "ATLASCLOUD_API_KEY",
}


@st.composite
def version_inputs(draw: st.DrawFn):
    provider = draw(st.sampled_from(PROVIDERS))
    return {
        "provider": provider,
        "env_name": ENV_NAMES[provider],
        "secret": draw(st.text(min_size=1, max_size=64)),
        "key_bytes": draw(st.binary(min_size=32, max_size=32)),
    }


@PROPERTY_SETTINGS
@given(case=version_inputs())
def test_property_19_environment_credential_versions_are_keyed_and_rotation_sensitive(case):
    """**Validates: Requirements 7.7**"""
    key = SecretBuffer(case["key_bytes"])
    version = environment_credential_version(
        key,
        provider=case["provider"],
        env_name=case["env_name"],
        secret=SecretBuffer(case["secret"]),
    )
    assert version.startswith(f"{CREDENTIAL_VERSION_PREFIX}:")
    digest = version[len(f"{CREDENTIAL_VERSION_PREFIX}:") :]
    assert len(digest) == 64

    # 相同输入产生稳定版本。
    again = environment_credential_version(
        key,
        provider=case["provider"],
        env_name=case["env_name"],
        secret=SecretBuffer(case["secret"]),
    )
    assert version == again

    # 任一 secret / key / provider / env-name 变化都改变版本。
    changed_secret = environment_credential_version(
        key,
        provider=case["provider"],
        env_name=case["env_name"],
        secret=SecretBuffer(case["secret"] + "x"),
    )
    assert changed_secret != version

    changed_key = environment_credential_version(
        SecretBuffer(bytes(byte ^ 0x01 for byte in case["key_bytes"])),
        provider=case["provider"],
        env_name=case["env_name"],
        secret=SecretBuffer(case["secret"]),
    )
    assert changed_key != version

    other_provider = next(p for p in PROVIDERS if p != case["provider"])
    changed_provider = environment_credential_version(
        key,
        provider=other_provider,
        env_name=ENV_NAMES[other_provider],
        secret=SecretBuffer(case["secret"]),
    )
    assert changed_provider != version

    changed_env = environment_credential_version(
        key,
        provider=case["provider"],
        env_name=case["env_name"] + "_ALT",
        secret=SecretBuffer(case["secret"]),
    )
    assert changed_env != version

    # 输出是 keyed HMAC 摘要：不等于裸 SHA-256(secret)，也不是可逆编码。
    import hashlib

    bare = hashlib.sha256(case["secret"].encode("utf-8")).hexdigest()
    assert f"{CREDENTIAL_VERSION_PREFIX}:{bare}" != version
    # 足够长的 secret 不得以连续子串出现在 hex 输出中（短 secret 的单个
    # 字符偶然出现在 hex 字符集内是正常的，不构成泄露）。
    if len(case["secret"]) >= 24:
        assert case["secret"] not in version
        assert case["secret"].encode("utf-8") not in version.encode("utf-8")


@PROPERTY_SETTINGS
@given(case=version_inputs())
def test_property_19_credential_version_reference_is_truncated_and_stable(case):
    """**Validates: Requirements 7.7, 15.2**"""
    key = SecretBuffer(case["key_bytes"])
    version = environment_credential_version(
        key,
        provider=case["provider"],
        env_name=case["env_name"],
        secret=SecretBuffer(case["secret"]),
    )
    reference = credential_version_reference(version)
    # 人类输出绝不展示完整 HMAC。
    assert version not in reference
    assert reference.startswith(f"{CREDENTIAL_VERSION_PREFIX}:")
    assert len(reference) < len(version)
    # 同一版本引用稳定。
    assert credential_version_reference(version) == reference


@PROPERTY_SETTINGS
@given(value=st.text())
def test_property_19_reference_rejects_malformed_versions(value):
    """**Validates: Requirements 7.7, 15.2**"""
    if value.startswith(f"{CREDENTIAL_VERSION_PREFIX}:") and len(
        value[len(f"{CREDENTIAL_VERSION_PREFIX}:") :]
    ) == 64:
        return
    try:
        credential_version_reference(value)
    except CredentialError:
        return
    raise AssertionError(f"malformed version accepted: {value!r}")


def test_closed_fingerprint_key_is_rejected():
    key = SecretBuffer(b"\x01" * 32)
    key.close()
    try:
        environment_credential_version(
            key,
            provider="openai",
            env_name="OPENAI_API_KEY",
            secret=SecretBuffer("secret"),
        )
    except CredentialError as exc:
        assert str(exc) == "credential_secret_closed"
        return
    raise AssertionError("closed fingerprint key must be rejected")
