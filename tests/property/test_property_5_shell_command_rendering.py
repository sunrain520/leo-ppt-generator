# Feature: guided-provider-config, Property 5: Shell command rendering
# round-trips safely

from __future__ import annotations

import shlex

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.config.reason_codes import (
    ActionIntent,
    CommandRenderer,
    ConfigCommandVerb,
    PrimaryActionKind,
    ReasonCode,
    ShellKind,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)

VERBS = tuple(ConfigCommandVerb)


@st.composite
def posix_paths(draw: st.DrawFn):
    return draw(
        st.text(
            alphabet=st.characters(
                blacklist_characters="\x00'",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=64,
        ).map(lambda value: f"/usr/local/bin/{value}".replace("//", "/"))
    )


@st.composite
def powershell_paths(draw: st.DrawFn):
    return draw(
        st.text(
            alphabet=st.characters(
                blacklist_characters="\x00",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=64,
        ).map(lambda value: f"C:\\Program Files\\{value}")
    )


@PROPERTY_SETTINGS
@given(path=posix_paths(), verb=st.sampled_from(VERBS))
def test_property_5_posix_command_roundtrips(path, verb):
    """**Validates: Requirements 2.13, 8.7, 10.7**"""
    renderer = CommandRenderer(ShellKind.POSIX)
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=ReasonCode.CONFIG_INVALID,
        command_verb=verb,
    )
    action = renderer.render(intent, cli_path=path)
    assert action is not None and action.command is not None
    tokens = shlex.split(action.command)
    assert tokens[0] == path
    assert tokens[1:] == _verb_args(verb)


@PROPERTY_SETTINGS
@given(path=posix_paths())
def test_property_5_posix_quotes_single_quotes(path):
    """**Validates: Requirements 2.13, 10.7**"""
    renderer = CommandRenderer(ShellKind.POSIX)
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=ReasonCode.CONFIG_INVALID,
        command_verb=ConfigCommandVerb.REPAIR,
    )
    action = renderer.render(intent, cli_path=path)
    tokens = shlex.split(action.command)
    assert tokens[0] == path
    # 任何含单引号或空格的路径都保持为一个 token。
    assert len(tokens) == 3


@PROPERTY_SETTINGS
@given(path=powershell_paths(), verb=st.sampled_from(VERBS))
def test_property_5_powershell_command_roundtrips(path, verb):
    """**Validates: Requirements 2.13, 8.7, 10.7**"""
    renderer = CommandRenderer(ShellKind.POWERSHELL)
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=ReasonCode.CONFIG_INVALID,
        command_verb=verb,
    )
    action = renderer.render(intent, cli_path=path)
    assert action is not None and action.command is not None
    assert action.command.startswith("& ")
    # PowerShell call operator + 单引号转义：路径中的单引号被翻倍。
    body = action.command[2:]
    assert body.startswith("'")
    doubled = path.replace("'", "''")
    assert body.startswith(f"'{doubled}'")


def test_property_5_cli_path_unresolved_uses_launcher():
    renderer = CommandRenderer(ShellKind.POSIX)
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=ReasonCode.CLI_PATH_UNRESOLVED,
        command_verb=None,
    )
    action = renderer.render(
        intent, launcher_path="/opt/leo/runtime-manager", launcher_args=("ensure",)
    )
    assert action is not None and action.command is not None
    tokens = shlex.split(action.command)
    assert tokens[0] == "/opt/leo/runtime-manager"
    assert tokens[1] == "ensure"


def test_property_5_resolved_cli_must_not_use_launcher():
    renderer = CommandRenderer(ShellKind.POSIX)
    intent = ActionIntent(
        kind=PrimaryActionKind.RUN_CLI,
        reason_code=ReasonCode.CONFIG_INVALID,
        command_verb=ConfigCommandVerb.REPAIR,
    )
    import pytest

    with pytest.raises(ValueError):
        renderer.render(
            intent,
            cli_path="/usr/local/bin/leo-ppt",
            launcher_path="/opt/leo/runtime-manager",
        )


def _verb_args(verb: ConfigCommandVerb) -> list[str]:
    return {
        ConfigCommandVerb.CONFIG: ["config"],
        ConfigCommandVerb.VERIFY: ["config", "verify"],
        ConfigCommandVerb.REPAIR: ["config", "repair"],
        ConfigCommandVerb.CHANGE: ["config", "change"],
    }[verb]
