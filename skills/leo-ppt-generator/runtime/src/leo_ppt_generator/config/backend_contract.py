"""静态 provider registry 与版本化配置映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BackendContractError(ValueError):
    reason_code = "backend_contract_error"


@dataclass(frozen=True)
class Backend:
    name: str
    backend_kind: str
    capabilities: frozenset[str]
    credential_environment: frozenset[str]
    default_model: str
    max_reference_images: int


class BackendRegistry:
    def __init__(self, backends: tuple[Backend, ...]) -> None:
        self._backends = {backend.name: backend for backend in backends}

    @classmethod
    def default(cls) -> BackendRegistry:
        return cls(
            (
                Backend(
                    "fixture",
                    "openai-compatible",
                    frozenset({"generate", "edit", "reference"}),
                    frozenset(),
                    "fixture-model",
                    4,
                ),
                Backend(
                    "builtin-imagegen",
                    "builtin-imagegen",
                    frozenset({"generate", "edit", "mask", "reference"}),
                    frozenset(),
                    "gpt-image-2",
                    16,
                ),
                Backend(
                    "openai",
                    "openai-compatible",
                    frozenset({"generate", "edit", "mask", "reference"}),
                    frozenset({"OPENAI_API_KEY"}),
                    "gpt-image-2",
                    16,
                ),
                Backend(
                    "atlascloud",
                    "atlascloud",
                    frozenset({"generate", "edit", "reference"}),
                    frozenset({"ATLASCLOUD_API_KEY"}),
                    "gpt-image-2",
                    4,
                ),
            )
        )

    def select(self, name: str, *, required: set[str]) -> Backend:
        try:
            backend = self._backends[name]
        except KeyError as exc:
            raise BackendContractError("unknown_backend") from exc
        if not required.issubset(backend.capabilities):
            raise BackendContractError("backend_capability_missing")
        return backend

    def candidates(
        self, required: set[str], *, include_fixtures: bool = False
    ) -> tuple[Backend, ...]:
        """按 registry 顺序枚举满足能力的公开 backend。"""

        return tuple(
            backend
            for backend in self._backends.values()
            if (include_fixtures or backend.name != "fixture")
            and required.issubset(backend.capabilities)
        )

    def create_contract(
        self,
        name: str,
        *,
        mode: str,
        model: str | None = None,
        selection_source: str = "user-confirmed",
        credential_source: str | None = None,
        credential_ref: str | None = None,
    ) -> dict[str, Any]:
        """从静态 registry 生成完整合同，并用同一 loader 自校验。"""

        if mode not in {"generate", "edit"}:
            raise BackendContractError("backend_mode_invalid")
        backend = self.select(name, required={mode})
        selected_model = backend.default_model if model is None else model
        if not isinstance(selected_model, str) or not selected_model.strip():
            raise BackendContractError("backend_model_invalid")
        if backend.credential_environment:
            resolved_credential_source = credential_source or "environment-reference"
            resolved_credential_ref = credential_ref or f"env:{min(backend.credential_environment)}"
        else:
            resolved_credential_source = "host-managed"
            resolved_credential_ref = None
        contract: dict[str, Any] = {
            "schema_version": 1,
            "backend_kind": backend.backend_kind,
            "provider": backend.name,
            "model": selected_model,
            "mode": mode,
            "credential_source": resolved_credential_source,
            "selection_source": selection_source,
            "capabilities": {
                "generate": "generate" in backend.capabilities,
                "edit": "edit" in backend.capabilities,
                "mask": "mask" in backend.capabilities,
                "max_reference_images": backend.max_reference_images,
                "execution_owner": (
                    "agent-host" if backend.backend_kind == "builtin-imagegen" else "runtime"
                ),
            },
        }
        if resolved_credential_ref is not None:
            contract["credential_ref"] = resolved_credential_ref
        self.load(contract, required={mode})
        return contract

    def load(self, value: dict[str, Any], *, required: set[str] | None = None) -> Backend:
        version = value.get("schema_version")
        if version != 1:
            raise BackendContractError("config_schema_too_new" if isinstance(version, int) and version > 1 else "unknown_config_version")
        allowed = {
            "schema_version",
            "backend_kind",
            "provider",
            "model",
            "mode",
            "credential_source",
            "credential_ref",
            "selection_source",
            "capabilities",
            "endpoint_origin",
            "timeouts",
        }
        for key in value:
            lowered = key.lower()
            if key not in allowed and any(marker in lowered for marker in ("token", "secret", "password", "key")):
                raise BackendContractError("unknown_sensitive_field")
            if key not in allowed:
                raise BackendContractError("backend_contract_unknown_field")
        if any(key in value for key in ("token", "api_key", "secret", "api_key_ref")):
            raise BackendContractError("raw_credential_forbidden")
        backend = self.select(str(value.get("provider")), required=set())
        if value.get("backend_kind") != backend.backend_kind:
            raise BackendContractError("backend_kind_mismatch")
        mode = value.get("mode")
        if mode not in {"generate", "edit"}:
            raise BackendContractError("backend_mode_invalid")
        model = value.get("model")
        if not isinstance(model, str) or not model.strip():
            raise BackendContractError("backend_model_invalid")
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, dict):
            raise BackendContractError("backend_capabilities_invalid")
        expected_capability_keys = {
            "generate",
            "edit",
            "mask",
            "max_reference_images",
            "execution_owner",
        }
        if set(capabilities) != expected_capability_keys:
            raise BackendContractError("backend_capabilities_invalid")
        declared = {
            name
            for name in ("generate", "edit", "mask")
            if capabilities.get(name) is True
        }
        if not declared.issubset(backend.capabilities):
            raise BackendContractError("backend_capability_overclaim")
        if not (required or set()).issubset(declared):
            raise BackendContractError("backend_capability_missing")
        if not isinstance(capabilities.get("max_reference_images"), int) or capabilities["max_reference_images"] < 0:
            raise BackendContractError("backend_capabilities_invalid")
        if capabilities["max_reference_images"] > backend.max_reference_images:
            raise BackendContractError("backend_capability_overclaim")
        expected_owner = "agent-host" if backend.backend_kind == "builtin-imagegen" else "runtime"
        if capabilities.get("execution_owner") != expected_owner:
            raise BackendContractError("backend_execution_owner_mismatch")
        credential_source = value.get("credential_source")
        reference = value.get("credential_ref")
        if backend.credential_environment:
            if credential_source not in {"environment-reference", "os-store-reference"}:
                raise BackendContractError("credential_reference_invalid")
            prefixes = ("env:",) if credential_source == "environment-reference" else ("host:", "keychain:")
            if not isinstance(reference, str) or not reference.startswith(prefixes):
                raise BackendContractError("credential_reference_invalid")
            if reference.startswith("env:") and reference.removeprefix("env:") not in backend.credential_environment:
                raise BackendContractError("credential_environment_not_allowed")
            if credential_source == "os-store-reference" and reference not in {
                f"keychain:leo-ppt-generator/{backend.name}",
                f"host:dpapi/{backend.name}",
            }:
                raise BackendContractError("credential_reference_invalid")
        elif credential_source != "host-managed" or reference is not None:
            raise BackendContractError("credential_reference_invalid")
        if value.get("selection_source") not in {"user-confirmed", "fallback-policy"}:
            raise BackendContractError("backend_selection_source_invalid")
        return backend
