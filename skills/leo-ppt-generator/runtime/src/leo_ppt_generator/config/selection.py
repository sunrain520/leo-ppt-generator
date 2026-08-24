"""从全局配置解析任务级 Provider，不执行 I/O 或 Provider 调用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import Capability, HostCapabilityState, ProviderName
from .provider_registry import ProviderRegistry


class ProviderSelectionError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ProviderSelection:
    provider: ProviderName
    source: str
    priority: int | None
    config_digest: str | None


def select_provider(
    *,
    profiles: Mapping[str, Mapping[str, object]],
    credential_available: Mapping[str, bool],
    required_capabilities: frozenset[Capability],
    registry: ProviderRegistry,
    host_imagegen: HostCapabilityState,
    preferred_provider: ProviderName | str | None,
    config_digest: str | None,
    requested_provider: ProviderName | str | None = None,
) -> ProviderSelection:
    """按调用方指定、全局偏好、唯一候选、优先级与宿主兜底依次解析。"""

    requested = _provider_name(requested_provider)
    preferred = _provider_name(preferred_provider)
    candidates = _configured_candidates(
        profiles=profiles,
        credential_available=credential_available,
        required_capabilities=required_capabilities,
        registry=registry,
    )
    by_name = {item.provider: item for item in candidates}

    if requested is not None:
        if requested is ProviderName.BUILTIN_IMAGEGEN:
            if host_imagegen is not HostCapabilityState.AVAILABLE:
                raise ProviderSelectionError("requested_provider_unavailable")
            return ProviderSelection(requested, "explicit-request", None, config_digest)
        candidate = by_name.get(requested)
        if candidate is None:
            raise ProviderSelectionError("requested_provider_unavailable")
        return ProviderSelection(requested, "explicit-request", candidate.priority, config_digest)

    if preferred is not None:
        candidate = by_name.get(preferred)
        if candidate is not None:
            return ProviderSelection(preferred, "configured-preferred", candidate.priority, config_digest)

    if len(candidates) == 1:
        candidate = candidates[0]
        return ProviderSelection(candidate.provider, "configured-singleton", candidate.priority, config_digest)
    if len(candidates) > 1:
        best_priority = min(item.priority for item in candidates)
        best = [item for item in candidates if item.priority == best_priority]
        if len(best) == 1:
            candidate = best[0]
            return ProviderSelection(candidate.provider, "configured-priority", candidate.priority, config_digest)
        raise ProviderSelectionError("provider_priority_tie")

    if host_imagegen is HostCapabilityState.AVAILABLE:
        return ProviderSelection(ProviderName.BUILTIN_IMAGEGEN, "host-fallback", None, config_digest)
    raise ProviderSelectionError("provider_selection_required")


@dataclass(frozen=True)
class _Candidate:
    provider: ProviderName
    priority: int


def _configured_candidates(
    *,
    profiles: Mapping[str, Mapping[str, object]],
    credential_available: Mapping[str, bool],
    required_capabilities: frozenset[Capability],
    registry: ProviderRegistry,
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for name, profile in profiles.items():
        try:
            provider = ProviderName(name)
        except ValueError as error:
            raise ProviderSelectionError("provider_profile_invalid") from error
        if provider is ProviderName.BUILTIN_IMAGEGEN:
            continue
        if profile.get("enabled") is not True or not credential_available.get(name, False):
            continue
        definition = registry.provider(provider, profile.get("endpoint_origin") if isinstance(profile.get("endpoint_origin"), str) else None)
        if not required_capabilities.issubset(definition.supported_capabilities):
            continue
        priority = profile.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ProviderSelectionError("provider_profile_invalid")
        candidates.append(_Candidate(provider, priority))
    return tuple(sorted(candidates, key=lambda item: (item.priority, item.provider.value)))


def _provider_name(value: ProviderName | str | None) -> ProviderName | None:
    if value is None:
        return None
    try:
        return ProviderName(value)
    except ValueError as error:
        raise ProviderSelectionError("provider_selection_invalid") from error
