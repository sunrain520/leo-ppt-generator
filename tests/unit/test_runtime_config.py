from __future__ import annotations

import pytest
from leo_ppt_generator.config.runtime_config import (
    RuntimeConfigError,
    assert_run_quota,
    default_home,
    load_runtime_config,
)


def test_runtime_config_reports_sources_and_environment_override(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(
        "schema_version: 1\nmax_concurrent_workers: 3\ntimeouts:\n  worker_page_seconds: 900\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    monkeypatch.setenv("LEO_PPT_MAX_WORKERS", "5")

    config = load_runtime_config()

    assert config.values["max_concurrent_workers"] == 5
    assert config.sources["max_concurrent_workers"] == "environment"
    assert config.values["timeouts"]["worker_page_seconds"] == 900
    assert config.sources["timeouts"] == "config.yaml"


def test_runtime_config_default_home_matches_platform_manager(monkeypatch):
    monkeypatch.delenv("LEO_PPT_HOME", raising=False)
    from tests.integration.test_runtime_manager import load_manager

    assert default_home() == load_manager().default_home()


@pytest.mark.parametrize(
    "content,reason",
    [
        ("schema_version: 2\n", "config_schema_too_new"),
        ("schema_version: 1\napi_key: secret\n", "unknown_sensitive_field"),
        ("schema_version: 1\nmax_concurrent_workers: 17\n", "config_invalid"),
    ],
)
def test_runtime_config_invalid_contracts_fail_closed(tmp_path, monkeypatch, content, reason):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(content, encoding="utf-8")
    monkeypatch.setenv("LEO_PPT_HOME", str(home))

    with pytest.raises(RuntimeConfigError, match=reason):
        load_runtime_config()


def test_run_quota_is_checked_before_finalization(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(
        "schema_version: 1\nmax_run_bytes: 1048576\n", encoding="utf-8"
    )
    monkeypatch.setenv("LEO_PPT_HOME", str(home))
    run = tmp_path / "run"
    run.mkdir()
    (run / "large.bin").write_bytes(b"x" * (1024**2 + 1))

    with pytest.raises(RuntimeConfigError, match="disk_quota_exceeded"):
        assert_run_quota(run, load_runtime_config())
