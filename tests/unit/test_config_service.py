"""ConfigService 状态编排的示例型单元测试。"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from leo_ppt_generator.config.models import (
    ArtifactDigest,
    Capability,
    CapabilityEvidence,
    ConfigStatus,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import (
    FileReceiptStore,
    compute_verification_fingerprint,
)
from leo_ppt_generator.config.runtime_config import ConfigStore, RuntimeConfigError
from leo_ppt_generator.config.service import (
    ConfigService,
    ConfigServiceError,
    StatusRequest,
)
from leo_ppt_generator.credentials import CredentialManager, UnsupportedCredentialStore

NOW = datetime(2026, 1, 8, tzinfo=UTC)


class FakeCredentialStore(UnsupportedCredentialStore):
    """支持 env 引用的测试凭据 store。"""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self.environ = environ or {}
        self.values: dict[str, str] = {}

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
                "credential_version": "hmac-sha256:unresolved",
            }
        if provider in self.values:
            return {
                "status": "available",
                "reason_code": "credential_store_available",
                "provider": provider,
                "reference_type": "os-store-reference",
                "credential_ref": f"keychain:leo-ppt-generator/{provider}",
            }
        return {
            "status": "missing",
            "reason_code": "credential_missing",
            "provider": provider,
            "reference_type": "none",
            "credential_ref": None,
        }

    def reference(self, provider: str) -> str:
        return f"keychain:leo-ppt-generator/{provider}"

    def read(self, provider: str) -> str:
        if provider not in self.values:
            raise Exception("credential_not_found")
        return self.values[provider]

    def write(self, provider: str, secret: str) -> None:
        self.values[provider] = (
            secret.reveal_text() if hasattr(secret, "reveal_text") else secret
        )

    def remove(self, provider: str) -> bool:
        return self.values.pop(provider, None) is not None

    def fingerprint_key(self, create: bool = False):
        return None


def _service(
    home: Path,
    *,
    config: dict | None = None,
    environ: dict[str, str] | None = None,
) -> ConfigService:
    store = ConfigStore(home)
    if config is not None:
        store.compare_and_swap(None, config)
    registry = ProviderRegistry.default()
    return ConfigService(
        store,
        FakeCredentialStore(environ),
        registry,
        FileReceiptStore(home, registry, clock=lambda: NOW),
        clock=lambda: NOW,
        cli_path="/usr/local/bin/leo-ppt",
    )


def test_status_empty_config_is_not_configured():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(Path(directory))
        report = svc.status(StatusRequest())
        assert report.status is ConfigStatus.NOT_CONFIGURED
        assert report.configuration_state.value == "not_configured"
        assert report.execution_eligibility.value == "blocked"
        assert report.reason_code in {"provider_selection_required", "provider_verification_not_run"}


def test_status_environment_configured_is_unverified_but_allowed():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(
            Path(directory),
            config={
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
            environ={"OPENAI_API_KEY": "sk-test"},
        )
        report = svc.status(StatusRequest())
        assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
        assert report.execution_eligibility.value == "allowed"
        assert report.installation_readiness.value == "usable_unverified"
        assert report.selected_provider is ProviderName.OPENAI
        assert report.readiness_scope.required_capabilities == frozenset({Capability.GENERATE})
        assert report.readiness_scope.missing_capabilities == frozenset({Capability.GENERATE})


def test_status_ready_with_valid_receipt():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config = {
            "schema_version": 1,
            "selected_provider": "openai",
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                }
            },
        }
        store = ConfigStore(home)
        store.compare_and_swap(None, config)
        registry = ProviderRegistry.default()
        receipt_store = FileReceiptStore(home, registry, clock=lambda: NOW)
        fingerprint = compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=None,
            model="gpt-image-2",
            credential_version="hmac-sha256:unresolved",
            runtime_identity="leo-ppt-generator/0.1.0",
            adapter_version=registry.provider(ProviderName.OPENAI, None).adapter.version,
            verification_policy_version=1,
        )
        receipt_store.merge(
            fingerprint,
            {
                Capability.GENERATE: CapabilityEvidence(
                    capability=Capability.GENERATE,
                    verified_at=NOW,
                    expires_at=NOW + timedelta(days=7),
                    operation_id="op-1",
                    verification_source=VerificationSource.PROVIDER_SMOKE,
                    artifact_digest=ArtifactDigest(
                        sha256="a" * 64, media_type="image/png", size_bytes=8
                    ),
                )
            },
        )
        svc = ConfigService(
            store,
            FakeCredentialStore({"OPENAI_API_KEY": "sk-test"}),
            registry,
            receipt_store,
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        report = svc.status(StatusRequest())
        assert report.status is ConfigStatus.READY
        assert report.execution_eligibility.value == "allowed"
        assert report.installation_readiness.value == "ready"
        assert report.readiness_scope.missing_capabilities == frozenset()


def test_status_environment_reference_missing_is_not_configuration_error():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(
            Path(directory),
            config={
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
            environ={},
        )
        report = svc.status(StatusRequest())
        assert report.status is ConfigStatus.NOT_CONFIGURED
        assert report.execution_eligibility.value == "blocked"
        assert report.reason_code == "credential_environment_missing"


def test_status_invalid_profile_is_invalid():
    """schema v1 不接受的 profile 在读取时被识别为 invalid，不静默忽略。"""
    with tempfile.TemporaryDirectory() as directory:
        # compare_and_swap 会对非法 profile 直接失败；这证明 schema 防线生效。
        with pytest.raises(Exception):
            _service(
                Path(directory),
                config={
                    "schema_version": 1,
                    "selected_provider": "openai",
                    "provider_profiles": {
                        "openai": {
                            "model": "",
                            "credential_source": "environment-reference",
                            "credential_ref": "env:OPENAI_API_KEY",
                        }
                    },
                },
                environ={"OPENAI_API_KEY": "sk-test"},
            )


def test_status_rejects_invalid_selected_provider():
    """selected_provider 指向不存在 profile 时写入即失败，不猜测选择。"""
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(Exception) as captured:
            _service(
                Path(directory),
                config={
                    "schema_version": 1,
                    "selected_provider": "openai",
                    "provider_profiles": {},
                },
            )
        assert "provider_selection_invalid" in str(captured.value)


def test_status_is_side_effect_free(tmp_path):
    """status 不得修改任何文件。"""
    home = tmp_path / "home"
    store = ConfigStore(home)
    before = None
    if store.path.exists():
        before = store.path.read_bytes()
    svc = _service(home)
    svc.status(StatusRequest())
    if before is None:
        assert not store.path.exists()
    else:
        assert store.path.read_bytes() == before


def test_change_switches_selected_provider_when_configured():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(
            Path(directory),
            config={
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                    },
                    "atlascloud": {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:ATLASCLOUD_API_KEY",
                    },
                },
            },
            environ={"OPENAI_API_KEY": "sk-a", "ATLASCLOUD_API_KEY": "sk-b"},
        )
        report = svc.change(
            StatusRequest(),
            selected_provider="atlascloud",
            operation_id="change-1",
        )
        assert report.selected_provider.value == "atlascloud"
        # 切换后重新读取确认持久化。
        assert svc.config_store.read().values["selected_provider"] == "atlascloud"


def test_change_unknown_provider_fails():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(Path(directory))
        try:
            svc.change(
                StatusRequest(),
                selected_provider="openai",
                operation_id="change-1",
            )
        except Exception as exc:
            assert "provider_profile_invalid" in str(exc)
        else:
            raise AssertionError("unknown provider change must fail")


def test_repair_returns_current_report():
    with tempfile.TemporaryDirectory() as directory:
        svc = _service(Path(directory))
        report = svc.repair(StatusRequest())
        assert report.status.value in {
            "not_configured",
            "configured_unverified",
            "ready",
            "invalid",
        }


def test_environment_profile_does_not_fall_back_to_os_store_credential():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
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
        credentials = FakeCredentialStore()
        credentials.values["openai"] = "stale-keychain-value"
        registry = ProviderRegistry.default()
        service = ConfigService(
            config_store,
            credentials,
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )

        report = service.status(StatusRequest())

        assert report.status is ConfigStatus.NOT_CONFIGURED
        assert report.reason_code == "credential_environment_missing"


def test_environment_profile_without_keyed_version_never_reuses_receipt():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
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
        registry = ProviderRegistry.default()
        receipt_store = FileReceiptStore(home, registry, clock=lambda: NOW)
        fingerprint = compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=None,
            model="gpt-image-2",
            credential_version="hmac-sha256:unresolved",
            runtime_identity="leo-ppt-generator/0.1.0",
            adapter_version=registry.provider(ProviderName.OPENAI, None).adapter.version,
            verification_policy_version=1,
        )
        receipt_store.merge(
            fingerprint,
            {
                Capability.GENERATE: CapabilityEvidence(
                    capability=Capability.GENERATE,
                    verified_at=NOW,
                    expires_at=NOW + timedelta(days=7),
                    operation_id="old-secret-op",
                    verification_source=VerificationSource.PROVIDER_SMOKE,
                    artifact_digest=ArtifactDigest(
                        sha256="b" * 64,
                        media_type="image/png",
                        size_bytes=8,
                    ),
                )
            },
        )
        credentials = FakeCredentialStore({"OPENAI_API_KEY": "rotated-secret"})
        service = ConfigService(
            config_store,
            credentials,
            registry,
            receipt_store,
            clock=lambda: NOW,
            credential_reader=lambda _provider: {
                "status": "available",
                "reason_code": "credential_store_available",
                "reference_type": "environment-reference",
                "credential_ref": "env:OPENAI_API_KEY",
            },
        )

        report = service.status(StatusRequest())

        assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
        assert report.readiness_scope.verified_capabilities == frozenset()


def test_change_surfaces_cas_conflict_without_switching_provider(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        service = _service(
            Path(directory),
            config={
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                    },
                    "atlascloud": {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:ATLASCLOUD_API_KEY",
                    },
                },
            },
            environ={"OPENAI_API_KEY": "sk-a", "ATLASCLOUD_API_KEY": "sk-b"},
        )

        def conflict(*_args, **_kwargs):
            raise RuntimeConfigError("config_write_conflict")

        monkeypatch.setattr(service.config_store, "compare_and_swap", conflict)

        with pytest.raises(ConfigServiceError) as captured:
            service.change(
                StatusRequest(),
                selected_provider="atlascloud",
                operation_id="change-conflict",
            )

        assert captured.value.reason_code == "config_write_conflict"
        assert service.config_store.read().values["selected_provider"] == "openai"


def test_configure_explicit_credential_replacement_bumps_generation_and_overwrites_store():
    from leo_ppt_generator.config.service import ConfigureRequest
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputSelection,
        SecretBuffer,
    )

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "os-store-reference",
                        "credential_ref": "keychain:leo-ppt-generator/openai",
                        "credential_generation": 4,
                    }
                },
            },
        )
        credentials = FakeCredentialStore()
        credentials.values["openai"] = "old-secret"
        registry = ProviderRegistry.default()
        service = ConfigService(
            config_store,
            credentials,
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("new-secret"),
        )

        service.configure(
            ConfigureRequest(
                provider="openai",
                credential=selection,
                model="gpt-image-2",
                operation_id="replace-openai-secret",
                overwrite_credential=True,
            )
        )

        profile = config_store.read().values["provider_profiles"]["openai"]
        assert profile["credential_generation"] == 5
        assert credentials.values["openai"] == "new-secret"
        assert selection.secret is not None and selection.secret.closed is True


def test_configure_rejects_credential_overwrite_without_explicit_authorization():
    from leo_ppt_generator.config.service import ConfigureRequest
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputSelection,
        SecretBuffer,
    )

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "os-store-reference",
                        "credential_ref": "keychain:leo-ppt-generator/openai",
                        "credential_generation": 2,
                    }
                },
            },
        )
        credentials = FakeCredentialStore()
        credentials.values["openai"] = "old-secret"
        registry = ProviderRegistry.default()
        service = ConfigService(
            config_store,
            credentials,
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
        )
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("unauthorized-secret"),
        )

        with pytest.raises(
            ConfigServiceError,
            match="credential_overwrite_confirmation_required",
        ):
            service.configure(
                ConfigureRequest(
                    provider="openai",
                    credential=selection,
                    model="gpt-image-2",
                    operation_id="unauthorized-overwrite",
                )
            )

        assert credentials.values["openai"] == "old-secret"
        assert config_store.read().values["provider_profiles"]["openai"][
            "credential_generation"
        ] == 2
        assert selection.secret is not None and selection.secret.closed is True


@pytest.mark.parametrize(
    "commit_failure",
    (RuntimeConfigError("config_write_conflict"), KeyboardInterrupt()),
)
def test_explicit_credential_replacement_restores_old_secret_when_commit_fails(
    monkeypatch, commit_failure
):
    from leo_ppt_generator.config.service import ConfigureRequest
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputSelection,
        SecretBuffer,
    )

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "os-store-reference",
                        "credential_ref": "keychain:leo-ppt-generator/openai",
                        "credential_generation": 7,
                    }
                },
            },
        )
        credentials = FakeCredentialStore()
        credentials.values["openai"] = "old-secret"
        registry = ProviderRegistry.default()
        service = ConfigService(
            config_store,
            credentials,
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
        )
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("new-secret"),
        )

        def fail_commit(*_args, **_kwargs):
            raise commit_failure

        monkeypatch.setattr(config_store, "compare_and_swap", fail_commit)

        with pytest.raises(type(commit_failure)):
            service.configure(
                ConfigureRequest(
                    provider="openai",
                    credential=selection,
                    model="gpt-image-2",
                    operation_id="replacement-commit-failure",
                    overwrite_credential=True,
                )
            )

        assert credentials.values["openai"] == "old-secret"
        profile = config_store.read().values["provider_profiles"]["openai"]
        assert profile["credential_generation"] == 7
        assert selection.secret is not None and selection.secret.closed is True
