from __future__ import annotations

import contextlib
import io
import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.runtime_config import RuntimeConfigError, load_runtime_config


PROPERTY_SETTINGS = settings(
    max_examples=100,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
_SAFE_TEXT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=24
)
_LEGACY_PROFILE = st.one_of(
    _SAFE_TEXT.map(lambda model: {"model": model}),
    _SAFE_TEXT.map(
        lambda host: {"endpoint_origin": f"https://{host}.example.com"}
    ),
    st.tuples(_SAFE_TEXT, _SAFE_TEXT).map(
        lambda values: {
            "endpoint_origin": f"https://{values[0]}.example.com",
            "model": values[1],
        }
    ),
)


@st.composite
def development_config_documents(draw: st.DrawFn) -> dict[str, Any]:
    if draw(st.booleans()):
        document: dict[str, Any] = {"schema_version": 1}
        if draw(st.booleans()):
            document["max_concurrent_workers"] = draw(st.integers(1, 16))
        if draw(st.booleans()):
            document["max_run_bytes"] = draw(
                st.integers(1024**2, 100 * 1024**3)
            )
        return document

    profiles = draw(
        st.dictionaries(
            st.sampled_from(("openai", "openai-compatible", "atlascloud")),
            _LEGACY_PROFILE,
            min_size=1,
            max_size=3,
        )
    )
    return {"schema_version": 1, "provider_profiles": profiles}


def _file_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@PROPERTY_SETTINGS
@given(
    document=development_config_documents(),
    credential_canary=st.binary(min_size=32, max_size=48).map(
        lambda value: f"credential-canary-{value.hex()}"
    ),
)
def test_property_34_development_config_reset_never_guesses_or_leaks(
    document: dict[str, Any], credential_canary: str
) -> None:
    """**Validates: Requirements 18.3, 18.4**"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        config_path = home / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        unknown_credential = home / "credentials" / "unowned-development-item"
        unknown_credential.parent.mkdir()
        unknown_credential.write_text(credential_canary, encoding="utf-8")
        before = _file_tree(home)

        stdout = io.StringIO()
        stderr = io.StringIO()
        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        errors: list[RuntimeConfigError] = []
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                for _ in range(2):
                    with pytest.raises(RuntimeConfigError) as captured:
                        load_runtime_config(
                            home=home,
                            environ={"LEGACY_PROVIDER_KEY": credential_canary},
                        )
                    errors.append(captured.value)
        finally:
            root_logger.removeHandler(handler)

        assert [error.reason_code for error in errors] == [
            "development_config_reset_required",
            "development_config_reset_required",
        ]
        assert all(error.pointer is None for error in errors)
        assert _file_tree(home) == before
        assert credential_canary not in config_path.read_text(encoding="utf-8")

        observable_output = "".join(
            (stdout.getvalue(), stderr.getvalue(), log_output.getvalue())
        ) + "".join(str(error) + repr(error) for error in errors)
        assert credential_canary not in observable_output
