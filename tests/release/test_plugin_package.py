from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


build_release = module("build_release", ROOT / "scripts/build_release.py")
sys.modules["build_release"] = build_release
validate_release = module("validate_release", ROOT / "scripts/validate_release.py")


def test_plugin_manifest_matches_root_and_declares_only_real_components():
    value = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert value["name"] == ROOT.name == "leo-ppt-generator"
    assert value["skills"] == "./skills/"
    assert value["license"] == "MIT"
    assert not {"apps", "mcpServers", "hooks"}.intersection(value)


def test_release_build_is_reproducible_and_both_channels_match_canonical_tree(tmp_path):
    first = build_release.build(tmp_path / "first")
    second = build_release.build(tmp_path / "second")
    first_manifest = Path(first["manifest"])
    second_manifest = Path(second["manifest"])

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    result = validate_release.validate(first_manifest)
    assert result["status"] == "passed"
    assert len(set(result["archives"].values())) == 1


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("cachebuster", "stale", "release_cachebuster_stale"),
        ("canonical_skill_tree_sha256", "0" * 64, "release_skill_tree_drift"),
        ("bootstrap_lock_sha256", "0" * 64, "release_bootstrap_lock_drift"),
        ("licenses", [], "release_licenses_missing"),
    ],
)
def test_release_validation_fails_closed_on_manifest_drift(tmp_path, field, value, reason):
    result = build_release.build(tmp_path)
    manifest = Path(result["manifest"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(validate_release.ReleaseValidationError, match=reason):
        validate_release.validate(manifest)
