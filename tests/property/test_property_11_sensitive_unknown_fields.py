from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings, strategies as st
from leo_ppt_generator.config.models import ProviderName
from leo_ppt_generator.config.provider_registry import DeclarationState, ProviderRegistry
from leo_ppt_generator.config.runtime_config import RuntimeConfigError, load_runtime_config


PROPERTY_SETTINGS = settings(
    max_examples=100,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
SENSITIVE_MARKERS = ("token", "secret", "password", "key")
POLICY_FIELDS = (
    "auth_probe",
    "model_discovery",
    "idempotency",
    "retry",
    "capability_ttls",
    "verification_policy",
)
SAFE_STEMS = ("metadata", "custom", "override", "policy", "registry", "probe", "rules")


def _json_pointer(parts: list[str]) -> str:
    return "".join(f"/{part.replace('~', '~0').replace('/', '~1')}" for part in parts)


def _nest(parts: list[str], value: str) -> dict[str, Any]:
    nested: Any = value
    for part in reversed(parts):
        nested = {part: nested}
    return nested


@st.composite
def sensitive_unknown_field_cases(draw: st.DrawFn) -> tuple[dict[str, Any], str, str]:
    digest = hashlib.sha256(draw(st.binary(min_size=32, max_size=32))).hexdigest()
    suffixes = draw(st.lists(st.text("abcdef0123456789", min_size=1, max_size=8), min_size=2, max_size=4))
    separators = draw(st.lists(st.sampled_from(("", "~part", "/part", "~/part")), min_size=len(suffixes), max_size=len(suffixes)))
    nested_names = [
        f"{draw(st.sampled_from(SAFE_STEMS))}_{suffix}{separator}"
        for suffix, separator in zip(suffixes, separators, strict=True)
    ]
    trigger_by_name = draw(st.booleans())
    if trigger_by_name:
        marker = draw(st.sampled_from(SENSITIVE_MARKERS))
        leaf_name = f"private_{marker}_{suffixes[0]}{draw(st.sampled_from(('', '~leaf', '/leaf')))}"
        canary = f"canary-{digest}"
    else:
        leaf_name = f"payload_{suffixes[0]}{draw(st.sampled_from(('', '~leaf', '/leaf')))}"
        canary = f"sk-{digest}"

    policy_field = draw(st.sampled_from(POLICY_FIELDS))
    override_path = [policy_field, *nested_names, leaf_name]
    profile = {
        "endpoint_origin": "https://proxy.example.com",
        "model": "gpt-image-2",
        "credential_source": "environment-reference",
        "credential_ref": "env:OPENAI_COMPATIBLE_API_KEY",
        "registry_overrides": _nest(override_path, canary),
    }
    document = {
        "schema_version": 1,
        "selected_provider": "openai-compatible",
        "provider_profiles": {"openai-compatible": profile},
    }
    pointer = _json_pointer(
        [
            "provider_profiles",
            "openai-compatible",
            "registry_overrides",
            *override_path,
        ]
    )
    return document, pointer, canary


@PROPERTY_SETTINGS
@given(case=sensitive_unknown_field_cases())
def test_property_11_sensitive_unknown_fields_fail_without_disclosure(case):
    """**Validates: Requirements 5.5, 15.2, 18.4, 19.8**"""

    document, expected_pointer, canary = case
    registry = ProviderRegistry.default()
    registry_before = registry.snapshot()
    policy_before = registry.policy(
        ProviderName.OPENAI_COMPATIBLE, "https://proxy.example.com"
    )
    safety_before = (
        policy_before.auth_probe.support,
        policy_before.model_discovery.support,
        policy_before.idempotency.support,
        policy_before.retry.support,
    )

    with tempfile.TemporaryDirectory() as temporary_home:
        home = Path(temporary_home)
        (home / "config.yaml").write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeConfigError) as captured:
            load_runtime_config(home=home, environ={})

    error = captured.value
    assert error.reason_code == "unknown_sensitive_field"
    assert error.pointer == expected_pointer

    error_report = {
        "status": "failed",
        "reason_code": str(error),
    }
    rendered_report = json.dumps(error_report, ensure_ascii=False, sort_keys=True)
    assert error_report == {
        "status": "failed",
        "reason_code": f"unknown_sensitive_field:{expected_pointer}",
    }
    assert all(
        canary not in rendered
        for rendered in (str(error), repr(error), rendered_report)
    )

    policy_after = registry.policy(
        ProviderName.OPENAI_COMPATIBLE, "https://proxy.example.com"
    )
    assert registry.snapshot() == registry_before
    assert (
        policy_after.auth_probe.support,
        policy_after.model_discovery.support,
        policy_after.idempotency.support,
        policy_after.retry.support,
    ) == safety_before == (DeclarationState.UNKNOWN,) * 4
