"""把冻结的 backend contract 转换成一次受控 provider 执行上下文。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .config.backend_contract import BackendContractError, BackendRegistry
from .credentials import PROVIDERS, CredentialError, credential_manager
from .storage import canonical_json, sha256_file


class BackendExecutionError(ValueError):
    """稳定的执行层错误；不得把 secret 放进错误文本。"""


CredentialResolver = Callable[[str, str], str | None]


@dataclass(frozen=True)
class BackendExecutionContext:
    provider: str
    model: str
    mode: str
    environment: Mapping[str, str]
    timeout_seconds: int
    retries: int
    contract_sha256: str
    receipt: Mapping[str, object]


def _load_contract(path: Path) -> tuple[dict, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackendExecutionError("backend_contract_invalid") from exc
    if not isinstance(value, dict):
        raise BackendExecutionError("backend_contract_invalid")
    try:
        BackendRegistry.default().load(value)
    except BackendContractError as exc:
        raise BackendExecutionError(str(exc)) from exc
    try:
        digest = sha256_file(path)
    except (OSError, ValueError) as exc:
        raise BackendExecutionError("backend_contract_unreadable") from exc
    return value, digest


def _resolve_reference(
    source: str,
    reference: str | None,
    *,
    resolver: CredentialResolver | None,
    provider: str,
) -> str | None:
    if source == "host-managed":
        return None
    if not isinstance(reference, str) or ":" not in reference:
        raise BackendExecutionError("credential_reference_invalid")
    prefix, value = reference.split(":", 1)
    if prefix == "env":
        secret = os.environ.get(value)
        if not secret:
            raise BackendExecutionError("credential_reference_unavailable")
        return secret
    if prefix in {"host", "keychain"}:
        environment_name = PROVIDERS.get(provider)
        if environment_name and os.environ.get(environment_name):
            return os.environ[environment_name]
        if resolver is None:
            resolver = credential_manager().resolve
        try:
            secret = resolver(prefix, value)
        except CredentialError as exc:
            raise BackendExecutionError(str(exc)) from exc
        if not secret:
            raise BackendExecutionError("credential_reference_unavailable")
        return secret
    raise BackendExecutionError("credential_reference_invalid")


def _openai_compatible_api_base_url(endpoint_origin: str) -> str:
    """从持久化的安全 origin 派生 OpenAI SDK 所需 `/v1` base URL。"""

    base_url = endpoint_origin.rstrip("/")
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def build_execution_context(
    contract_path: str | Path,
    isolated_root: str | Path,
    *,
    resolver: CredentialResolver | None = None,
    timeout_seconds: int | None = None,
    retries: int | None = None,
) -> BackendExecutionContext:
    """读取并执行冻结 contract；只返回最小、非持久化的环境上下文。"""

    path = Path(contract_path).resolve()
    contract, contract_sha256 = _load_contract(path)
    provider = str(contract["provider"])
    credential = _resolve_reference(
        str(contract["credential_source"]),
        contract.get("credential_ref"),
        resolver=resolver,
        provider=provider,
    )
    env: dict[str, str] = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "CODEX_PPT_HOME": str(Path(isolated_root).resolve() / "codex-ppt-config"),
        "EDITPPT_CONFIG_HOME": str(Path(isolated_root).resolve() / "editppt-config"),
    }
    if credential is not None:
        if provider == "atlascloud":
            # Atlas vendor 使用独立的 HTTP provider；兼容层只需同时提供其旧字段。
            env["ATLASCLOUD_API_KEY"] = credential
            env["OPENAI_API_KEY"] = credential
        elif provider in {"openai", "openai-compatible"}:
            env["OPENAI_API_KEY"] = credential
        else:
            raise BackendExecutionError("provider_credential_mapping_unsupported")
    endpoint = contract.get("endpoint_origin")
    if isinstance(endpoint, str) and endpoint:
        env["OPENAI_BASE_URL"] = (
            _openai_compatible_api_base_url(endpoint)
            if provider == "openai-compatible"
            else endpoint
        )
    timeouts = contract.get("timeouts")
    if not isinstance(timeouts, dict):
        timeouts = {}
    configured_timeout = timeouts.get("backend_api_seconds", 60)
    configured_retries = timeouts.get("backend_api_retries", 3)
    timeout = configured_timeout if timeout_seconds is None else timeout_seconds
    retry_count = configured_retries if retries is None else retries
    if not isinstance(timeout, int) or timeout < 1:
        raise BackendExecutionError("backend_timeout_invalid")
    if not isinstance(retry_count, int) or retry_count < 0:
        raise BackendExecutionError("backend_retries_invalid")
    receipt = {
        "schema_version": 1,
        "provider": provider,
        "model": str(contract["model"]),
        "mode": str(contract["mode"]),
        "credential_source": str(contract["credential_source"]),
        "credential_ref": contract.get("credential_ref"),
        "contract_sha256": contract_sha256,
        "timeout_seconds": timeout,
        "retries": retry_count,
    }
    # A cheap invariant protecting future additions to the receipt.
    if any(secret and secret in canonical_json(receipt) for secret in [credential]):
        raise BackendExecutionError("secret_in_execution_receipt")
    return BackendExecutionContext(
        provider=provider,
        model=str(contract["model"]),
        mode=str(contract["mode"]),
        environment=env,
        timeout_seconds=timeout,
        retries=retry_count,
        contract_sha256=contract_sha256,
        receipt=receipt,
    )
