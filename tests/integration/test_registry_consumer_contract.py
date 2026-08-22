"""Registry/Route 消费者契约集成测试（8.4）。

验证 setup、BackendRegistry、ConfigService 从同一 ProviderRegistry /
Route owner 得到一致的候选能力与安全策略，无第二份真值。
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from leo_ppt_generator.application.routes import (
    ROUTE_CAPABILITY_RESOLVER,
    route_definition,
)
from leo_ppt_generator.config.backend_contract import BackendRegistry
from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    RouteName,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import ConfigService, StatusRequest

NOW = datetime(2026, 1, 8, tzinfo=UTC)
_PROVIDERS = (ProviderName.OPENAI, ProviderName.OPENAI_COMPATIBLE, ProviderName.ATLASCLOUD)
_ROUTES = tuple(RouteName)


def test_backend_registry_capabilities_match_provider_registry():
    registry = ProviderRegistry.default()
    backend_registry = BackendRegistry.from_provider_registry(registry)
    for provider in _PROVIDERS:
        definition = registry.provider(provider, None)
        backend = backend_registry.select(provider.value, required=set())
        assert backend.capabilities == frozenset(
            capability.value for capability in definition.supported_capabilities
        )


def test_route_owner_is_single_source_for_all_routes():
    from leo_ppt_generator.application.routes import route_definition

    for route in _ROUTES:
        definition = route_definition(route.value)
        resolved = ROUTE_CAPABILITY_RESOLVER.resolve(route)
        assert resolved == definition.base_capabilities
        # setup 的基础能力映射不得复制第二份。
        assert route.value != "generate" or resolved == frozenset({Capability.GENERATE})


def test_config_service_and_registry_agree_on_candidate_capabilities():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        registry = ProviderRegistry.default()
        store = ConfigStore(home)
        store.compare_and_swap(
            None,
            {
                "schema_version": 1,
                "selected_provider": "openai",
                "provider_profiles": {
                    "openai": {
                        "model": "gpt-image-2",
                        "credential_source": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                    }
                },
            },
        )

        class EnvStore:
            def status(self, provider):
                from leo_ppt_generator.credentials import PROVIDERS

                env_name = PROVIDERS[provider]
                if env_name == "OPENAI_API_KEY":
                    return {
                        "status": "available",
                        "reference_type": "environment-reference",
                        "credential_ref": "env:OPENAI_API_KEY",
                        "reason_code": "credential_store_available",
                    }
                return {
                    "status": "missing",
                    "reference_type": "none",
                    "credential_ref": None,
                    "reason_code": "credential_missing",
                }

        service = ConfigService(
            store,
            EnvStore(),
            registry,
            FileReceiptStore(home, registry, clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        report = service.status(StatusRequest())
        assert report.status.value == "configured_unverified"
        # readiness scope 的 required capabilities 来自 Route owner。
        definition = route_definition(RouteName.GENERATE.value)
        assert (
            report.readiness_scope.required_capabilities
            == definition.base_capabilities
        )
        # provider report 的能力与 registry 一致。
        provider_report = next(
            item for item in report.providers if item.provider is ProviderName.OPENAI
        )
        assert (
            provider_report.candidate_capabilities
            == registry.provider(ProviderName.OPENAI, None).supported_capabilities
        )
