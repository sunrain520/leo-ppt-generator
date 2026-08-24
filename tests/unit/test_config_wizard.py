"""ConfigWizard 的示例型单元测试。"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import (
    ConfigService,
    ConfigServiceError,
    StatusRequest,
)
from leo_ppt_generator.config.wizard import ConfigWizard, WizardCancelled
from leo_ppt_generator.credentials import (
    CredentialInputChannel,
    CredentialInputSelection,
    CredentialInputResolver,
    SecretBuffer,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)


class MenuStore:
    """把菜单选择和展示项记录下来的假输入。"""

    def __init__(self, choices: list[int | None]) -> None:
        self.choices = list(choices)
        self.menus: list[str] = []
        self.presented_choices: list[tuple[str, ...]] = []

    def menu(self, choices, title):
        self.menus.append(title)
        self.presented_choices.append(tuple(choices))
        return self.choices.pop(0) if self.choices else None


class FixedResolver:
    def __init__(self, selection: CredentialInputSelection) -> None:
        self.selection = selection
        self.calls: list[tuple[str, dict]] = []

    def select(self, provider: str, **kwargs) -> CredentialInputSelection:
        self.calls.append((provider, kwargs))
        return self.selection


class MemoryStore:
    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = {}
        self.environ = environ or {}
        self.writes = 0

    def reference(self, provider: str) -> str:
        return f"keychain:leo-ppt-generator/{provider}"

    def status(self, provider: str) -> str:
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
        return "available" if provider in self.values else "missing"

    def read(self, provider: str) -> str:
        if provider not in self.values:
            raise Exception("credential_not_found")
        return self.values[provider]

    def write(self, provider: str, secret) -> None:
        self.writes += 1
        self.values[provider] = (
            secret.reveal_text() if isinstance(secret, SecretBuffer) else str(secret)
        )

    def remove(self, provider: str) -> bool:
        return self.values.pop(provider, None) is not None

    def fingerprint_key(self, create: bool = False):
        return None


def _service(home: Path, credential_store) -> ConfigService:
    registry = ProviderRegistry.default()
    return ConfigService(
        ConfigStore(home),
        credential_store,
        registry,
        FileReceiptStore(home, registry, clock=lambda: NOW),
        clock=lambda: NOW,
        cli_path="/usr/local/bin/leo-ppt",
    )


def _env_resolver(environ: dict[str, str]) -> CredentialInputResolver:
    return CredentialInputResolver(store=MemoryStore(), environ=environ)


def test_configured_wizard_shows_current_profile_and_enter_keeps_everything():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai-compatible",
                "provider_profiles": {
                    "openai-compatible": {
                        "endpoint_origin": "https://relay.example.com",
                        "model": "relay-image-v1",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                    }
                },
            },
        )
        credential_store = MemoryStore(
            {"OPENAI_API_KEY": "environment-secret"}
        )
        unavailable = CredentialInputSelection(
            channel=CredentialInputChannel.UNAVAILABLE,
            reason_code="credential_input_channel_unavailable",
        )
        resolver = FixedResolver(unavailable)
        menu = MenuStore([1])
        answers = iter(("", ""))
        prompts: list[str] = []
        confirmations: list[tuple[str, bool]] = []

        def prompt(text: str) -> str:
            prompts.append(text)
            return next(answers)

        def confirm(text: str, default: bool) -> bool:
            confirmations.append((text, default))
            return True

        before = config_store.path.read_bytes()
        result = ConfigWizard(
            _service(home, credential_store),
            resolver,
            menu=menu.menu,
            prompt=prompt,
            confirm=confirm,
        ).run(StatusRequest())

        assert config_store.path.read_bytes() == before
        assert menu.presented_choices[0][1].endswith("（当前）")
        assert prompts == [
            "请输入中转站 HTTPS 地址（当前 https://relay.example.com，回车保留）：",
            "请输入图片模型（当前 relay-image-v1，回车保留）：",
        ]
        assert confirmations == [
            (
                "当前凭据：environment-reference env:OPENAI_API_KEY。是否保留？",
                True,
            )
        ]
        assert "environment-secret" not in "".join(prompts + [confirmations[0][0]])
        assert resolver.calls == []
        assert credential_store.writes == 0
        assert result.cancelled is False
        assert result.report.status.value == "configured_unverified"


def test_configured_wizard_edits_profile_and_preserves_exact_credential_reference():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        ConfigStore(home).compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai-compatible",
                "provider_profiles": {
                    "openai-compatible": {
                        "endpoint_origin": "https://old.example.com",
                        "model": "old-model",
                        "credential_source": "os-store-reference",
                        "credential_ref": "keychain:leo-ppt-generator/openai-compatible",
                        "credential_generation": 3,
                    }
                },
            },
        )
        credential_store = MemoryStore(
            {"OPENAI_API_KEY": "environment-must-not-win"}
        )
        credential_store.values["openai-compatible"] = "stored-secret"
        resolver = FixedResolver(
            CredentialInputSelection(
                channel=CredentialInputChannel.ENVIRONMENT,
                reason_code="credential_environment_available",
                credential_ref="env:OPENAI_API_KEY",
            )
        )
        answers = iter(("https://new.example.com", "new-model"))

        ConfigWizard(
            _service(home, credential_store),
            resolver,
            menu=MenuStore([1]).menu,
            prompt=lambda _text: next(answers),
            confirm=lambda _text, _default: True,
        ).run(StatusRequest())

        profile = ConfigStore(home).read().values["provider_profiles"][
            "openai-compatible"
        ]
        assert profile == {
            "endpoint_origin": "https://new.example.com",
            "model": "new-model",
            "credential_source": "os-store-reference",
            "credential_ref": "keychain:leo-ppt-generator/openai-compatible",
            "credential_generation": 3,
            "enabled": True,
            "priority": 100,
        }
        assert resolver.calls == []
        assert credential_store.values["openai-compatible"] == "stored-secret"
        assert credential_store.writes == 0


def test_configured_wizard_explicitly_replaces_secret_without_echoing_it():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        ConfigStore(home).compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "os-store-reference",
                        "credential_ref": "keychain:leo-ppt-generator/openai",
                        "credential_generation": 1,
                    }
                },
            },
        )
        credential_store = MemoryStore()
        credential_store.values["openai"] = "old-secret"
        replacement = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("new-secret"),
        )
        resolver = FixedResolver(replacement)
        visible_text: list[str] = []

        ConfigWizard(
            _service(home, credential_store),
            resolver,
            menu=MenuStore([0]).menu,
            prompt=lambda text: visible_text.append(text) or "",
            confirm=lambda text, _default: visible_text.append(text) or False,
        ).run(StatusRequest())

        profile = ConfigStore(home).read().values["provider_profiles"]["openai"]
        assert profile["credential_generation"] == 2
        assert credential_store.values["openai"] == "new-secret"
        assert credential_store.writes == 1
        assert resolver.calls[0][1]["force_new_secret"] is True
        assert replacement.secret is not None and replacement.secret.closed is True
        assert "old-secret" not in "".join(visible_text)
        assert "new-secret" not in "".join(visible_text)


def test_wizard_writes_credential_from_tty_selection():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        credential_store = MemoryStore()
        service = _service(home, credential_store)
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("sk-canary"),
        )
        wizard = ConfigWizard(
            service, FixedResolver(selection), menu=MenuStore([0]).menu
        )
        result = wizard.run(StatusRequest())
        # 选择 OpenAI 后凭据写入 store；状态至少不再缺失。
        assert credential_store.values.get("openai") == "sk-canary"
        assert result.report.status.value in {"configured_unverified", "not_configured"}


def test_wizard_choose_exit_cancels_without_write():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        credential_store = MemoryStore()
        service = _service(home, credential_store)
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.UNAVAILABLE,
            reason_code="credential_input_channel_unavailable",
        )
        wizard = ConfigWizard(
            service, FixedResolver(selection), menu=MenuStore([3]).menu
        )
        with pytest.raises(WizardCancelled):
            wizard.run(StatusRequest())
        assert credential_store.values == {}


def test_wizard_unavailable_channel_reports_channel_error():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _service(home, MemoryStore())
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.UNAVAILABLE,
            reason_code="credential_input_channel_unavailable",
        )
        wizard = ConfigWizard(
            service, FixedResolver(selection), menu=MenuStore([0]).menu
        )
        # 无 TTY、无 env、无 stdin 时选择 Provider 后必须报通道不可用。
        with pytest.raises(Exception) as captured:
            wizard.run(StatusRequest())
        assert "credential_input_channel_unavailable" in str(captured.value)


def test_wizard_environment_reference_writes_complete_openai_profile():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        credential_store = MemoryStore({"OPENAI_API_KEY": "sk-env"})
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.ENVIRONMENT,
            reason_code="credential_environment_available",
            credential_ref="env:OPENAI_API_KEY",
        )
        wizard = ConfigWizard(
            _service(home, credential_store),
            FixedResolver(selection),
            menu=MenuStore([0]).menu,
        )

        result = wizard.run(StatusRequest())

        snapshot = ConfigStore(home).read()
        assert snapshot.values["selected_provider"] == "openai"
        assert snapshot.values["provider_profiles"]["openai"] == {
            "model": "gpt-image-2",
            "credential_source": "environment-reference",
            "credential_ref": "env:OPENAI_API_KEY",
            "enabled": True,
            "priority": 100,
        }
        assert credential_store.values == {}
        assert result.report.status.value == "configured_unverified"
        assert result.report.execution_eligibility.value == "allowed"


def test_wizard_tty_secret_writes_store_reference_and_closes_secret():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        credential_store = MemoryStore()
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("sk-canary"),
        )
        wizard = ConfigWizard(
            _service(home, credential_store),
            FixedResolver(selection),
            menu=MenuStore([0]).menu,
        )

        result = wizard.run(StatusRequest())

        profile = ConfigStore(home).read().values["provider_profiles"]["openai"]
        assert credential_store.values == {"openai": "sk-canary"}
        assert profile == {
            "model": "gpt-image-2",
            "credential_source": "os-store-reference",
            "credential_ref": "keychain:leo-ppt-generator/openai",
            "credential_generation": 1,
            "enabled": True,
            "priority": 100,
        }
        assert selection.secret is not None and selection.secret.closed is True
        assert result.report.status.value == "configured_unverified"


def test_wizard_openai_compatible_collects_origin_model_and_credential():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        credential_store = MemoryStore()
        selection = CredentialInputSelection(
            channel=CredentialInputChannel.TTY_GETPASS,
            reason_code="credential_input_tty",
            secret=SecretBuffer("sk-relay"),
        )
        answers = iter(("https://relay.example.com", "relay-image-model"))
        prompts: list[str] = []

        def prompt(text: str) -> str:
            prompts.append(text)
            return next(answers)

        wizard = ConfigWizard(
            _service(home, credential_store),
            FixedResolver(selection),
            menu=MenuStore([1]).menu,
            prompt=prompt,
        )

        result = wizard.run(StatusRequest())

        profile = ConfigStore(home).read().values["provider_profiles"][
            "openai-compatible"
        ]
        assert prompts == [
            "请输入中转站 HTTPS 地址（仅 origin，例如 https://api.example.com）：",
            "请输入图片模型（默认 gpt-image-2）：",
        ]
        assert profile == {
            "endpoint_origin": "https://relay.example.com",
            "model": "relay-image-model",
            "credential_source": "os-store-reference",
            "credential_ref": "keychain:leo-ppt-generator/openai-compatible",
            "credential_generation": 1,
            "enabled": True,
            "priority": 100,
        }
        assert credential_store.values == {"openai-compatible": "sk-relay"}
        assert result.report.status.value == "configured_unverified"


def test_wizard_non_tty_never_opens_menu_or_reads_input():
    class NonTTY:
        def isatty(self) -> bool:
            return False

        def read(self, *args, **kwargs):
            raise AssertionError("非交互 config 不得读取 stdin")

    with tempfile.TemporaryDirectory() as directory:
        wizard = ConfigWizard(
            _service(Path(directory), MemoryStore()),
            FixedResolver(
                CredentialInputSelection(
                    channel=CredentialInputChannel.UNAVAILABLE,
                    reason_code="credential_input_channel_unavailable",
                )
            ),
            input_stream=NonTTY(),
            menu=lambda *_: (_ for _ in ()).throw(
                AssertionError("非交互 config 不得打开菜单")
            ),
        )

        with pytest.raises(ConfigServiceError) as captured:
            wizard.run(StatusRequest())

        assert captured.value.reason_code == "credential_input_channel_unavailable"


@pytest.mark.parametrize("interruption", [EOFError(), KeyboardInterrupt()])
def test_wizard_normalizes_terminal_interruption_to_cancel(interruption):
    def interrupted_menu(*_):
        raise interruption

    with tempfile.TemporaryDirectory() as directory:
        wizard = ConfigWizard(
            _service(Path(directory), MemoryStore()),
            FixedResolver(
                CredentialInputSelection(
                    channel=CredentialInputChannel.UNAVAILABLE,
                    reason_code="credential_input_channel_unavailable",
                )
            ),
            input_stream=type("TTY", (), {"isatty": lambda self: True})(),
            menu=interrupted_menu,
        )

        with pytest.raises(WizardCancelled):
            wizard.run(StatusRequest())


def test_default_terminal_menu_enter_uses_current_provider_and_profile_defaults():
    import io

    class TTYInput(io.StringIO):
        def isatty(self) -> bool:
            return True

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_store = ConfigStore(home)
        config_store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai-compatible",
                "provider_profiles": {
                    "openai-compatible": {
                        "endpoint_origin": "https://relay.example.com",
                        "model": "relay-image-v1",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                    }
                },
            },
        )
        credential_store = MemoryStore(
            {"OPENAI_API_KEY": "environment-secret"}
        )
        output = io.StringIO()
        before = config_store.path.read_bytes()

        result = ConfigWizard(
            _service(home, credential_store),
            FixedResolver(
                CredentialInputSelection(
                    channel=CredentialInputChannel.UNAVAILABLE,
                    reason_code="credential_input_channel_unavailable",
                )
            ),
            input_stream=TTYInput("\n\n\n\n"),
            output_stream=output,
        ).run(StatusRequest())

        assert config_store.path.read_bytes() == before
        rendered = output.getvalue()
        assert "OpenAI-compatible 中转站（当前）" in rendered
        assert "请选择 (1-4，默认 2)" in rendered
        assert "当前 https://relay.example.com" in rendered
        assert "当前 relay-image-v1" in rendered
        assert "environment-secret" not in rendered
        assert result.report.status.value == "configured_unverified"
