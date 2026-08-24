from __future__ import annotations

import json
import os
import string
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hypothesis import given, settings, strategies as st
from leo_ppt_generator.config.runtime_config import (
    RuntimeConfigError,
    configure_openai_compatible_profile,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
_PROVIDERS = ("openai", "openai-compatible", "atlascloud")
_ENV_REFS = {
    "openai": "env:OPENAI_API_KEY",
    "openai-compatible": "env:OPENAI_API_KEY",
    "atlascloud": "env:ATLASCLOUD_API_KEY",
}
_OS_REFS = {
    provider: (
        f"keychain:leo-ppt-generator/{provider}",
        f"host:dpapi/{provider}",
    )
    for provider in _PROVIDERS
}
_ALL_REFS = (
    "",
    "env:UNKNOWN_API_KEY",
    *tuple(_ENV_REFS.values()),
    *(reference for references in _OS_REFS.values() for reference in references),
)


@dataclass(frozen=True)
class ProfileCase:
    endpoint: str
    normalized_endpoint: str
    endpoint_valid: bool
    model: str
    model_valid: bool
    credential_source: str
    credential_ref: str | None
    credential_generation: int | None
    credential_valid: bool


@st.composite
def endpoint_cases(draw: st.DrawFn) -> tuple[str, str, bool]:
    label = draw(
        st.text(string.ascii_lowercase + string.digits, min_size=1, max_size=12)
    )
    host = f"{label}.example.com"
    port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    authority = host.upper() + (f":{port}" if port is not None else "")
    normalized = f"https://{host}" + (f":{port}" if port is not None else "")
    kind = draw(
        st.sampled_from(
            ("valid", "http", "userinfo", "query", "fragment", "path")
        )
    )
    endpoints = {
        "valid": f" \tHTTPS://{authority}{draw(st.sampled_from(('', '/')))}\n",
        "http": f"http://{authority}",
        "userinfo": f"https://user:pass@{authority}",
        "query": f"https://{authority}?token=value",
        "fragment": f"https://{authority}#settings",
        "path": f"https://{authority}/v1/images",
    }
    return endpoints[kind], normalized, kind == "valid"


def _platform_accepts(reference: str) -> bool:
    if sys.platform == "darwin":
        return reference.startswith("keychain:")
    if os.name == "nt":
        return reference.startswith("host:dpapi/")
    return True


@st.composite
def profile_cases(draw: st.DrawFn) -> ProfileCase:
    endpoint, normalized_endpoint, endpoint_valid = draw(endpoint_cases())
    model_body = draw(
        st.text(
            string.ascii_letters + string.digits + "-._/",
            min_size=1,
            max_size=32,
        )
    )
    model_valid = draw(st.booleans())
    model = (
        f" \t{model_body}\n"
        if model_valid
        else draw(st.sampled_from(("", " ", "\t\n")))
    )
    source = draw(st.sampled_from(("environment-reference", "os-store-reference")))
    reference = draw(st.one_of(st.none(), st.sampled_from(_ALL_REFS)))
    generation = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=100))
    )

    if source == "environment-reference":
        effective_ref = reference or _ENV_REFS["openai-compatible"]
        credential_valid = (
            reference != ""
            and effective_ref == _ENV_REFS["openai-compatible"]
            and generation is None
        )
    else:
        effective_ref = reference or _ENV_REFS["openai-compatible"]
        credential_valid = (
            effective_ref in _OS_REFS["openai-compatible"]
            and _platform_accepts(effective_ref)
            and generation is not None
            and generation >= 1
        )

    return ProfileCase(
        endpoint,
        normalized_endpoint,
        endpoint_valid,
        model,
        model_valid,
        source,
        reference,
        generation,
        credential_valid,
    )


@PROPERTY_SETTINGS
@given(
    case=profile_cases(),
    secrets=st.tuples(
        *(
            st.binary(min_size=24, max_size=48).map(
                lambda value, provider=provider: (
                    provider,
                    f"sk-property9-{value.hex()}",
                )
            )
            for provider in _PROVIDERS
        )
    ),
)
def test_property_9_provider_profiles_are_normalized_isolated_and_secret_free(
    case: ProfileCase,
    secrets: tuple[tuple[str, str], ...],
) -> None:
    """**Validates: Requirements 4.2, 4.3, 4.4, 4.5**"""

    expected_valid = case.endpoint_valid and case.model_valid and case.credential_valid
    secret_by_provider = dict(secrets)
    environment = {
        _ENV_REFS[provider].removeprefix("env:"): secret
        for provider, secret in secret_by_provider.items()
    }

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        try:
            config = configure_openai_compatible_profile(
                home=home,
                environ=environment,
                endpoint_origin=case.endpoint,
                model=case.model,
                credential_source=case.credential_source,
                credential_ref=case.credential_ref,
                credential_generation=case.credential_generation,
            )
        except RuntimeConfigError:
            assert not expected_valid
            yaml_text = (
                (home / "config.yaml").read_text(encoding="utf-8")
                if (home / "config.yaml").exists()
                else ""
            )
            assert all(secret not in yaml_text for secret in secret_by_provider.values())
            return

        assert expected_valid
        profile = config.document["provider_profiles"]["openai-compatible"]
        expected_ref = (
            case.credential_ref
            if case.credential_ref is not None
            else _ENV_REFS["openai-compatible"]
        )
        assert config.document["selected_provider"] == "openai-compatible"
        assert profile["endpoint_origin"] == case.normalized_endpoint
        assert profile["model"] == case.model.strip() and profile["model"]
        assert profile["credential_source"] == case.credential_source
        assert profile["credential_ref"] == expected_ref
        assert expected_ref in (
            _ENV_REFS["openai-compatible"],
            *_OS_REFS["openai-compatible"],
        )
        assert set(profile) == {
            "endpoint_origin",
            "model",
            "credential_source",
            "credential_ref",
            *(
                ("credential_generation",)
                if case.credential_source == "os-store-reference"
                else ()
            ),
        }

        yaml_text = (home / "config.yaml").read_text(encoding="utf-8")
        serialized_document = json.dumps(config.document, ensure_ascii=False)
        assert all(
            secret not in yaml_text and secret not in serialized_document
            for secret in secret_by_provider.values()
        )
