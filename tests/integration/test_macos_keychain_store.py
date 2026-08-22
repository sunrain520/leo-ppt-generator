"""macOS arm64 Keychain 平台集成测试（13.2）。

真实 Keychain 路径仅使用唯一 service 与固定 provider account 的组合，测试结束时
删除该 item。锁定/拒绝状态无法在不更改用户 Keychain 会话状态下安全复现，因此通过
受控的 SecItem 状态返回验证适配器的稳定分类。
"""

from __future__ import annotations

import hashlib
import platform
import secrets
import subprocess
import sys
import uuid

import pytest

from leo_ppt_generator import credentials as credentials_module
from leo_ppt_generator.credentials import (
    CredentialError,
    MacOSKeychainStore,
    SecretBuffer,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or platform.machine().lower() not in {"arm64", "aarch64"},
    reason="仅在 macOS arm64 上运行真实 Keychain 平台集成测试",
)

_UNAVAILABLE_KEYCHAIN_REASONS = frozenset(
    {
        "credential_store_unsupported",
        "credential_store_locked",
        "credential_store_denied",
    }
)


class _StatusFailingKeychainAPI:
    """受控 SecItem 状态，避免为测试改变当前用户的 Keychain 安全状态。"""

    def __init__(self, status: int) -> None:
        self._status = status

    def copy(self, _service, _account, *, return_data):
        del return_data
        return self._status, None

    def add(self, _service, _account, _value):
        return self._status

    def update(self, _service, _account, _value):
        return self._status

    def delete(self, _service, _account):
        return self._status


def _isolated_live_store(monkeypatch: pytest.MonkeyPatch) -> MacOSKeychainStore:
    """返回使用唯一 service/account 对的真实 SecItem store，或跳过不可用环境。"""

    service = f"leo-ppt-generator-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(credentials_module, "KEYCHAIN_SERVICE", service)
    try:
        store = MacOSKeychainStore()
        assert isinstance(store.api, credentials_module._SecItemAPI)
        assert store.status("openai") == "missing"
    except CredentialError as exc:
        reason_code = str(exc)
        if reason_code in _UNAVAILABLE_KEYCHAIN_REASONS:
            pytest.skip(f"当前 Keychain 不可用于隔离集成测试：{reason_code}")
        raise
    return store


def _process_table_contains(secret: bytes) -> bool:
    """只返回布尔结果，避免在断言失败时将 secret 放进测试输出。"""

    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "command="],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"无法读取进程表以验证 argv 安全性：{type(exc).__name__}")
    return secret in result.stdout


def _secret_digest(secret: SecretBuffer) -> bytes:
    return hashlib.sha256(secret.reveal_bytes()).digest()


def test_macos_arm64_secitem_round_trip_uses_isolated_item_and_no_secret_argv(
    monkeypatch: pytest.MonkeyPatch,
):
    """真实 SecItem add/update/read/delete 不污染用户 item，且 secret 不进入 argv。"""

    store = _isolated_live_store(monkeypatch)
    first_secret = SecretBuffer(secrets.token_urlsafe(32))
    updated_secret = SecretBuffer(secrets.token_urlsafe(32))
    item_written = False

    try:
        assert store.remove("openai") is False

        store.write("openai", first_secret)
        item_written = True
        assert store.status("openai") == "available"
        assert hashlib.sha256(store.read("openai").encode("utf-8")).digest() == _secret_digest(
            first_secret
        )
        assert not _process_table_contains(first_secret.reveal_bytes())

        store.write("openai", updated_secret)
        assert hashlib.sha256(store.read("openai").encode("utf-8")).digest() == _secret_digest(
            updated_secret
        )
        assert not _process_table_contains(first_secret.reveal_bytes())
        assert not _process_table_contains(updated_secret.reveal_bytes())
    finally:
        try:
            if item_written:
                assert store.remove("openai") is True
            assert store.status("openai") == "missing"
        finally:
            first_secret.close()
            updated_secret.close()


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        pytest.param(-25308, "credential_store_locked", id="interaction-not-allowed"),
        pytest.param(-25293, "credential_store_denied", id="auth-failed"),
    ],
)
def test_macos_arm64_secitem_access_failures_have_stable_reason_codes(
    status: int,
    reason_code: str,
):
    """锁定和拒绝均由 SecItem 状态转换为稳定、非敏感的 reason code。"""

    store = MacOSKeychainStore(_StatusFailingKeychainAPI(status))

    with pytest.raises(CredentialError) as captured:
        store.status("openai")

    assert str(captured.value) == reason_code
