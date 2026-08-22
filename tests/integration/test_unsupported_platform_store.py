"""Unsupported platform adapter contract test（13.4）。

安全存储不可用时稳定返回 credential_store_unsupported，不创建 plaintext
fallback、普通临时 secret 或可被识别为有效凭据的残留文件。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from leo_ppt_generator.credentials import (
    CredentialError,
    UnsupportedCredentialStore,
)


@pytest.mark.parametrize(
    "provider",
    ("openai", "openai-compatible", "atlascloud", "paddleocr"),
)
def test_unsupported_store_rejects_all_providers(provider):
    store = UnsupportedCredentialStore()
    with pytest.raises(CredentialError) as captured:
        store.reference(provider)
    assert str(captured.value) == "credential_store_unsupported"
    with pytest.raises(CredentialError) as captured:
        store.read(provider)
    assert str(captured.value) == "credential_store_unsupported"
    with pytest.raises(CredentialError) as captured:
        store.write(provider, "plaintext-canary")
    assert str(captured.value) == "credential_store_unsupported"
    assert store.status(provider) == "missing"
    assert store.remove(provider) is False


def test_unsupported_store_never_creates_plaintext_files(tmp_path):
    store = UnsupportedCredentialStore()
    home = tmp_path / "leo-home"
    with pytest.raises(CredentialError):
        store.write("openai", "plaintext-canary")
    # 无任何文件被创建。
    assert not home.exists()
    # 即使目录存在也不写入。
    home.mkdir()
    with pytest.raises(CredentialError):
        store.write("openai", "plaintext-canary")
    assert list(home.iterdir()) == []


def test_unsupported_store_fingerprint_key_returns_none_without_residue(tmp_path):
    store = UnsupportedCredentialStore()
    home = tmp_path / "leo-home"
    home.mkdir()
    key = store.fingerprint_key(create=True)
    assert key is None
    assert list(home.iterdir()) == []


def test_platform_store_on_unknown_platform_is_unsupported(monkeypatch):
    import sys

    from leo_ppt_generator import credentials

    monkeypatch.setattr(sys, "platform", "freebsd")
    monkeypatch.setattr(sys, "platform", "linux")
    # Linux 不是受支持的安全凭据平台：必须返回 unsupported store。
    store = credentials.platform_store()
    with pytest.raises(CredentialError) as captured:
        store.write("openai", "canary")
    assert str(captured.value) == "credential_store_unsupported"
