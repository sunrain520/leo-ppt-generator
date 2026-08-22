from __future__ import annotations

import shlex

import pytest

from leo_ppt_generator.config.models import PrimaryActionKind
from leo_ppt_generator.config.reason_codes import (
    REASON_CATALOG,
    ActionIntent,
    CommandRenderer,
    ConfigCommandVerb,
    ReasonCode,
    ShellKind,
    reason_definition,
)


def test_reason_catalog_is_total_and_has_one_typed_default_action():
    assert set(REASON_CATALOG) == set(ReasonCode)
    assert len(REASON_CATALOG) == len(ReasonCode)
    for code, definition in REASON_CATALOG.items():
        assert definition.code is code
        if definition.user_repairable:
            assert definition.default_action is not None
            assert definition.default_action.reason_code is code

    rate_limit = reason_definition(ReasonCode.PROVIDER_RATE_LIMITED)
    assert rate_limit.default_action is not None
    assert rate_limit.default_action.kind is PrimaryActionKind.WAIT_AND_RETRY


def test_action_intent_only_allows_command_verbs_for_run_cli():
    with pytest.raises(ValueError, match="requires a config command verb"):
        ActionIntent(
            kind=PrimaryActionKind.RUN_CLI,
            reason_code=ReasonCode.CONFIG_INVALID,
        )
    with pytest.raises(ValueError, match="only run_cli"):
        ActionIntent(
            kind=PrimaryActionKind.START_TASK,
            reason_code=ReasonCode.PROVIDER_VERIFICATION_NOT_RUN,
            command_verb=ConfigCommandVerb.CONFIG,
        )
    with pytest.raises(ValueError, match="must not invent"):
        ActionIntent(
            kind=PrimaryActionKind.RUN_CLI,
            reason_code=ReasonCode.CLI_PATH_UNRESOLVED,
            command_verb=ConfigCommandVerb.REPAIR,
        )


def test_posix_renderer_round_trips_absolute_cli_path_and_arguments():
    intent = reason_definition(ReasonCode.CONFIG_INVALID).default_action
    action = CommandRenderer(ShellKind.POSIX).render(
        intent,
        cli_path="/opt/Leo's 幻灯片/leo-ppt",
    )
    assert action is not None
    assert shlex.split(action.command or "") == [
        "/opt/Leo's 幻灯片/leo-ppt",
        "config",
        "repair",
    ]


def test_powershell_renderer_uses_call_operator_and_single_quote_escaping():
    intent = reason_definition(ReasonCode.PROVIDER_SELECTION_REQUIRED).default_action
    action = CommandRenderer(ShellKind.POWERSHELL).render(
        intent,
        cli_path="C:\\Program Files\\Leo's 幻灯片\\leo-ppt.exe",
    )
    assert action is not None
    assert action.command == (
        "& 'C:\\Program Files\\Leo''s 幻灯片\\leo-ppt.exe' 'config'"
    )


def test_renderer_rejects_relative_paths_and_never_fakes_unresolved_cli():
    renderer = CommandRenderer(ShellKind.POSIX)
    repair = reason_definition(ReasonCode.CONFIG_INVALID).default_action
    with pytest.raises(ValueError, match="absolute path"):
        renderer.render(repair, cli_path="bin/leo-ppt")

    unresolved = reason_definition(ReasonCode.CLI_PATH_UNRESOLVED).default_action
    with pytest.raises(ValueError, match="must not use or invent"):
        renderer.render(unresolved, cli_path="/invented/leo-ppt")
    action = renderer.render(
        unresolved,
        launcher_path="/Applications/Leo PPT/runtime-manager",
        launcher_args=("ensure",),
    )
    assert action is not None
    assert shlex.split(action.command or "") == [
        "/Applications/Leo PPT/runtime-manager",
        "ensure",
    ]


def test_non_cli_and_no_action_never_render_a_command():
    renderer = CommandRenderer(ShellKind.POSIX)
    start = reason_definition(ReasonCode.PROVIDER_VERIFICATION_NOT_RUN).default_action
    action = renderer.render(start)
    assert action is not None
    assert action.to_dict() == {"kind": "start_task"}
    assert renderer.render(None) is None


def test_renderer_renders_module_launcher_without_treating_it_as_cli_path():
    intent = reason_definition(ReasonCode.CONFIG_INVALID).default_action
    action = CommandRenderer(ShellKind.POSIX).render_prefixed(
        intent,
        executable="/opt/Leo's Python/bin/python3",
        prefix_arguments=("-m", "leo_ppt_generator"),
    )

    assert action is not None
    assert shlex.split(action.command or "") == [
        "/opt/Leo's Python/bin/python3",
        "-m",
        "leo_ppt_generator",
        "config",
        "repair",
    ]
