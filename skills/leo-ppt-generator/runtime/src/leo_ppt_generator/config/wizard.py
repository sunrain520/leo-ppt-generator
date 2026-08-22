"""`leo-ppt config` 的交互式向导。

ConfigWizard 只负责 TTY 提问、已有配置预填、安全取消与提交分流；
不直接写文件。所有持久化与状态计算由 ConfigService 承担。
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from ..credentials import (
    CredentialError,
    CredentialInputChannel,
    CredentialInputResolver,
    CredentialInputSelection,
)
from .models import ConfigReport, ProviderName
from .runtime_config import RuntimeConfigError, validate_endpoint_origin
from .service import (
    ConfigureRequest,
    ConfigService,
    ConfigServiceError,
    StatusRequest,
)


class WizardCancelled(Exception):
    reason_code = "wizard_cancelled"


@dataclass(frozen=True)
class WizardResult:
    report: ConfigReport
    cancelled: bool = False


class ConfigWizard:
    """终端配置向导；所有提示默认安全（不默认同意付费、不默认覆盖）。"""

    def __init__(
        self,
        service: ConfigService,
        resolver: CredentialInputResolver,
        *,
        input_stream=None,
        output_stream=None,
        prompt: Callable[[str], str] | None = None,
        confirm: Callable[[str, bool], bool] | None = None,
        menu: Callable[[Sequence[str], str], int | None] | None = None,
        key_stdin: bool = False,
        fixed_provider: ProviderName | str | None = None,
    ) -> None:
        self.service = service
        self.resolver = resolver
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.key_stdin = key_stdin
        self.fixed_provider = (
            ProviderName(fixed_provider) if fixed_provider is not None else None
        )
        self._menu_injected = menu is not None
        self.prompt = prompt or self._default_prompt
        self.confirm = confirm or self._default_confirm
        self.menu = menu or self._default_menu

    def run(self, request: StatusRequest | None = None) -> WizardResult:
        """执行向导；交互调用始终允许检查并编辑已有配置。"""

        status_request = request or StatusRequest()
        if not self._has_interactive_input():
            # 安装器等非交互调用仍可安全读取已有状态，但不得尝试打开向导。
            report = self.service.status(status_request)
            if report.status.value in {"ready", "configured_unverified"}:
                return WizardResult(report=report)
            raise ConfigServiceError("credential_input_channel_unavailable")
        try:
            return self._configure(status_request)
        except (EOFError, KeyboardInterrupt):
            raise WizardCancelled() from None

    def _configure(self, request: StatusRequest) -> WizardResult:
        snapshot = self.service.config_store.read()
        profiles = snapshot.values.get("provider_profiles", {})
        selected = snapshot.values.get("selected_provider")
        current_provider = ProviderName(selected) if isinstance(selected, str) else None

        provider = self._choose_provider(current_provider)
        if provider is None:
            raise WizardCancelled()

        existing_profile = profiles.get(provider.value)
        endpoint_origin, model = self._profile_inputs(provider, existing_profile)
        selection, credential_kept = self._credential_selection(
            provider, existing_profile
        )
        operation_id = f"config-wizard-{provider.value}-{uuid.uuid4().hex}"
        changed = True
        try:
            if selection.credential_ref is None and selection.secret is None:
                raise ConfigServiceError("credential_input_channel_unavailable")

            profile_unchanged = self._profile_unchanged(
                provider,
                existing_profile,
                endpoint_origin=endpoint_origin,
                model=model,
            )
            if existing_profile is not None and credential_kept and profile_unchanged:
                if provider is current_provider:
                    changed = False
                    report = self.service.status(request)
                else:
                    report = self.service.change(
                        request,
                        selected_provider=provider,
                        operation_id=operation_id,
                    )
            else:
                report = self.service.configure(
                    ConfigureRequest(
                        provider=provider,
                        credential=selection,
                        endpoint_origin=endpoint_origin,
                        model=model,
                        status_request=request,
                        operation_id=operation_id,
                        overwrite_credential=(
                            existing_profile is not None and not credential_kept
                        ),
                    )
                )
        finally:
            # ConfigService 也在边界关闭 secret；这里保持适配层异常路径同样清零。
            selection.close()

        if not changed:
            self._write("配置未修改，已保留当前设置。")
        elif report.status.value in {"ready", "configured_unverified"}:
            self._write("配置完成，可以开始使用；首次生成图片时验证服务。")
        return WizardResult(report=report)

    def _profile_inputs(
        self,
        provider: ProviderName,
        existing_profile: Mapping[str, object] | None,
    ) -> tuple[str | None, str]:
        endpoint_origin: str | None = None
        current_origin = (
            str(existing_profile.get("endpoint_origin"))
            if existing_profile is not None
            and existing_profile.get("endpoint_origin")
            else None
        )
        if provider is ProviderName.OPENAI_COMPATIBLE:
            while endpoint_origin is None:
                if current_origin is not None:
                    raw = self.prompt(
                        "请输入中转站 HTTPS 地址"
                        f"（当前 {current_origin}，回车保留）："
                    ).strip()
                    candidate = raw or current_origin
                else:
                    candidate = self.prompt(
                        "请输入中转站 HTTPS 地址（仅 origin，例如 https://api.example.com）："
                    ).strip()
                try:
                    endpoint_origin = validate_endpoint_origin(candidate)
                except RuntimeConfigError:
                    self._write(
                        "地址无效：请输入不含路径、用户名、查询串或片段的 HTTPS 地址。"
                    )

        definition = self.service.registry.provider(provider, endpoint_origin)
        current_model = (
            str(existing_profile.get("model"))
            if existing_profile is not None and existing_profile.get("model")
            else definition.default_model
        )
        model = current_model
        if existing_profile is not None:
            entered = self.prompt(
                f"请输入图片模型（当前 {current_model}，回车保留）："
            ).strip()
            if entered:
                model = entered
        elif provider is ProviderName.OPENAI_COMPATIBLE:
            entered = self.prompt(
                f"请输入图片模型（默认 {definition.default_model}）："
            ).strip()
            if entered:
                model = entered
        return endpoint_origin, model

    def _choose_provider(
        self, current_provider: ProviderName | None
    ) -> ProviderName | None:
        providers = (
            ProviderName.OPENAI,
            ProviderName.OPENAI_COMPATIBLE,
            ProviderName.ATLASCLOUD,
        )
        labels = ["OpenAI", "OpenAI-compatible 中转站", "AtlasCloud"]
        if self.fixed_provider is not None:
            if self.fixed_provider not in providers:
                raise ConfigServiceError("unknown_provider")
            return self.fixed_provider
        default_index: int | None = None
        if current_provider in providers:
            default_index = providers.index(current_provider)
            labels[default_index] += "（当前）"
        choices = (*labels, "退出")
        if self._menu_injected:
            index = self.menu(choices, "选择图片服务 Provider")
        else:
            index = self._default_menu(
                choices,
                "选择图片服务 Provider",
                default_index=default_index,
            )
        if index is None or index >= len(providers):
            return None
        return providers[index]

    def _credential_selection(
        self,
        provider: ProviderName,
        existing_profile: Mapping[str, object] | None,
    ) -> tuple[CredentialInputSelection, bool]:
        if existing_profile is not None:
            source = str(existing_profile.get("credential_source", ""))
            reference = str(existing_profile.get("credential_ref", ""))
            if self.confirm(
                f"当前凭据：{source} {reference}。是否保留？",
                True,
            ):
                return self._preserved_credential(source, reference), True
            return self._resolve_credential(provider, force_new_secret=True), False
        return self._resolve_credential(provider), False

    @staticmethod
    def _preserved_credential(
        source: str, reference: str
    ) -> CredentialInputSelection:
        if source == "environment-reference":
            channel = CredentialInputChannel.ENVIRONMENT
            reason_code = "credential_environment_reference_preserved"
        elif source == "os-store-reference":
            channel = CredentialInputChannel.EXISTING_STORE
            reason_code = "credential_store_reference_preserved"
        else:
            raise ConfigServiceError("provider_profile_invalid")
        return CredentialInputSelection(
            channel=channel,
            reason_code=reason_code,
            credential_ref=reference,
        )

    @staticmethod
    def _profile_unchanged(
        provider: ProviderName,
        existing_profile: Mapping[str, object] | None,
        *,
        endpoint_origin: str | None,
        model: str,
    ) -> bool:
        if existing_profile is None or existing_profile.get("model") != model:
            return False
        if provider is ProviderName.OPENAI_COMPATIBLE:
            return existing_profile.get("endpoint_origin") == endpoint_origin
        return True

    def _resolve_credential(
        self,
        provider: ProviderName,
        *,
        force_new_secret: bool = False,
    ) -> CredentialInputSelection:
        try:
            return self.resolver.select(
                provider.value,
                key_stdin=self.key_stdin,
                input_stream=self.input_stream,
                tty_stream=self.input_stream,
                force_new_secret=force_new_secret,
            )
        except CredentialError as error:
            raise ConfigServiceError(str(error)) from error

    def _has_interactive_input(self) -> bool:
        if self.input_stream is not None:
            return _is_tty(self.input_stream)
        # 注入 menu 的测试/宿主已显式承担交互；生产默认菜单仍要求真实 TTY。
        return self._menu_injected or _is_tty(sys.stdin)

    def _read_line(self, text: str) -> str:
        stream = self.input_stream or sys.stdin
        output = self.output_stream or sys.stdout
        print(text, end="", file=output, flush=True)
        value = stream.readline()
        if value == "":
            raise EOFError
        return value.rstrip("\r\n")

    def _default_prompt(self, text: str) -> str:
        return self._read_line(text)

    def _default_confirm(self, text: str, default: bool) -> bool:
        suffix = " [Y/n]" if default else " [y/N]"
        raw = self._read_line(f"{text}{suffix} ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes"}

    def _default_menu(
        self,
        choices: Sequence[str],
        title: str,
        *,
        default_index: int | None = None,
    ) -> int | None:
        self._write(title)
        for index, choice in enumerate(choices, start=1):
            self._write(f"  {index}. {choice}")
        default_text = (
            f"，默认 {default_index + 1}" if default_index is not None else ""
        )
        raw = self._read_line(
            f"请选择 (1-{len(choices)}{default_text}): "
        ).strip()
        if not raw and default_index is not None:
            return default_index
        try:
            value = int(raw)
        except ValueError:
            return None
        if value < 1 or value > len(choices):
            return None
        return value - 1

    def _write(self, text: str) -> None:
        print(text, file=self.output_stream or sys.stdout)


def _is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


__all__ = ["ConfigWizard", "WizardCancelled", "WizardResult"]
