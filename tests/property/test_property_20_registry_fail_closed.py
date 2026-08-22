from __future__ import annotations

import string
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st
from leo_ppt_generator.application.routes import TASK_CAPABILITIES
from leo_ppt_generator.config.models import (
    Capability,
    ConfigurationState,
    ConfigStatus,
    CredentialReferenceType,
    ProviderName,
    RouteName,
)
from leo_ppt_generator.config.provider_registry import (
    DeclarationState,
    ProviderRegistry,
)
from leo_ppt_generator.config.readiness import (
    ProviderReadinessFacts,
    evaluate_readiness,
)
from leo_ppt_generator.config.reason_codes import ReasonCode
from leo_ppt_generator.config.runtime_config import RuntimeConfigError, load_runtime_config

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)


@st.composite
def registry_cases(draw: st.DrawFn):
    label = draw(st.text(string.ascii_lowercase + string.digits, min_size=1, max_size=16))
    port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    endpoint = f"https://{label}.example.invalid" + (f":{port}" if port else "")
    omitted = draw(st.sampled_from(tuple(Capability)))
    route = draw(st.sampled_from(tuple(RouteName)))
    task_capabilities = draw(
        st.frozensets(
            st.sampled_from(
                tuple(sorted(TASK_CAPABILITIES, key=lambda capability: capability.value))
            )
        )
    )
    promotion_field = draw(
        st.sampled_from(
            ("auth_probe", "model_discovery", "idempotency", "retry", "capabilities", "verification_policy")
        )
    )
    promotion_value = draw(
        st.sampled_from(("supported", True, 3, {"support": "supported"}))
    )
    return endpoint, omitted, route, task_capabilities, promotion_field, promotion_value


@PROPERTY_SETTINGS
@given(case=registry_cases())
def test_property_20_registry_policy_is_fail_closed(case):
    """**Validates: Requirements 4.7, 6.11, 6.12, 19.2, 19.3, 19.4, 19.6, 19.8**"""

    endpoint, omitted, route, task_capabilities, promotion_field, promotion_value = case
    registry = ProviderRegistry.default()
    definition = registry.provider(ProviderName.OPENAI_COMPATIBLE, endpoint)
    policy = registry.policy(ProviderName.OPENAI_COMPATIBLE, endpoint)

    # 任意用户 origin 都只能取得 generic unknown 策略；unknown 探测不会自动执行。
    assert policy is registry.policy(
        ProviderName.OPENAI_COMPATIBLE, "https://another.example.invalid"
    )
    assert policy.auth_probe.support is DeclarationState.UNKNOWN
    assert policy.model_discovery.support is DeclarationState.UNKNOWN
    assert not policy.auth_probe.automatic
    assert not policy.model_discovery.automatic
    called_operations = [
        name
        for name, operation in (
            ("auth_probe", policy.auth_probe),
            ("model_discovery", policy.model_discovery),
        )
        if operation.automatic
    ]
    assert called_operations == []

    # unknown 幂等与 retry 不能授权结果不确定后的自动重试。
    assert policy.idempotency.support is DeclarationState.UNKNOWN
    assert policy.idempotency.request_not_accepted_evidence is DeclarationState.UNKNOWN
    assert not policy.idempotency.replay_safe_after_acceptance
    assert policy.retry.support is DeclarationState.UNKNOWN
    assert policy.retry.max_attempts == 1
    assert policy.retry.retryable_failures == frozenset()
    assert policy.retry.backoff_seconds == ()

    # capability 声明缺失必须按 unknown 处理，不能进入 supported 候选集合。
    sparse_definition = replace(
        definition,
        capabilities={
            capability: state
            for capability, state in definition.capabilities.items()
            if capability is not omitted
        },
    )
    sparse_registry = ProviderRegistry((sparse_definition,))
    sparse = sparse_registry.provider(ProviderName.OPENAI_COMPATIBLE, endpoint)
    assert sparse.capability(omitted) is DeclarationState.UNKNOWN
    assert omitted not in sparse.supported_capabilities

    # 即使静态 capability 全部 supported，没有真实 evidence 也只能 unverified。
    facts = ProviderReadinessFacts(
        provider=ProviderName.OPENAI_COMPATIBLE,
        configuration_state=ConfigurationState.LOCALLY_CONFIGURED,
        reason_code=ReasonCode.PROVIDER_VERIFICATION_NOT_RUN,
        candidate_capabilities=definition.supported_capabilities,
        credential_reference_type=CredentialReferenceType.ENVIRONMENT,
    )
    readiness = evaluate_readiness(
        (facts,),
        selected_provider=ProviderName.OPENAI_COMPATIBLE,
        route=route,
        task_capabilities=task_capabilities,
    )
    assert readiness.status is ConfigStatus.CONFIGURED_UNVERIFIED
    assert readiness.readiness_scope.verified_capabilities == frozenset()
    assert readiness.readiness_scope.missing_capabilities == readiness.readiness_scope.required_capabilities

    # 用户 Config_File 中的策略提升字段必须被拒绝，且不能改变 checked-in Registry。
    registry_before = registry.snapshot()
    document = {
        "schema_version": 1,
        "selected_provider": "openai-compatible",
        "provider_profiles": {
            "openai-compatible": {
                "endpoint_origin": endpoint,
                "model": "gpt-image-2",
                "credential_source": "environment-reference",
                "credential_ref": "env:OPENAI_COMPATIBLE_API_KEY",
                promotion_field: promotion_value,
            }
        },
    }
    with tempfile.TemporaryDirectory() as temporary_home:
        home = Path(temporary_home)
        (home / "config.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )
        with pytest.raises(RuntimeConfigError) as captured:
            load_runtime_config(
                home=home,
                environ={"OPENAI_COMPATIBLE_API_KEY": "test-only-placeholder"},
            )

    assert captured.value.reason_code == "provider_profile_invalid"
    assert registry.snapshot() == registry_before
    assert registry.policy(ProviderName.OPENAI_COMPATIBLE, endpoint) is policy