"""统一 Provider 配置的 ConfigService 编排。

ConfigService 是 `leo-ppt config` 五个用例（status/configure/verify/repair/
change）的唯一编排 owner。它只通过 port 访问 I/O，不持有状态规则；所有
状态由 readiness 内核计算。status 类接口不访问 Provider port，保证零外部调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Sequence

from ..application.routes import ROUTE_CAPABILITY_RESOLVER
from ..credentials import CredentialInputChannel, CredentialInputSelection
from .models import (
    Capability,
    ConfigReport,
    ProviderName,
    RouteName,
)
from .provider_registry import ProviderRegistry
from .readiness import (
    ActionMaterializer,
    OperationContext,
    ProviderReadinessFacts,
    build_config_report,
)
from .reason_codes import CommandRenderer, ReasonCode, ShellKind
from .receipt_store import FileReceiptStore, ReceiptInspection
from .runtime_config import (
    ConfigStore,
    RuntimeConfig,
    RuntimeConfigError,
    validate_endpoint_origin,
)
from .transactions import ConfigTransactionCoordinator, ConfigTransactionError
from . import models as domain


class ConfigServiceError(ValueError):
    reason_code = "config_service_error"

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class StatusRequest:
    route: RouteName | str | None = None
    task_capabilities: tuple[Capability | str, ...] = ()


@dataclass(frozen=True)
class ConfigureRequest:
    provider: ProviderName | str
    credential: CredentialInputSelection
    model: str | None = None
    endpoint_origin: str | None = None
    status_request: StatusRequest = StatusRequest()
    operation_id: str = "config-wizard"
    overwrite_credential: bool = False


@dataclass(frozen=True)
class ProviderFactsInput:
    """ConfigStore 与 CredentialStore 事实到 readiness facts 的适配输入。"""

    provider: ProviderName
    configuration_state: Any
    reason_code: Any
    candidate_capabilities: frozenset[Capability]
    credential_reference_type: Any
    receipt: ReceiptInspection | None = None
    fingerprint_sha256: str | None = None
    evidence_refs: tuple[str, ...] = ()


class ConfigService:
    """组合 ConfigStore、CredentialStore、Registry 与 ReceiptStore 的编排层。"""

    def __init__(
        self,
        config_store: ConfigStore,
        credential_store: Any,
        registry: ProviderRegistry,
        receipt_store: FileReceiptStore,
        *,
        clock: Callable[[], datetime] | None = None,
        credential_reader: Callable[[ProviderName], Mapping[str, Any]] | None = None,
        action_materializer: ActionMaterializer | None = None,
        cli_path: str | None = None,
        launcher_path: str | None = None,
        launcher_args: Sequence[str] = ("ensure",),
        shell: ShellKind | str = ShellKind.POSIX,
        default_route: RouteName | str = RouteName.GENERATE,
    ) -> None:
        self.config_store = config_store
        self.credential_store = credential_store
        self.registry = registry
        self.receipt_store = receipt_store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.credential_reader = credential_reader or _default_credential_reader(
            credential_store
        )
        self.default_route = RouteName(default_route)
        if action_materializer is None:
            renderer = CommandRenderer(shell)
            if cli_path is not None or launcher_path is not None:
                self.action_materializer = lambda intent: renderer.render(
                    intent,
                    cli_path=cli_path,
                    launcher_path=launcher_path,
                    launcher_args=tuple(launcher_args),
                )
            else:
                # 未解析 CLI 时，run_cli 动作无法渲染；仍允许 report 携带
                # intent 语义（由 CLI 层注入 materializer 后渲染）。
                self.action_materializer = None
        else:
            self.action_materializer = action_materializer

    # ------------------------------------------------------------------ status
    def status(self, request: StatusRequest) -> ConfigReport:
        """只读状态：只访问 ConfigStore/CredentialStore metadata/Registry/
        ReceiptStore；绝不访问 Provider port。"""

        snapshot = self.config_store.read()
        return self._build_report(snapshot, request)

    # --------------------------------------------------------------- configure
    def configure(self, request: ConfigureRequest) -> ConfigReport:
        """原子保存 Provider profile 与凭据引用，不发起 Provider 调用。"""

        try:
            provider = ProviderName(request.provider)
        except ValueError as exc:
            raise ConfigServiceError("unknown_provider") from exc

        endpoint_origin: str | None = None
        if provider is ProviderName.OPENAI_COMPATIBLE:
            endpoint_origin = validate_endpoint_origin(request.endpoint_origin)
        elif request.endpoint_origin is not None:
            raise ConfigServiceError("provider_profile_invalid:endpoint_origin")

        definition = self.registry.provider(provider, endpoint_origin)
        model = (request.model or definition.default_model).strip()
        if not model:
            raise ConfigServiceError("provider_profile_invalid:model")

        selection = request.credential
        snapshot = self.config_store.read()
        previous = snapshot.values.get("provider_profiles", {}).get(
            provider.value, {}
        )
        profile: dict[str, Any] = {"model": model}
        if endpoint_origin is not None:
            profile["endpoint_origin"] = endpoint_origin

        secret = None
        try:
            if selection.channel is CredentialInputChannel.ENVIRONMENT:
                profile.update(
                    credential_source="environment-reference",
                    credential_ref=selection.credential_ref,
                )
                fingerprint_key = self.credential_store.fingerprint_key(create=True)
                if fingerprint_key is not None:
                    fingerprint_key.close()
            elif selection.channel is CredentialInputChannel.EXISTING_STORE:
                reference = selection.credential_ref
                generation = 1
                if (
                    previous.get("credential_source") == "os-store-reference"
                    and previous.get("credential_ref") == reference
                ):
                    generation = int(previous.get("credential_generation", 1))
                profile.update(
                    credential_source="os-store-reference",
                    credential_ref=reference,
                    credential_generation=generation,
                )
            elif selection.channel in {
                CredentialInputChannel.TTY_GETPASS,
                CredentialInputChannel.EXPLICIT_STDIN,
            }:
                reference = self.credential_store.reference(provider.value)
                generation = 1
                if previous.get("credential_source") == "os-store-reference":
                    generation = int(previous.get("credential_generation", 0)) + 1
                profile.update(
                    credential_source="os-store-reference",
                    credential_ref=reference,
                    credential_generation=generation,
                )
                secret = selection.secret
            else:
                raise ConfigServiceError("credential_input_channel_unavailable")

            if not profile.get("credential_ref"):
                raise ConfigServiceError("credential_input_channel_unavailable")
            try:
                committed = ConfigTransactionCoordinator(
                    self.config_store,
                    self.credential_store,
                    self.receipt_store,
                ).configure(
                    provider=provider,
                    profile=profile,
                    operation_id=request.operation_id,
                    secret=secret,
                    allow_credential_overwrite=request.overwrite_credential,
                )
            except ConfigTransactionError as error:
                raise ConfigServiceError(error.reason_code) from error
        finally:
            selection.close()

        return self._build_report(committed, request.status_request)

    # ------------------------------------------------------------------ verify
    def verify(
        self,
        request: StatusRequest,
        *,
        operation_context: OperationContext | None = None,
    ) -> ConfigReport:
        """显式验证入口（smoke 由外层 executor 执行后合并 evidence）。

        本方法不发起 Provider 调用；它只基于当前事实生成 report。付费
        smoke 的执行与 evidence 合并由 VerificationCoordinator owner 承担，
        ConfigService 不持有 Provider 调用能力。
        """

        snapshot = self.config_store.read()
        return self._build_report(snapshot, request, operation_context)

    def change(
        self,
        request: StatusRequest,
        *,
        selected_provider: ProviderName | str,
        operation_id: str,
    ) -> ConfigReport:
        """切换当前 Provider；候选本地配置成功后原子提交。

        切换前保留原 ready Provider 与 credential reference；CAS 失败
        不破坏原选择。本方法只更新非敏感 profile 与 selected_provider，
        凭据写入由事务 owner 负责。
        """

        provider = ProviderName(selected_provider)
        snapshot = self.config_store.read()
        profiles = snapshot.values.get("provider_profiles", {})
        if provider.value not in profiles:
            raise ConfigServiceError("provider_profile_invalid")
        candidate = dict(snapshot.document)
        candidate["selected_provider"] = provider.value
        try:
            self.config_store.compare_and_swap(
                snapshot.canonical_digest, candidate
            )
        except RuntimeConfigError as error:
            # 保留原 Provider，但命令本身必须明确失败，不能把旧 ready 状态
            # 伪装成切换成功并以 0 退出。
            raise ConfigServiceError(error.reason_code) from error
        return self._build_report(self.config_store.read(), request)

    def repair(self, request: StatusRequest) -> ConfigReport:
        """从 Reason catalog 的最早未完成步骤续接配置。

        本方法只基于当前事实重新计算状态；凭据/档案的原子写入由
        事务 owner（wizard/CLI）执行，service 不猜测中间步骤。
        """

        snapshot = self.config_store.read()
        report = self._build_report(snapshot, request)
        return report

    # ------------------------------------------------------- internal helpers
    def _build_report(
        self,
        snapshot: RuntimeConfig,
        request: StatusRequest,
        operation_context: OperationContext | None = None,
    ) -> ConfigReport:
        facts = self._provider_facts(snapshot)
        selected = snapshot.values.get("selected_provider")
        selected_name = (
            ProviderName(selected)
            if isinstance(selected, str) and selected
            else None
        )
        if selected_name is not None and selected_name not in {
            item.provider for item in facts
        }:
            raise ConfigServiceError("provider_selection_invalid")
        return build_config_report(
            facts,
            selected_provider=selected_name,
            route=request.route or self.default_route,
            task_capabilities=request.task_capabilities,
            operation_context=operation_context,
            action_materializer=self.action_materializer,
        )
    def _provider_facts(
        self, snapshot: RuntimeConfig
    ) -> tuple[ProviderReadinessFacts, ...]:
        profiles: Mapping[str, Any] = snapshot.values.get(
            "provider_profiles", {}
        )
        result: list[ProviderReadinessFacts] = []
        for name, profile in sorted(profiles.items()):
            try:
                provider = ProviderName(name)
            except ValueError as exc:
                raise ConfigServiceError("unknown_provider") from exc
            if provider is ProviderName.BUILTIN_IMAGEGEN:
                # Host Provider 不持久化于 config.yaml。
                continue
            credential = self._credential_for_profile(provider, profile)
            candidate = self.registry.provider(
                provider,
                profile.get("endpoint_origin"),
            )
            fingerprint = self._fingerprint_for(provider, profile, credential)
            receipt = self._inspect_receipt(
                provider, profile, credential, fingerprint
            )
            configuration = self._configuration_state(
                snapshot, provider, profile, credential
            )
            reference_type = credential.get(
                "reference_type", "none"
            )
            reason_code = _normalize_reason_code(
                credential.get("reason_code", "provider_verification_not_run")
            )
            # env 引用的运行时缺失：以 credential_environment_missing 表达，
            # 不误报为 schema invalid，也不阻断其他兼容 Provider。
            if (
                profile.get("credential_source") == "environment-reference"
                and credential.get("status") != "available"
            ):
                reason_code = ReasonCode.CREDENTIAL_ENVIRONMENT_MISSING
            result.append(
                ProviderReadinessFacts(
                    provider=provider,
                    configuration_state=configuration,
                    reason_code=reason_code,
                    candidate_capabilities=candidate.supported_capabilities,
                    credential_reference_type=reference_type,
                    receipt=receipt,
                    fingerprint_sha256=(
                        fingerprint.sha256 if fingerprint is not None else None
                    ),
                )
            )
        return tuple(result)

    def _credential_for_profile(
        self,
        provider: ProviderName,
        profile: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """只接受 profile 明确引用的凭据来源，不跨 channel 自动替代。"""

        expected_source = profile.get("credential_source")
        expected_reference = profile.get("credential_ref")
        if expected_source == "environment-reference":
            facts = dict(self.credential_reader(provider))
            if (
                facts.get("status") == "available"
                and facts.get("reference_type") == "environment-reference"
                and facts.get("credential_ref") == expected_reference
            ):
                return facts
            return {
                "status": "missing",
                "reason_code": "credential_environment_missing",
                "reference_type": "none",
                "credential_ref": None,
            }

        try:
            status = self.credential_store.status(provider.value)
        except Exception:
            status = "missing"
        if isinstance(status, Mapping):
            available = status.get("status") == "available"
            reference = status.get("credential_ref")
            reference_type = status.get("reference_type")
        else:
            available = status == "available"
            reference = (
                self.credential_store.reference(provider.value)
                if available
                else None
            )
            reference_type = "os-store-reference" if available else "none"
        if (
            available
            and reference_type == "os-store-reference"
            and reference == expected_reference
        ):
            return {
                "status": "available",
                "reason_code": "credential_store_available",
                "reference_type": "os-store-reference",
                "credential_ref": reference,
            }
        return {
            "status": "missing",
            "reason_code": "credential_missing",
            "reference_type": "none",
            "credential_ref": None,
        }

    def _inspect_receipt(
        self,
        provider: ProviderName,
        profile: Mapping[str, Any],
        credential: Mapping[str, Any],
        fingerprint,
    ) -> ReceiptInspection | None:
        if (
            not profile
            or not credential.get("credential_ref")
            or fingerprint is None
        ):
            return None
        return self.receipt_store.inspect(
            provider, fingerprint, self.clock()
        )

    def _fingerprint_for(
        self,
        provider: ProviderName,
        profile: Mapping[str, Any],
        credential: Mapping[str, Any],
    ):
        from .receipt_store import fingerprint_from_registry

        source = profile.get("credential_source")
        if source == "os-store-reference":
            credential_version = f"generation:{profile.get('credential_generation', 1)}"
        else:
            # env 引用必须绑定实际 secret 的 keyed HMAC；版本不可解析时
            # 保持 configured_unverified，绝不使用可长期命中的固定 sentinel。
            credential_version = credential.get("credential_version")
            if not credential_version:
                return None
        return fingerprint_from_registry(
            self.registry,
            provider=provider,
            endpoint_origin=profile.get("endpoint_origin"),
            model=profile.get("model"),
            credential_version=credential_version,
            runtime_identity=_runtime_identity(),
        )

    @staticmethod
    def _configuration_state(
        snapshot: RuntimeConfig,
        provider: ProviderName,
        profile: Mapping[str, Any],
        credential: Mapping[str, Any],
    ):
        if snapshot.validation_issues:
            fatal = any(
                issue.fatal and (issue.provider is None or issue.provider == provider.value)
                for issue in snapshot.validation_issues
            )
            if fatal:
                return domain.ConfigurationState.INVALID
        if not profile:
            return domain.ConfigurationState.NOT_CONFIGURED
        # env 引用的运行时缺失由 CredentialStore 判定（每次读取基于当前
        # 进程环境），config 文件本身不携带 env 值，持久化 issue 不决定状态。
        if credential.get("status") != "available":
            return domain.ConfigurationState.NOT_CONFIGURED
        return domain.ConfigurationState.LOCALLY_CONFIGURED


def _normalize_reason_code(value: Any) -> ReasonCode:
    """把任意来源的 reason 字符串归一化为 ReasonCode；未知值不猜测。"""

    try:
        return ReasonCode(value)
    except (TypeError, ValueError):
        return ReasonCode.PROVIDER_VERIFICATION_NOT_RUN


def _runtime_identity() -> str:
    import leo_ppt_generator

    try:
        return f"leo-ppt-generator/{leo_ppt_generator.__version__}"
    except AttributeError:
        return "leo-ppt-generator/0.1.0"


def _default_credential_reader(credential_store: Any):
    """把 CredentialStore 包装为只读 credential 事实读取器。"""

    def reader(provider: ProviderName) -> dict[str, Any]:
        try:
            report = credential_store.status(provider.value)
        except Exception:
            return {"status": "missing", "reason_code": "credential_missing"}
        if isinstance(report, dict) and report.get("status") == "available":
            return {
                "status": "available",
                "reference_type": report.get(
                    "reference_type", "os-store-reference"
                ),
                "credential_ref": report.get("credential_ref"),
                "credential_version": report.get("credential_version"),
                "reason_code": report.get("reason_code", "credential_store_available"),
            }
        if isinstance(report, str) and report == "available":
            return {
                "status": "available",
                "reference_type": "os-store-reference",
                "credential_ref": credential_store.reference(provider.value),
                "reason_code": "credential_store_available",
            }
        return {"status": "missing", "reason_code": "credential_missing"}

    return reader


__all__ = [
    "ConfigureRequest",
    "ConfigService",
    "ConfigServiceError",
    "ProviderFactsInput",
    "StatusRequest",
]
