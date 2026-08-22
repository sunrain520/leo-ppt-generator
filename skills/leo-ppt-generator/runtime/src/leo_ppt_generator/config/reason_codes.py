"""稳定原因码、默认恢复动作与跨 shell 命令渲染。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Mapping, Sequence

from .models import PrimaryAction, PrimaryActionKind


class ConfigStage(StrEnum):
    STATUS = "status"
    CONFIGURE = "configure"
    CREDENTIAL = "credential"
    PROFILE = "profile"
    VERIFY = "verify"
    RECEIPT = "receipt"
    TRANSACTION = "transaction"
    ONBOARDING = "onboarding"
    HOST_GUARD = "host_guard"


class RecoveryCategory(StrEnum):
    NONE = "none"
    CONFIGURE = "configure"
    REPAIR = "repair"
    CHANGE_PROVIDER = "change_provider"
    RETRY = "retry"
    CONFIRM_NEW_REQUEST = "confirm_new_request"
    START_TASK = "start_task"
    RESUME_TASK = "resume_task"
    HOST_FALLBACK = "host_fallback"


class ConfigCommandVerb(StrEnum):
    CONFIG = "config"
    VERIFY = "verify"
    REPAIR = "repair"
    CHANGE = "change"


class ShellKind(StrEnum):
    POSIX = "posix"
    POWERSHELL = "powershell"


class ReasonCode(StrEnum):
    CONFIGURATION_READY = "configuration_ready"
    PROVIDER_VERIFICATION_NOT_RUN = "provider_verification_not_run"
    PROVIDER_VERIFICATION_STALE = "provider_verification_stale"
    CONFIG_INVALID = "config_invalid"
    CONFIG_SCHEMA_TOO_NEW = "config_schema_too_new"
    DEVELOPMENT_CONFIG_RESET_REQUIRED = "development_config_reset_required"
    UNKNOWN_SENSITIVE_FIELD = "unknown_sensitive_field"
    PROVIDER_SELECTION_REQUIRED = "provider_selection_required"
    PROVIDER_PROFILE_INVALID = "provider_profile_invalid"
    PROVIDER_PROFILE_INVALID_ENDPOINT_ORIGIN = "provider_profile_invalid:endpoint_origin"
    PROVIDER_PROFILE_INVALID_MODEL = "provider_profile_invalid:model"
    CREDENTIAL_INPUT_CHANNEL_UNAVAILABLE = "credential_input_channel_unavailable"
    CREDENTIAL_EMPTY = "credential_empty"
    CREDENTIAL_OVERWRITE_CONFIRMATION_REQUIRED = "credential_overwrite_confirmation_required"
    CREDENTIAL_STORE_UNSUPPORTED = "credential_store_unsupported"
    CREDENTIAL_STORE_LOCKED = "credential_store_locked"
    CREDENTIAL_STORE_DENIED = "credential_store_denied"
    CREDENTIAL_BLOB_INVALID = "credential_blob_invalid"
    CREDENTIAL_STORE_ACL_TOO_BROAD = "credential_store_acl_too_broad"
    CREDENTIAL_ENVIRONMENT_MISSING = "credential_environment_missing"
    PROVIDER_AUTHENTICATION_FAILED = "provider_authentication_failed"
    PROVIDER_PERMISSION_DENIED = "provider_permission_denied"
    PROVIDER_ENDPOINT_NOT_FOUND = "provider_endpoint_not_found"
    PROVIDER_MODEL_NOT_FOUND = "provider_model_not_found"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    PROVIDER_NETWORK_ERROR = "provider_network_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_OUTCOME_UNKNOWN = "provider_outcome_unknown"
    PROVIDER_ARTIFACT_EMPTY = "provider_artifact_empty"
    PROVIDER_ARTIFACT_UNREADABLE = "provider_artifact_unreadable"
    PROVIDER_ARTIFACT_MEDIA_TYPE_UNSUPPORTED = "provider_artifact_media_type_unsupported"
    VERIFICATION_RECEIPT_INVALID = "verification_receipt_invalid"
    VERIFICATION_EVIDENCE_PERSIST_FAILED = "verification_evidence_persist_failed"
    CREDENTIAL_TRANSACTION_INCONSISTENT = "credential_transaction_inconsistent"
    CONFIG_WRITE_FAILED = "config_write_failed"
    CLI_PATH_UNRESOLVED = "cli_path_unresolved"
    CONFIG_PROTOCOL_INVALID = "config_protocol_invalid"
    CONFIG_CHECK_UNAVAILABLE = "config_check_unavailable"
    HOST_CHECK_REQUIRED = "host_check_required"
    HOST_IMAGE_CAPABILITY_UNAVAILABLE = "host_image_capability_unavailable"
    HOST_RECHECK_ALLOWED = "host_recheck_allowed"


@dataclass(frozen=True, slots=True)
class ActionIntent:
    kind: PrimaryActionKind
    reason_code: ReasonCode
    command_verb: ConfigCommandVerb | None = None
    resume_ref: str | None = None

    def __post_init__(self) -> None:
        if self.kind is PrimaryActionKind.RUN_CLI:
            unresolved = self.reason_code is ReasonCode.CLI_PATH_UNRESOLVED
            if unresolved and self.command_verb is not None:
                raise ValueError("cli_path_unresolved must not invent a CLI command")
            if not unresolved and self.command_verb is None:
                raise ValueError("run_cli action requires a config command verb")
        elif self.command_verb is not None:
            raise ValueError("only run_cli action may contain a command verb")
        if self.resume_ref is not None and self.kind is not PrimaryActionKind.RESUME_TASK:
            raise ValueError("only resume_task action may contain resume_ref")
        if self.resume_ref is not None and not self.resume_ref.strip():
            raise ValueError("resume_ref must not be empty")


@dataclass(frozen=True, slots=True)
class ReasonDefinition:
    code: ReasonCode
    stage: ConfigStage
    recovery_category: RecoveryCategory
    default_action: ActionIntent | None
    user_repairable: bool

    def __post_init__(self) -> None:
        if self.default_action is not None and self.default_action.reason_code is not self.code:
            raise ValueError("default action reason_code must match its catalog entry")
        if self.user_repairable and self.default_action is None:
            raise ValueError("user-repairable reasons require one default action")

def _intent(
    code: ReasonCode,
    kind: PrimaryActionKind,
    verb: ConfigCommandVerb | None = None,
) -> ActionIntent:
    return ActionIntent(kind=kind, reason_code=code, command_verb=verb)


def _definition(
    code: ReasonCode,
    stage: ConfigStage,
    category: RecoveryCategory,
    kind: PrimaryActionKind | None = None,
    verb: ConfigCommandVerb | None = None,
    *,
    user_repairable: bool = True,
) -> ReasonDefinition:
    action = _intent(code, kind, verb) if kind is not None else None
    return ReasonDefinition(code, stage, category, action, user_repairable)


_RUN = PrimaryActionKind.RUN_CLI
_WAIT = PrimaryActionKind.WAIT_AND_RETRY
_CONFIRM = PrimaryActionKind.CONFIRM_NEW_REQUEST
_START = PrimaryActionKind.START_TASK
_RESUME = PrimaryActionKind.RESUME_TASK
_REPAIR = ConfigCommandVerb.REPAIR
_CONFIG = ConfigCommandVerb.CONFIG
_CHANGE = ConfigCommandVerb.CHANGE
_VERIFY = ConfigCommandVerb.VERIFY

_REASON_DEFINITIONS = (
    _definition(ReasonCode.CONFIGURATION_READY, ConfigStage.STATUS, RecoveryCategory.START_TASK, _START, user_repairable=False),
    _definition(ReasonCode.PROVIDER_VERIFICATION_NOT_RUN, ConfigStage.STATUS, RecoveryCategory.START_TASK, _START, user_repairable=False),
    _definition(ReasonCode.PROVIDER_VERIFICATION_STALE, ConfigStage.STATUS, RecoveryCategory.START_TASK, _START, user_repairable=False),
    _definition(ReasonCode.CONFIG_INVALID, ConfigStage.STATUS, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CONFIG_SCHEMA_TOO_NEW, ConfigStage.STATUS, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.DEVELOPMENT_CONFIG_RESET_REQUIRED, ConfigStage.STATUS, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.UNKNOWN_SENSITIVE_FIELD, ConfigStage.STATUS, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_SELECTION_REQUIRED, ConfigStage.PROFILE, RecoveryCategory.CONFIGURE, _RUN, _CONFIG),
    _definition(ReasonCode.PROVIDER_PROFILE_INVALID, ConfigStage.PROFILE, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_PROFILE_INVALID_ENDPOINT_ORIGIN, ConfigStage.PROFILE, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_PROFILE_INVALID_MODEL, ConfigStage.PROFILE, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_INPUT_CHANNEL_UNAVAILABLE, ConfigStage.CREDENTIAL, RecoveryCategory.CONFIGURE, _RUN, _CONFIG),
    _definition(ReasonCode.CREDENTIAL_EMPTY, ConfigStage.CREDENTIAL, RecoveryCategory.CONFIGURE, _RUN, _CONFIG),
    _definition(ReasonCode.CREDENTIAL_OVERWRITE_CONFIRMATION_REQUIRED, ConfigStage.CREDENTIAL, RecoveryCategory.CONFIGURE, _RUN, _CONFIG),
    _definition(ReasonCode.CREDENTIAL_STORE_UNSUPPORTED, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_STORE_LOCKED, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_STORE_DENIED, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_BLOB_INVALID, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_STORE_ACL_TOO_BROAD, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_ENVIRONMENT_MISSING, ConfigStage.CREDENTIAL, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_AUTHENTICATION_FAILED, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_PERMISSION_DENIED, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_ENDPOINT_NOT_FOUND, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_MODEL_NOT_FOUND, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_RATE_LIMITED, ConfigStage.VERIFY, RecoveryCategory.RETRY, _WAIT),
    _definition(ReasonCode.PROVIDER_SERVER_ERROR, ConfigStage.VERIFY, RecoveryCategory.RETRY, _WAIT),
    _definition(ReasonCode.PROVIDER_NETWORK_ERROR, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_TIMEOUT, ConfigStage.VERIFY, RecoveryCategory.RETRY, _WAIT),
    _definition(ReasonCode.PROVIDER_OUTCOME_UNKNOWN, ConfigStage.VERIFY, RecoveryCategory.CONFIRM_NEW_REQUEST, _CONFIRM),
    _definition(ReasonCode.PROVIDER_ARTIFACT_EMPTY, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _VERIFY),
    _definition(ReasonCode.PROVIDER_ARTIFACT_UNREADABLE, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.PROVIDER_ARTIFACT_MEDIA_TYPE_UNSUPPORTED, ConfigStage.VERIFY, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.VERIFICATION_RECEIPT_INVALID, ConfigStage.RECEIPT, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.VERIFICATION_EVIDENCE_PERSIST_FAILED, ConfigStage.RECEIPT, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CREDENTIAL_TRANSACTION_INCONSISTENT, ConfigStage.TRANSACTION, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CONFIG_WRITE_FAILED, ConfigStage.TRANSACTION, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CLI_PATH_UNRESOLVED, ConfigStage.ONBOARDING, RecoveryCategory.REPAIR, _RUN),
    _definition(ReasonCode.CONFIG_PROTOCOL_INVALID, ConfigStage.ONBOARDING, RecoveryCategory.REPAIR, _RUN, _REPAIR),
    _definition(ReasonCode.CONFIG_CHECK_UNAVAILABLE, ConfigStage.ONBOARDING, RecoveryCategory.RETRY, _WAIT),
    _definition(ReasonCode.HOST_CHECK_REQUIRED, ConfigStage.HOST_GUARD, RecoveryCategory.HOST_FALLBACK, user_repairable=False),
    _definition(ReasonCode.HOST_IMAGE_CAPABILITY_UNAVAILABLE, ConfigStage.HOST_GUARD, RecoveryCategory.CONFIGURE, _RUN, _CONFIG),
    _definition(ReasonCode.HOST_RECHECK_ALLOWED, ConfigStage.HOST_GUARD, RecoveryCategory.RESUME_TASK, _RESUME, user_repairable=False),
)

if len({item.code for item in _REASON_DEFINITIONS}) != len(_REASON_DEFINITIONS):
    raise RuntimeError("reason catalog contains duplicate reason codes")
if {item.code for item in _REASON_DEFINITIONS} != set(ReasonCode):
    raise RuntimeError("reason catalog must define every stable reason code")

REASON_CATALOG: Mapping[ReasonCode, ReasonDefinition] = MappingProxyType(
    {item.code: item for item in _REASON_DEFINITIONS}
)


def reason_definition(reason_code: ReasonCode | str) -> ReasonDefinition:
    """返回原因码的唯一合同；未知输入不会被猜测为相近原因。"""

    return REASON_CATALOG[ReasonCode(reason_code)]


_COMMAND_ARGUMENTS: Mapping[ConfigCommandVerb, tuple[str, ...]] = MappingProxyType(
    {
        ConfigCommandVerb.CONFIG: ("config",),
        ConfigCommandVerb.VERIFY: ("config", "verify"),
        ConfigCommandVerb.REPAIR: ("config", "repair"),
        ConfigCommandVerb.CHANGE: ("config", "change"),
    }
)

class CommandRenderer:
    """把 typed action 渲染为当前 shell 可直接执行的命令。"""

    def __init__(self, shell: ShellKind) -> None:
        self.shell = ShellKind(shell)

    def render(
        self,
        intent: ActionIntent | None,
        *,
        cli_path: str | None = None,
        launcher_path: str | None = None,
        launcher_args: Sequence[str] = ("ensure",),
    ) -> PrimaryAction | None:
        if intent is None:
            return None
        if intent.kind is not PrimaryActionKind.RUN_CLI:
            return PrimaryAction(kind=intent.kind, resume_ref=intent.resume_ref)

        if intent.reason_code is ReasonCode.CLI_PATH_UNRESOLVED:
            if cli_path is not None:
                raise ValueError("cli_path_unresolved must not use or invent a CLI path")
            executable = self._absolute_path(launcher_path, "launcher_path")
            arguments = self._arguments(launcher_args, "launcher_args")
            if not arguments:
                raise ValueError("launcher repair command requires arguments")
        else:
            if launcher_path is not None:
                raise ValueError("resolved CLI actions must not use a launcher path")
            executable = self._absolute_path(cli_path, "cli_path")
            if intent.command_verb is None:  # pragma: no cover - ActionIntent 已保证
                raise ValueError("run_cli action requires a config command verb")
            arguments = _COMMAND_ARGUMENTS[intent.command_verb]

        command = self._render_command(executable, arguments)
        return PrimaryAction(
            kind=PrimaryActionKind.RUN_CLI,
            command=command,
            resume_ref=intent.resume_ref,
        )

    def render_prefixed(
        self,
        intent: ActionIntent | None,
        *,
        executable: str,
        prefix_arguments: Sequence[str] = (),
    ) -> PrimaryAction | None:
        """用显式启动器前缀渲染已知可执行的模块入口。"""

        if intent is None:
            return None
        if intent.kind is not PrimaryActionKind.RUN_CLI:
            return PrimaryAction(kind=intent.kind, resume_ref=intent.resume_ref)
        if intent.reason_code is ReasonCode.CLI_PATH_UNRESOLVED:
            raise ValueError("cli_path_unresolved requires a launcher repair command")
        if intent.command_verb is None:  # pragma: no cover - ActionIntent 已保证
            raise ValueError("run_cli action requires a config command verb")
        command = self._render_command(
            self._absolute_path(executable, "executable"),
            (*self._arguments(prefix_arguments, "prefix_arguments"), *_COMMAND_ARGUMENTS[intent.command_verb]),
        )
        return PrimaryAction(
            kind=PrimaryActionKind.RUN_CLI,
            command=command,
            resume_ref=intent.resume_ref,
        )

    def _absolute_path(self, value: str | None, field_name: str) -> str:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError(f"{field_name} must be an absolute path")
        path_type = PurePosixPath if self.shell is ShellKind.POSIX else PureWindowsPath
        if not path_type(value).is_absolute():
            raise ValueError(f"{field_name} must be an absolute path")
        return value

    @staticmethod
    def _arguments(values: Sequence[str], field_name: str) -> tuple[str, ...]:
        result = tuple(values)
        if any(not isinstance(value, str) or not value or "\x00" in value for value in result):
            raise ValueError(f"{field_name} must contain non-empty strings")
        return result

    def _render_command(self, executable: str, arguments: Sequence[str]) -> str:
        quote = self._quote_posix if self.shell is ShellKind.POSIX else self._quote_powershell
        tokens = [quote(executable), *(quote(argument) for argument in arguments)]
        prefix = "& " if self.shell is ShellKind.POWERSHELL else ""
        return prefix + " ".join(tokens)

    @staticmethod
    def _quote_posix(value: str) -> str:
        return "'" + value.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _quote_powershell(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
