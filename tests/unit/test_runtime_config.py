from __future__ import annotations

import stat

import pytest
from leo_ppt_generator.config import runtime_config as runtime_config_module
from leo_ppt_generator.config.runtime_config import (
    ConfigStore,
    RuntimeConfigError,
    assert_run_quota,
    canonical_config_digest,
    configure_openai_compatible_profile,
    default_home,
    load_runtime_config,
)


def _write_config(home, body: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(body, encoding="utf-8")


def test_runtime_config_defaults_to_five_workers(tmp_path):
    config = load_runtime_config(home=tmp_path / "home", environ={})

    assert config.values["max_concurrent_workers"] == 5
    assert config.sources["max_concurrent_workers"] == "default"


def test_runtime_config_reports_sources_and_environment_override(tmp_path):
    home = tmp_path / "home"
    _write_config(
        home,
        "schema_version: 1\nprovider_profiles: {}\n"
        "max_concurrent_workers: 3\ntimeouts:\n  worker_page_seconds: 900\n",
    )
    config = load_runtime_config(
        home=home, environ={"LEO_PPT_MAX_WORKERS": "5"}
    )

    assert config.values["max_concurrent_workers"] == 5
    assert config.sources["max_concurrent_workers"] == "environment"
    assert config.source_map["/max_concurrent_workers"] == "environment"
    assert config.values["timeouts"]["worker_page_seconds"] == 900
    assert config.source_map["/timeouts/worker_page_seconds"] == "config.yaml"
    assert config.source_map["/timeouts/backend_api_seconds"] == "default"
    assert config.digest == canonical_config_digest(config.document)


def test_runtime_config_default_home_matches_platform_manager(monkeypatch):
    monkeypatch.delenv("LEO_PPT_HOME", raising=False)
    from tests.integration.test_runtime_manager import load_manager

    assert default_home() == load_manager().default_home()


def test_custom_home_expands_environment_and_is_absolute(tmp_path):
    home = default_home({"ROOT": str(tmp_path), "LEO_PPT_HOME": "$ROOT/config"})
    assert home == (tmp_path / "config").resolve()


@pytest.mark.parametrize(
    "content,reason",
    [
        ("schema_version: 2\n", "config_schema_too_new"),
        (
            "schema_version: 1\nprovider_profiles: {}\napi_key: secret\n",
            "unknown_sensitive_field",
        ),
        (
            "schema_version: 1\nprovider_profiles: {}\nmax_concurrent_workers: 17\n",
            "config_invalid",
        ),
        (
            "schema_version: 1\nmax_concurrent_workers: 3\n",
            "development_config_reset_required",
        ),
        (
            "schema_version: 1\nprovider_profiles:\n"
            "  openai-compatible:\n    endpoint_origin: https://proxy.example.com\n"
            "    model: old-model\n",
            "development_config_reset_required",
        ),
    ],
)
def test_runtime_config_invalid_contracts_fail_closed(tmp_path, content, reason):
    home = tmp_path / "home"
    _write_config(home, content)

    with pytest.raises(RuntimeConfigError, match=reason):
        load_runtime_config(home=home, environ={})


def test_recursive_sensitive_scan_reports_pointer_without_value(tmp_path):
    home = tmp_path / "home"
    canary = "sk-this-must-never-be-rendered"
    _write_config(
        home,
        "schema_version: 1\nprovider_profiles: {}\n"
        f"metadata:\n  nested:\n    api_token: {canary}\n",
    )

    with pytest.raises(RuntimeConfigError) as captured:
        load_runtime_config(home=home, environ={})

    assert captured.value.reason_code == "unknown_sensitive_field"
    assert captured.value.pointer == "/metadata/nested/api_token"
    assert canary not in str(captured.value)


def test_environment_reference_missing_is_a_nonfatal_provider_issue(tmp_path):
    home = tmp_path / "home"
    _write_config(
        home,
        "schema_version: 1\nselected_provider: openai\nprovider_profiles:\n"
        "  openai:\n    model: gpt-image-2\n"
        "    credential_source: environment-reference\n"
        "    credential_ref: env:OPENAI_API_KEY\n",
    )

    config = load_runtime_config(home=home, environ={})

    assert config.values["selected_provider"] == "openai"
    assert [issue.reason_code for issue in config.issues] == [
        "credential_environment_missing"
    ]
    assert config.issues[0].fatal is False


def test_provider_reference_isolated_and_endpoint_is_origin_only(tmp_path):
    home = tmp_path / "home"
    _write_config(
        home,
        "schema_version: 1\nprovider_profiles:\n"
        "  openai-compatible:\n    endpoint_origin: https://images.example.com/\n"
        "    model: '  gpt-image-2  '\n"
        "    credential_source: environment-reference\n"
        "    credential_ref: env:OPENAI_COMPATIBLE_API_KEY\n",
    )
    config = load_runtime_config(
        home=home, environ={"OPENAI_COMPATIBLE_API_KEY": "present"}
    )
    profile = config.values["provider_profiles"]["openai-compatible"]
    assert profile["endpoint_origin"] == "https://images.example.com"
    assert profile["model"] == "gpt-image-2"

    profile_path = home / "config.yaml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            "env:OPENAI_COMPATIBLE_API_KEY", "env:OPENAI_API_KEY"
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeConfigError, match="provider_profile_invalid"):
        load_runtime_config(home=home, environ={"OPENAI_API_KEY": "present"})


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://images.example.com",
        "https://user:pass@images.example.com",
        "https://images.example.com/v1",
        "https://images.example.com?key=value",
        "https://images.example.com/#fragment",
    ],
)
def test_openai_compatible_endpoint_rejects_non_origins(tmp_path, endpoint):
    with pytest.raises(RuntimeConfigError, match="provider_profile_invalid"):
        configure_openai_compatible_profile(
            home=tmp_path / "home",
            environ={"OPENAI_COMPATIBLE_API_KEY": "present"},
            endpoint_origin=endpoint,
            model="gpt-image-2",
        )


def test_config_store_cas_persists_complete_profile_with_private_permissions(tmp_path):
    home = tmp_path / "home"
    config = configure_openai_compatible_profile(
        home=home,
        environ={},
        endpoint_origin="https://proxy.example.com/",
        model="gpt-image-2",
    )

    assert config.values["selected_provider"] == "openai-compatible"
    assert config.values["provider_profiles"]["openai-compatible"] == {
        "model": "gpt-image-2",
        "endpoint_origin": "https://proxy.example.com",
        "credential_source": "environment-reference",
        "credential_ref": "env:OPENAI_COMPATIBLE_API_KEY",
    }
    assert config.issues[0].reason_code == "credential_environment_missing"
    if runtime_config_module.os.name != "nt":
        assert stat.S_IMODE(home.stat().st_mode) == 0o700
        assert stat.S_IMODE((home / "config.yaml").stat().st_mode) == 0o600

    with pytest.raises(RuntimeConfigError, match="config_write_conflict"):
        ConfigStore(home, environ={}).compare_and_swap(None, config.document)


def test_atomic_write_failure_preserves_previous_bytes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    store = ConfigStore(home, environ={})
    original = store.compare_and_swap(
        None, {"schema_version": 1, "provider_profiles": {}}
    )
    previous_bytes = (home / "config.yaml").read_bytes()
    candidate = dict(original.document)
    candidate["max_concurrent_workers"] = 2

    def fail_replace(_source, _destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr(runtime_config_module.os, "replace", fail_replace)
    with pytest.raises(RuntimeConfigError, match="config_write_failed"):
        store.compare_and_swap(original.digest, candidate)

    assert (home / "config.yaml").read_bytes() == previous_bytes
    assert not list(home.glob(".config.yaml.*.tmp"))


def test_run_quota_is_checked_before_finalization(tmp_path):
    home = tmp_path / "home"
    _write_config(
        home,
        "schema_version: 1\nprovider_profiles: {}\nmax_run_bytes: 1048576\n",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "large.bin").write_bytes(b"x" * (1024**2 + 1))

    with pytest.raises(RuntimeConfigError, match="disk_quota_exceeded"):
        assert_run_quota(run, load_runtime_config(home=home, environ={}))
