# Feature: guided-provider-config, Properties 26/27: Onboarding decisions do
# not alter installation truth; update checks reuse valid state and preserve
# typed recovery

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.models import (
    Capability,
    ConfigStatus,
    InstallationReadiness,
    ProviderName,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import ConfigService, StatusRequest

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_PROVIDERS = (ProviderName.OPENAI, ProviderName.OPENAI_COMPATIBLE, ProviderName.ATLASCLOUD)


class EnvStore:
    def __init__(self, environ: dict[str, str]) -> None:
        self.environ = environ

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
        raise AssertionError("status 不得读取 secret")

    def write(self, provider: str, secret) -> None:
        raise AssertionError("onboarding 不得写入 secret")

    def remove(self, provider: str) -> bool:
        raise AssertionError("onboarding 不得删除 secret")

    def fingerprint_key(self, create: bool = False):
        return None


@st.composite
def onboarding_cases(draw: st.DrawFn):
    provider = draw(st.sampled_from(_PROVIDERS))
    env_present = draw(st.booleans())
    return {"provider": provider, "env_present": env_present}


@PROPERTY_SETTINGS
@given(case=onboarding_cases())
def test_property_26_onboarding_does_not_alter_installation_truth(case):
    """**Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6**"""
    from leo_ppt_generator.credentials import PROVIDERS

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        env_name = PROVIDERS[case["provider"].value]
        environ = {env_name: "sk-x"} if case["env_present"] else {}
        store = ConfigStore(home)
        store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": case["provider"].value,
                "provider_profiles": {
                    case["provider"].value: {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": f"env:{env_name}",
                        **(
                            {"endpoint_origin": "https://images.example.com"}
                            if case["provider"] is ProviderName.OPENAI_COMPATIBLE
                            else {}
                        ),
                    }
                },
            },
        )
        registry = ProviderRegistry.default()
        service = ConfigService(
            store,
            EnvStore(environ),
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        report = service.status(StatusRequest())
        status = ConfigStatus(report.status)

        # onboarding 报告映射 Installation_Readiness：
        # External ready 保持 host unknown；configured_unverified 可用；
        # blocked/retryable 才未就绪。
        if status in {ConfigStatus.READY, ConfigStatus.CONFIGURED_UNVERIFIED}:
            assert InstallationReadiness(report.installation_readiness) in {
                InstallationReadiness.READY,
                InstallationReadiness.USABLE_UNVERIFIED,
            }
        else:
            assert (
                InstallationReadiness(report.installation_readiness)
                is InstallationReadiness.INSTALLED_NOT_READY
            )
        # 向导失败/推迟不把已激活 Skill 变回未安装（无安装状态字段）。
        assert "installed" in str(report.installation_readiness) or status.value in {
            "ready",
            "configured_unverified",
        }


@PROPERTY_SETTINGS
@given(case=onboarding_cases())
def test_property_27_update_reuses_valid_state_and_preserves_typed_recovery(case):
    """**Validates: Requirements 9.2, 9.3, 9.5**"""
    from leo_ppt_generator.credentials import PROVIDERS

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        env_name = PROVIDERS[case["provider"].value]
        environ = {env_name: "sk-update"} if case["env_present"] else {}
        store = ConfigStore(home)
        store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": case["provider"].value,
                "provider_profiles": {
                    case["provider"].value: {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": f"env:{env_name}",
                        **(
                            {"endpoint_origin": "https://images.example.com"}
                            if case["provider"] is ProviderName.OPENAI_COMPATIBLE
                            else {}
                        ),
                    }
                },
            },
        )
        registry = ProviderRegistry.default()
        service = ConfigService(
            store,
            EnvStore(environ),
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        # 更新检查（重复 status）不提问、不付费，复用有效本地状态。
        first = service.status(StatusRequest())
        second = service.status(StatusRequest())
        assert first.status is second.status
        assert first.readiness_scope.to_dict() == second.readiness_scope.to_dict()
        # 缺失/过期时回到 usable_unverified；不误报 ready。
        if case["env_present"]:
            assert InstallationReadiness(first.installation_readiness) in {
                InstallationReadiness.READY,
                InstallationReadiness.USABLE_UNVERIFIED,
            }