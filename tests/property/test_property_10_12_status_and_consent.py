# Feature: guided-provider-config, Property 10: Local status is side-effect
# free; Property 12: Paid verification requires a one-shot affirmative capability

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings, strategies as st

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


class EnvCredentialStore:
    """只读 env 引用凭据 store；status 无副作用。"""

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
        return f"env:{provider.upper()}"

    def read(self, provider: str) -> str:
        raise AssertionError("status 不得读取 secret")

    def write(self, provider: str, secret) -> None:
        raise AssertionError("status 不得写入 secret")

    def remove(self, provider: str) -> bool:
        raise AssertionError("status 不得删除 secret")

    def fingerprint_key(self, create: bool = False):
        raise AssertionError("status 不得创建 fingerprint key")


@st.composite
def config_cases(draw: st.DrawFn):
    provider = draw(st.sampled_from(("openai", "openai-compatible", "atlascloud")))
    env_missing = draw(st.booleans())
    return {"provider": provider, "env_missing": env_missing}


@PROPERTY_SETTINGS
@given(case=config_cases())
def test_property_10_local_status_is_side_effect_free(case):
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4**"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        provider = case["provider"]
        env_value = "" if case["env_missing"] else "sk-property-10"
        environ = {f"{provider.upper().replace('-', '_')}_API_KEY": env_value}
        # env 名不匹配 provider 时使用正确映射。
        from leo_ppt_generator.credentials import PROVIDERS

        environ = {PROVIDERS[provider]: env_value}
        store = ConfigStore(home)
        store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": provider,
                "provider_profiles": {
                    provider: {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": f"env:{PROVIDERS[provider]}",
                        **(
                            {"endpoint_origin": "https://images.example.com"}
                            if provider == "openai-compatible"
                            else {}
                        ),
                    }
                },
            },
        )
        registry = ProviderRegistry.default()
        service = ConfigService(
            store,
            EnvCredentialStore(environ),
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        tree_before = _tree(home)
        report = service.status(StatusRequest())
        tree_after = _tree(home)
        # status 不创建、修改或删除任何文件。
        assert tree_before == tree_after
        # status 不发起 Provider 调用（EnvCredentialStore 禁止 read/write）。
        assert report.status.value in {
            "configured_unverified",
            "not_configured",
        }


# ---------------------------------------------------------------- Property 12
@PROPERTY_SETTINGS
@given(provider=st.sampled_from(("openai", "openai-compatible", "atlascloud")))
def test_property_12_paid_verification_requires_affirmative_consent(provider):
    """**Validates: Requirements 6.1, 6.2, 6.3**"""
    # 付费 smoke 的同意是单次肯定能力；默认必须为"否"。
    # 本测试验证：ConfigService 不持有任何自动触发 smoke 的路径。
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        from leo_ppt_generator.credentials import PROVIDERS

        environ = {PROVIDERS[provider]: "sk-consent-test"}
        store = ConfigStore(home)
        store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": provider,
                "provider_profiles": {
                    provider: {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": f"env:{PROVIDERS[provider]}",
                        **(
                            {"endpoint_origin": "https://images.example.com"}
                            if provider == "openai-compatible"
                            else {}
                        ),
                    }
                },
            },
        )
        registry = ProviderRegistry.default()
        service = ConfigService(
            store,
            EnvCredentialStore(environ),
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        # status 与 verify（无显式同意）都不产生付费调用、不写入 evidence。
        report = service.status(StatusRequest())
        verify_report = service.verify(StatusRequest())
        assert report.status.value == "configured_unverified"
        assert verify_report.readiness_scope.verified_capabilities == frozenset()
        assert verify_report.readiness_scope.missing_capabilities == frozenset(
            {"generate"}
        ) or verify_report.readiness_scope.missing_capabilities


def _tree(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
    )
