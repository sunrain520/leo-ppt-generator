from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from hypothesis import settings

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = REPO_ROOT / "skills/leo-ppt-generator/runtime/src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

MIN_PROPERTY_EXAMPLES = 100
HYPOTHESIS_CI_PROFILE = "ci"

settings.register_profile(
    HYPOTHESIS_CI_PROFILE,
    max_examples=MIN_PROPERTY_EXAMPLES,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
if os.environ.get("CI"):
    settings.load_profile(HYPOTHESIS_CI_PROFILE)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """拒绝降低任一 property test 的最小样本数。"""
    for item in items:
        test = getattr(item, "obj", None)
        if test is None or not hasattr(test, "hypothesis"):
            continue
        property_settings = getattr(
            test,
            "_hypothesis_internal_use_settings",
            settings.default,
        )
        if property_settings.max_examples < MIN_PROPERTY_EXAMPLES:
            raise pytest.UsageError(
                f"{item.nodeid} 必须运行至少 {MIN_PROPERTY_EXAMPLES} 个 examples"
            )
