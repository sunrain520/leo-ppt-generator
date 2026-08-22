from __future__ import annotations

import json

import pytest
from leo_ppt_generator.backend_execution import (
    BackendExecutionError,
    build_execution_context,
)

from tests.backend_fixtures import backend_contract


def test_execution_context_resolves_declared_environment_reference_without_leaking_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    contract_path = tmp_path / "backend-contract.json"
    contract_path.write_text(json.dumps(backend_contract("openai")), encoding="utf-8")

    context = build_execution_context(contract_path, tmp_path / "isolated")

    assert context.provider == "openai"
    assert context.environment["OPENAI_API_KEY"] == "test-secret"
    assert context.receipt["credential_ref"] == "env:OPENAI_API_KEY"
    assert "test-secret" not in json.dumps(context.receipt)


@pytest.mark.parametrize(
    "endpoint_origin",
    ("https://proxy.example.com", "https://proxy.example.com/v1"),
)
def test_execution_context_maps_compatible_contract_to_isolated_openai_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path, endpoint_origin: str
):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "proxy-secret")
    contract_path = tmp_path / "backend-contract.json"
    contract = backend_contract("openai-compatible")
    contract["endpoint_origin"] = endpoint_origin
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    context = build_execution_context(contract_path, tmp_path / "isolated")

    assert context.provider == "openai-compatible"
    assert context.environment["OPENAI_API_KEY"] == "proxy-secret"
    assert context.environment["OPENAI_BASE_URL"] == "https://proxy.example.com/v1"
    assert context.receipt["credential_ref"] == "env:OPENAI_COMPATIBLE_API_KEY"
    assert "proxy-secret" not in json.dumps(context.receipt)


def test_execution_context_maps_atlas_contract_to_atlas_provider_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-secret")
    contract_path = tmp_path / "backend-contract.json"
    contract_path.write_text(json.dumps(backend_contract("atlascloud")), encoding="utf-8")

    context = build_execution_context(contract_path, tmp_path / "isolated")

    assert context.environment["ATLASCLOUD_API_KEY"] == "atlas-secret"
    assert context.environment["OPENAI_API_KEY"] == "atlas-secret"
    assert context.receipt["provider"] == "atlascloud"
    assert "atlas-secret" not in json.dumps(context.receipt)


def test_missing_declared_credential_fails_closed(tmp_path):
    contract_path = tmp_path / "backend-contract.json"
    contract_path.write_text(json.dumps(backend_contract("openai")), encoding="utf-8")

    with pytest.raises(BackendExecutionError, match="credential_reference_unavailable"):
        build_execution_context(contract_path, tmp_path / "isolated")


def test_noncanonical_keychain_reference_is_rejected(tmp_path):
    contract = backend_contract("openai")
    contract["credential_source"] = "os-store-reference"
    contract["credential_ref"] = "keychain:leo/openai"
    contract_path = tmp_path / "backend-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(BackendExecutionError, match="credential_reference_invalid"):
        build_execution_context(contract_path, tmp_path / "isolated")


def test_os_store_reference_uses_resolver_without_leaking_secret(tmp_path):
    contract = backend_contract("openai")
    contract["credential_source"] = "os-store-reference"
    contract["credential_ref"] = "keychain:leo-ppt-generator/openai"
    contract_path = tmp_path / "backend-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    context = build_execution_context(
        contract_path,
        tmp_path / "isolated",
        resolver=lambda prefix, value: "stored-secret"
        if (prefix, value) == ("keychain", "leo-ppt-generator/openai")
        else None,
    )

    assert context.environment["OPENAI_API_KEY"] == "stored-secret"
    assert "stored-secret" not in json.dumps(context.receipt)
