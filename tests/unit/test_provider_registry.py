from __future__ import annotations

from datetime import timedelta

import pytest
from leo_ppt_generator.config.backend_contract import BackendRegistry
from leo_ppt_generator.config.models import Capability, ProviderName
from leo_ppt_generator.config.provider_registry import (
    DEFAULT_ARTIFACT_MEDIA_TYPES,
    DEFAULT_CAPABILITY_TTL,
    DeclarationState,
    ProviderRegistry,
    ProviderRegistryError,
)


def test_registry_declares_complete_fail_closed_provider_metadata():
    registry = ProviderRegistry.default()

    for definition in registry.definitions(include_internal=True):
        assert definition.adapter.name
        assert definition.adapter.version
        assert definition.adapter.backend_kind
        assert set(definition.capabilities) == set(Capability)
        assert all(
            state in DeclarationState for state in definition.capabilities.values()
        )
        assert definition.capability("future-capability") is DeclarationState.UNKNOWN
        policy = definition.verification_policy
        assert policy.version >= 1
        assert set(policy.capability_ttls) == set(Capability)
        assert all(policy.ttl(capability) == timedelta(days=7) for capability in Capability)
        assert policy.artifacts.support is DeclarationState.SUPPORTED
        assert policy.artifacts.media_types == DEFAULT_ARTIFACT_MEDIA_TYPES
        assert policy.artifacts.max_bytes is not None

    with pytest.raises(ProviderRegistryError, match="unknown_provider"):
        registry.provider("user-invented-provider")


def test_generic_openai_compatible_endpoint_cannot_promote_unknown_safety_policy():
    registry = ProviderRegistry.default()
    first = registry.policy(
        ProviderName.OPENAI_COMPATIBLE, "https://proxy.example.com/v1"
    )
    second = registry.policy(
        ProviderName.OPENAI_COMPATIBLE, "https://other.example.net"
    )

    assert first is second
    assert first.auth_probe.support is DeclarationState.UNKNOWN
    assert first.model_discovery.support is DeclarationState.UNKNOWN
    assert first.idempotency.support is DeclarationState.UNKNOWN
    assert (
        first.idempotency.request_not_accepted_evidence
        is DeclarationState.UNKNOWN
    )
    assert first.retry.support is DeclarationState.UNKNOWN
    assert not first.auth_probe.automatic
    assert not first.model_discovery.automatic


def test_registry_snapshot_and_policy_ttls_are_immutable():
    registry = ProviderRegistry.default()
    snapshot = registry.snapshot()
    policy = registry.policy(ProviderName.OPENAI, None)

    with pytest.raises(TypeError):
        snapshot["openai-compatible"] = snapshot["openai"]  # type: ignore[index]
    with pytest.raises(TypeError):
        policy.capability_ttls[Capability.GENERATE] = DEFAULT_CAPABILITY_TTL * 2  # type: ignore[index]


def test_backend_registry_projects_candidate_metadata_from_provider_registry():
    backends = BackendRegistry.default()
    registry = backends.provider_registry
    assert registry is not None

    for backend in backends.candidates(set(), include_fixtures=True):
        definition = registry.provider(backend.name, None)
        assert backend.definition is definition
        assert backend.backend_kind == definition.adapter.backend_kind
        assert backend.capabilities == frozenset(
            capability.value for capability in definition.supported_capabilities
        )
        assert backend.credential_environment == definition.credential_environments
        assert backend.default_model == definition.default_model
        assert backend.max_reference_images == definition.max_reference_images
        assert backend.verification_policy is definition.verification_policy