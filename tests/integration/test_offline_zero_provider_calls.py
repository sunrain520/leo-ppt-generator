"""离线零真实 Provider 调用与 opt-in paid smoke 安全门测试（13.6）。

普通 unit/integration/release/installer/skill eval 必须零真实网络；
真实 Provider smoke 只存在于显式 opt-in 路径。本测试验证控制面
（status/verify/change/repair）不触发任何 Provider 调用。
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import ConfigService, StatusRequest

NOW = datetime(2026, 1, 8, tzinfo=UTC)
_REGISTRY = ProviderRegistry.default()


class OfflineEnvStore:
    """env 引用凭据 store；任何 read 都触发断言（status 路径零读取）。"""

    def __init__(self, environ: dict[str, str]) -> None:
        self.environ = environ
        self.read_calls = 0

    def status(self, provider: str) -> dict:
        from leo_ppt_generator.credentials import PROVIDERS

        env_name = PROVIDERS[provider]
        if self.environ.get(env_name):
            return {
                "status": "available",
                "reason_code": "credential_store_available",
                "provider": provider,
                "reference_type": "environment-reference",
                "credential_ref": f"env:{env_name}",
            }
        return {
            "status": "missing",
            "reason_code": "credential_missing",
            "provider": provider,
            "reference_type": "none",
            "credential_ref": None,
        }

    def reference(self, provider: str) -> str:
        return f"env:{provider}"

    def read(self, provider: str) -> str:
        self.read_calls += 1
        raise AssertionError("离线 status 不得读取 secret（零 Provider 调用）")

    def write(self, provider: str, secret) -> None:
        raise AssertionError("离线 status 不得写入")

    def remove(self, provider: str) -> bool:
        raise AssertionError("离线 status 不得删除")

    def fingerprint_key(self, create: bool = False):
        return None


def _service(home: Path, environ: dict[str, str]) -> ConfigService:
    store = ConfigStore(home)
    store.compare_and_swap(
        None,
        {
            "schema_version": 1,
            "selected_provider": "openai",
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                }
            },
        },
    )
    return ConfigService(
        store,
        OfflineEnvStore(environ),
        _REGISTRY,
        FileReceiptStore(home, _REGISTRY, clock=lambda: NOW),
        clock=lambda: NOW,
        cli_path="/usr/local/bin/leo-ppt",
    )


def test_status_verify_change_repair_are_zero_provider_calls(monkeypatch):
    """status/verify/change/repair 全部零网络、零 Provider 调用。"""
    # 拦截所有网络出口：任何真实调用立即失败。
    import socket

    def deny_connect(*args, **kwargs):
        raise AssertionError("离线模式禁止任何网络连接")

    monkeypatch.setattr(socket, "create_connection", deny_connect)

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _service(home, {"OPENAI_API_KEY": "sk-offline"})
        report = service.status(StatusRequest())
        assert report.status.value == "configured_unverified"

        verify = service.verify(StatusRequest())
        assert verify.status.value == "configured_unverified"

        changed = service.change(
            StatusRequest(), selected_provider="openai", operation_id="op-1"
        )
        assert changed.status.value == "configured_unverified"

        repaired = service.repair(StatusRequest())
        assert repaired.status.value == "configured_unverified"


def test_status_with_missing_env_blocks_without_network():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _service(home, {})
        report = service.status(StatusRequest())
        assert report.status.value == "not_configured"
        assert report.reason_code == "credential_environment_missing"
        # primary action 是终端命令，绝不触网。
        assert report.primary_action is not None
        assert report.primary_action.kind.value == "run_cli"


def test_no_paid_smoke_without_explicit_consent():
    """ConfigService 不持有任何自动触发 smoke 的路径。"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _service(home, {"OPENAI_API_KEY": "sk-offline"})
        # 任何 status/verify 都不写 evidence。
        for _ in range(3):
            report = service.status(StatusRequest())
            assert report.readiness_scope.verified_capabilities == frozenset()
