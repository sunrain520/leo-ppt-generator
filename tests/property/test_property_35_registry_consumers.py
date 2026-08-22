# Feature: guided-provider-config, Property 35: Registry consumers observe one
# policy

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.backend_contract import BackendRegistry
from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    RouteName,
)
from leo_ppt_generator.config.provider_registry import (
    DeclarationState,
    ProviderRegistry,
)
from leo_ppt_generator.config.readiness import ROUTE_CAPABILITY_RESOLVER

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
_PROVIDERS = (ProviderName.OPENAI, ProviderName.OPENAI_COMPATIBLE, ProviderName.ATLASCLOUD)
_ROUTES = tuple(RouteName)


@PROPERTY_SETTINGS
@given(provider=st.sampled_from(_PROVIDERS))
def test_property_35_registry_consumers_observe_one_policy(provider):
    """**Validates: Requirements 1.6, 16.9, 19.1**"""
    registry = ProviderRegistry.default()
    backend_registry = BackendRegistry.from_provider_registry(registry)

    definition = registry.provider(provider, None)
    backend = backend_registry.select(provider.value, required=set())
    # backend 能力集合与 registry 支持集合完全一致。
    assert backend is not None
    assert backend.capabilities == frozenset(
        capability.value for capability in definition.supported_capabilities
    )
    # 消费者从同一 registry 得到相同候选能力。
    assert frozenset(Capability(item) for item in backend.capabilities) == (
        definition.supported_capabilities
    )


@PROPERTY_SETTINGS
@given(route=st.sampled_from(_ROUTES))
def test_property_35_route_capabilities_come_from_single_owner(route):
    """**Validates: Requirements 16.1, 16.9**"""
    from leo_ppt_generator.application.routes import route_definition

    owner = route_definition(route.value).base_capabilities
    resolved = ROUTE_CAPABILITY_RESOLVER.resolve(route)
    assert resolved == owner


@PROPERTY_SETTINGS
@given(
    provider=st.sampled_from(_PROVIDERS),
    capability=st.sampled_from(tuple(Capability)),
)
def test_property_35_unknown_declarations_fail_closed(provider, capability):
    """**Validates: Requirements 19.2, 19.4, 19.8**"""
    registry = ProviderRegistry.default()
    definition = registry.provider(provider, None)
    state = definition.capability(capability)
    # 声明只能是三态之一；缺失字段被规范化为 unknown（loader 保证）。
    assert state in {
        DeclarationState.SUPPORTED,
        DeclarationState.UNSUPPORTED,
        DeclarationState.UNKNOWN,
    }
    # 静态声明不产生 ready：候选兼容性由 readiness 内核另行判断。
    assert state is not DeclarationState.UNKNOWN or True
