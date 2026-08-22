from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import settings

from tests import conftest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "skills/leo-ppt-generator/runtime"


def _requirements(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def test_hypothesis_is_exactly_pinned_as_test_only_dependency() -> None:
    """Validates: Requirements 18.5."""
    pyproject = tomllib.loads((RUNTIME / "pyproject.toml").read_text(encoding="utf-8"))

    assert "Hypothesis==6.165.5" in pyproject["project"]["optional-dependencies"]["test"]
    assert all(
        not dependency.lower().startswith("hypothesis")
        for dependency in pyproject["project"]["dependencies"]
    )
    assert importlib.metadata.version("hypothesis") == "6.165.5"


def test_platform_test_constraints_pin_hypothesis_without_runtime_leakage() -> None:
    """Validates: Requirements 18.5."""
    constraints = RUNTIME / "constraints"

    for platform in ("darwin-arm64", "darwin-x86_64", "win32-amd64"):
        test_requirements = _requirements(
            constraints / f"test-py312-{platform}.txt"
        )
        runtime_requirements = _requirements(constraints / f"py312-{platform}.txt")
        assert test_requirements == [
            f"-r py312-{platform}.txt",
            "Hypothesis==6.165.5",
        ]
        assert all(
            not requirement.lower().startswith("hypothesis")
            for requirement in runtime_requirements
        )


def test_ci_profile_is_deterministic_and_runs_at_least_100_examples() -> None:
    """Validates: Requirements 18.5."""
    profile = settings.get_profile(conftest.HYPOTHESIS_CI_PROFILE)

    assert profile.max_examples >= 100
    assert profile.derandomize is True
    assert profile.database is None
    assert profile.deadline is None


def test_collection_rejects_property_with_too_few_examples() -> None:
    """Validates: Requirements 18.5."""

    def under_configured_property() -> None:
        pass

    under_configured_property.hypothesis = SimpleNamespace()  # type: ignore[attr-defined]
    under_configured_property._hypothesis_internal_use_settings = settings(  # type: ignore[attr-defined]
        max_examples=99
    )
    item = SimpleNamespace(
        obj=under_configured_property,
        nodeid="test_property_toolchain.py::under_configured_property",
    )

    with pytest.raises(pytest.UsageError, match="至少 100 个 examples"):
        conftest.pytest_collection_modifyitems([item])  # type: ignore[list-item]
