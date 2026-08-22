from __future__ import annotations

import pytest
from leo_ppt_generator.config.backend_contract import (
    BackendContractError,
    BackendRegistry,
)

from tests.backend_fixtures import backend_contract


def test_backend_capabilities_and_sensitive_unknown_fields_fail_closed():
    registry = BackendRegistry.default()
    assert registry.select("fixture", required={"generate"}).name == "fixture"
    with pytest.raises(BackendContractError, match="backend_capability_missing"):
        registry.select("fixture", required={"mask"})
    with pytest.raises(BackendContractError, match="unknown_sensitive_field"):
        registry.load({**backend_contract(), "private_token": "x"})
    with pytest.raises(BackendContractError, match="config_schema_too_new"):
        registry.load({**backend_contract(), "schema_version": 99})


def test_backend_registry_enumerates_public_candidates_by_capability():
    registry = BackendRegistry.default()

    assert [backend.name for backend in registry.candidates({"generate"})] == [
        "builtin-imagegen",
        "openai",
        "openai-compatible",
        "atlascloud",
    ]
    assert [backend.name for backend in registry.candidates({"edit", "mask"})] == [
        "builtin-imagegen",
        "openai",
        "openai-compatible",
    ]
    assert [
        backend.name
        for backend in registry.candidates({"generate"}, include_fixtures=True)
    ] == ["fixture", "builtin-imagegen", "openai", "openai-compatible", "atlascloud"]


def test_backend_contract_validates_declared_capabilities_owner_and_credential_allowlist():
    registry = BackendRegistry.default()
    assert registry.load(backend_contract("openai"), required={"generate"}).name == "openai"
    assert registry.load(backend_contract("openai-compatible"), required={"generate"}).name == "openai-compatible"
    overclaim = backend_contract("atlascloud")
    overclaim["capabilities"]["mask"] = True
    with pytest.raises(BackendContractError, match="backend_capability_overclaim"):
        registry.load(overclaim)
    wrong_owner = backend_contract("builtin-imagegen")
    wrong_owner["capabilities"]["execution_owner"] = "runtime"
    with pytest.raises(BackendContractError, match="backend_execution_owner_mismatch"):
        registry.load(wrong_owner)
    wrong_env = backend_contract("openai")
    wrong_env["credential_ref"] = "env:UNRELATED_SECRET"
    with pytest.raises(BackendContractError, match="credential_environment_not_allowed"):
        registry.load(wrong_env)
    wrong_store = backend_contract("openai")
    wrong_store["credential_source"] = "os-store-reference"
    wrong_store["credential_ref"] = "keychain:other-service/openai"
    with pytest.raises(BackendContractError, match="credential_reference_invalid"):
        registry.load(wrong_store)


def test_backend_registry_creates_complete_self_validating_contract():
    registry = BackendRegistry.default()

    contract = registry.create_contract("openai", mode="generate")

    assert registry.load(contract, required={"generate"}).name == "openai"
    assert contract["model"] == "gpt-image-2"
    assert contract["credential_ref"] == "env:OPENAI_API_KEY"
    assert contract["capabilities"]["execution_owner"] == "runtime"

    stored = registry.create_contract(
        "openai",
        mode="generate",
        credential_source="os-store-reference",
        credential_ref="keychain:leo-ppt-generator/openai",
    )
    assert registry.load(stored).name == "openai"

    compatible = registry.create_contract(
        "openai-compatible",
        mode="generate",
        credential_source="os-store-reference",
        credential_ref="keychain:leo-ppt-generator/openai-compatible",
        endpoint_origin="https://proxy.example.com/v1",
    )
    assert compatible["endpoint_origin"] == "https://proxy.example.com/v1"
    with pytest.raises(BackendContractError, match="endpoint_origin_required"):
        registry.create_contract("openai-compatible", mode="generate")


def test_backend_registry_rejects_empty_model_during_creation_and_load():
    registry = BackendRegistry.default()

    with pytest.raises(BackendContractError, match="backend_model_invalid"):
        registry.create_contract("openai", mode="generate", model="")
    with pytest.raises(BackendContractError, match="backend_model_invalid"):
        registry.load({**backend_contract("openai"), "model": ""})
    with pytest.raises(BackendContractError, match="backend_mode_invalid"):
        registry.create_contract("openai", mode="unsupported")


def test_backend_registry_rejects_reference_limit_overclaim():
    registry = BackendRegistry.default()
    contract = backend_contract("atlascloud")
    contract["capabilities"]["max_reference_images"] = 5

    with pytest.raises(BackendContractError, match="backend_capability_overclaim"):
        registry.load(contract)
