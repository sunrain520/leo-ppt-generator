from __future__ import annotations

import pytest

from leo_ppt_generator.config.models import Capability, HostCapabilityState, ProviderName
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.selection import ProviderSelectionError, select_provider


def _select(
    profiles: dict[str, dict[str, object]],
    *,
    preferred: str | None = None,
    host: HostCapabilityState = HostCapabilityState.UNAVAILABLE,
):
    return select_provider(
        profiles=profiles,
        credential_available={name: True for name in profiles},
        required_capabilities=frozenset({Capability.GENERATE}),
        registry=ProviderRegistry.default(),
        host_imagegen=host,
        preferred_provider=preferred,
        config_digest="a" * 64,
    )


def test_single_configured_provider_is_selected_without_confirmation():
    selection = _select({"openai": {"enabled": True, "priority": 100}})

    assert selection.provider is ProviderName.OPENAI
    assert selection.source == "configured-singleton"


def test_preferred_provider_wins_over_lower_priority_candidate():
    selection = _select(
        {
            "openai": {"enabled": True, "priority": 1},
            "atlascloud": {"enabled": True, "priority": 2},
        },
        preferred="atlascloud",
    )

    assert selection.provider is ProviderName.ATLASCLOUD
    assert selection.source == "configured-preferred"


def test_ineligible_preferred_provider_falls_back_to_eligible_priority_candidate():
    selection = select_provider(
        profiles={
            "openai": {"enabled": False, "priority": 1},
            "atlascloud": {"enabled": True, "priority": 2},
        },
        credential_available={"openai": True, "atlascloud": True},
        required_capabilities=frozenset({Capability.GENERATE}),
        registry=ProviderRegistry.default(),
        host_imagegen=HostCapabilityState.AVAILABLE,
        preferred_provider="openai",
        config_digest="a" * 64,
    )

    assert selection.provider is ProviderName.ATLASCLOUD
    assert selection.source == "configured-singleton"


def test_explicit_request_does_not_fall_back_when_the_requested_provider_is_ineligible():
    with pytest.raises(ProviderSelectionError, match="requested_provider_unavailable"):
        select_provider(
            profiles={"openai": {"enabled": False, "priority": 1}},
            credential_available={"openai": True},
            required_capabilities=frozenset({Capability.GENERATE}),
            registry=ProviderRegistry.default(),
            host_imagegen=HostCapabilityState.AVAILABLE,
            preferred_provider=None,
            requested_provider="openai",
            config_digest="a" * 64,
        )


def test_unique_lowest_priority_value_wins_deterministically():
    selection = _select(
        {
            "openai": {"enabled": True, "priority": 2},
            "atlascloud": {"enabled": True, "priority": 1},
        }
    )

    assert selection.provider is ProviderName.ATLASCLOUD
    assert selection.source == "configured-priority"


def test_equal_best_priorities_require_configuration():
    with pytest.raises(ProviderSelectionError, match="provider_priority_tie"):
        _select(
            {
                "openai": {"enabled": True, "priority": 1},
                "atlascloud": {"enabled": True, "priority": 1},
            }
        )


def test_configured_provider_precedes_available_host_imagegen():
    selection = _select(
        {"openai": {"enabled": True, "priority": 1}},
        host=HostCapabilityState.AVAILABLE,
    )

    assert selection.provider is ProviderName.OPENAI


def test_available_host_is_a_fallback_when_no_configured_candidate_exists():
    selection = _select({}, host=HostCapabilityState.AVAILABLE)

    assert selection.provider is ProviderName.BUILTIN_IMAGEGEN
    assert selection.source == "host-fallback"
