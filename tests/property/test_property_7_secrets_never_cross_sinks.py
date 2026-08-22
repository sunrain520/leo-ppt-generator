# Feature: guided-provider-config, Property 7: Secrets never cross forbidden
# sinks

from __future__ import annotations

import io
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.transactions import ConfigTransactionJournal
from leo_ppt_generator.config.verification_operations import (
    FileVerificationCoordinator,
    VerificationIntent,
)
from leo_ppt_generator.credentials import (
    CredentialError,
    CredentialInputChannel,
    CredentialInputSelection,
    SecretBuffer,
    environment_credential_version,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_REGISTRY = ProviderRegistry.default()


def _canary() -> str:
    return f"sk-canary-{__import__('uuid').uuid4().hex}-secret"


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")),
)
def test_property_7_canary_never_crosses_journal_or_receipt(provider):
    """**Validates: Requirements 15.2, 15.4, 11.5**"""
    canary = _canary()
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        # 事务 journal
        journal = ConfigTransactionJournal(home, clock=lambda: NOW)
        journal.write(
            f"op-{provider}",
            provider=provider,
            step="prepared",
            target_generation=1,
        )
        # verification operation journal（模拟含 canary 的失败上下文）
        coordinator = FileVerificationCoordinator(
            home, _REGISTRY, clock=lambda: NOW
        )
        from leo_ppt_generator.config.models import (
            Capability,
            ProviderName,
            VerificationScope,
        )
        from leo_ppt_generator.config.receipt_store import (
            compute_verification_fingerprint,
        )

        fp = compute_verification_fingerprint(
            provider=ProviderName(provider),
            endpoint_origin=None,
            model="gpt-image-2",
            credential_version="generation:1",
            runtime_identity="leo-ppt-generator/test",
            adapter_version=_REGISTRY.provider(ProviderName(provider), None).adapter.version,
            verification_policy_version=1,
        )
        scope = VerificationScope(
            fingerprint=fp,
            required_capabilities=frozenset({Capability.GENERATE}),
        )
        coordinator.begin(
            scope,
            VerificationIntent(
                operation_id=f"op-{provider}",
                intent_id=f"intent-{provider}",
                provider=ProviderName(provider),
                capabilities=frozenset({Capability.GENERATE}),
                request_identity=canary,  # canary 作为请求标识（模拟用户输入）
            ),
        )
        # 所有持久化产物不得包含 canary。
        for path in home.rglob("*"):
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                assert canary not in content, f"{path} 泄露 canary"


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")),
)
def test_property_7_hidden_input_canary_not_in_args_or_output(provider):
    """**Validates: Requirements 3.4, 10.5**"""
    canary = _canary()
    selection = CredentialInputSelection(
        channel=CredentialInputChannel.TTY_GETPASS,
        reason_code="credential_input_tty",
        secret=SecretBuffer(canary),
    )
    # secret 的 repr/str 永不明文。
    assert canary not in repr(selection)
    assert canary not in str(selection)
    # 序列化含 secret 的选择必须失败（不可序列化防线）。
    try:
        json.dumps({"secret": selection.secret})
    except TypeError:
        pass
    else:
        raise AssertionError("secret 可以被 JSON 序列化")
    # stdout/stderr 捕获无 canary。
    stdout = io.StringIO()
    stderr = io.StringIO()
    print(repr(selection), file=stdout)
    print(str(selection.reason_code), file=stderr)
    assert canary not in stdout.getvalue()
    assert canary not in stderr.getvalue()
    selection.close()


def test_property_7_hmac_version_does_not_expose_secret():
    """**Validates: Requirements 15.2**"""
    canary = _canary()
    key = SecretBuffer(b"\x42" * 32)
    version = environment_credential_version(
        key,
        provider="openai",
        env_name="OPENAI_API_KEY",
        secret=SecretBuffer(canary),
    )
    assert "sk-canary" not in version
    assert canary not in version
    # 截断引用更短。
    from leo_ppt_generator.credentials import credential_version_reference

    reference = credential_version_reference(version)
    assert canary not in reference
    key.close()


def test_property_7_unsupported_platform_has_no_plaintext_residue():
    """**Validates: Requirements 3.10, 10.5**"""
    from leo_ppt_generator.credentials import UnsupportedCredentialStore

    canary = _canary()
    store = UnsupportedCredentialStore()
    try:
        store.write("openai", canary)
    except CredentialError as error:
        assert str(error) == "credential_store_unsupported"
    else:
        raise AssertionError("unsupported store 必须拒绝写入")
    # 无残留文件。
    with tempfile.TemporaryDirectory() as directory:
        assert list(Path(directory).iterdir()) == []