# Feature: guided-provider-config, Property 8: Existing credentials are
# preserved without overwrite consent

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.credentials import (
    CredentialError,
    CredentialInputChannel,
    CredentialInputResolver,
    CredentialInputSelection,
    SecretBuffer,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
_PROVIDERS = ("openai", "openai-compatible", "atlascloud")


class RecordingStore:
    """记录写入/覆盖意图的凭据 store。"""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.write_calls: list[str] = []

    def reference(self, provider: str) -> str:
        return f"keychain:leo-ppt-generator/{provider}"

    def status(self, provider: str) -> str:
        return "available" if provider in self.values else "missing"

    def read(self, provider: str) -> str:
        return self.values[provider]

    def write(self, provider: str, secret) -> None:
        self.write_calls.append(provider)
        self.values[provider] = (
            secret.reveal_text() if isinstance(secret, SecretBuffer) else str(secret)
        )

    def remove(self, provider: str) -> bool:
        return self.values.pop(provider, None) is not None

    def fingerprint_key(self, create: bool = False):
        return None


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(_PROVIDERS),
    existing=st.text(min_size=1, max_size=16),
    new_secret=st.text(min_size=1, max_size=16),
)
def test_property_8_existing_credentials_preserved_without_overwrite_consent(
    provider, existing, new_secret
):
    """**Validates: Requirements 3.8, 3.9, 13.1**"""
    with tempfile.TemporaryDirectory() as directory:
        store = RecordingStore({provider: existing})
        resolver = CredentialInputResolver(store=store, environ={})
        # 已存在凭据时，select 走 EXISTING_STORE 通道，不读取 stdin、不覆盖。
        selection = resolver.select(provider)
        assert selection.channel is CredentialInputChannel.EXISTING_STORE
        assert selection.credential_ref == store.reference(provider)
        assert selection.secret is None
        # resolver 不触发任何写入，且选择后已有值保持不变。
        assert store.write_calls == []
        assert store.values[provider] == existing


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(_PROVIDERS),
    secret=st.text(min_size=1, max_size=16),
)
def test_property_8_missing_credential_goes_to_input_channel(provider, secret):
    """**Validates: Requirements 3.4, 3.5, 3.6**"""
    store = RecordingStore()
    resolver = CredentialInputResolver(store=store, environ={})
    # 无 TTY 且无 --key-stdin 时：通道不可用，不读取 stdin。
    class Pipe:
        def isatty(self):
            return False

        def readline(self):
            raise AssertionError("不得在未授权时读取 stdin")

    selection = resolver.select(provider, input_stream=Pipe(), tty_stream=Pipe())
    assert selection.channel is CredentialInputChannel.UNAVAILABLE
    assert selection.secret is None
    assert store.values == {}
