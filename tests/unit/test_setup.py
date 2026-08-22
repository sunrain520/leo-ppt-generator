from __future__ import annotations

import json

import pytest
from leo_ppt_generator import cli, setup


def parse(*arguments: str):
    return cli.build_parser().parse_args(arguments)


def doctor_fixture(
    *,
    local_status: str = "ready",
    reason_code: str = "ready",
    openai: str = "missing",
    atlascloud: str = "missing",
    paddleocr: str = "missing",
) -> dict:
    return {
        "status": local_status,
        "reason_code": reason_code,
        "readiness_summary": {
            "local_mechanism": "blocked" if local_status == "blocked" else "ready"
        },
        "credential_references": {
            "builtin-imagegen": {
                "status": "host_check_required",
                "reference_type": "host-managed",
                "evidence_refs": ["doctor://credential/builtin-imagegen"],
            },
            "openai": {
                "status": openai,
                "reference_type": "environment",
                "evidence_refs": ["doctor://credential/openai"],
            },
            "atlascloud": {
                "status": atlascloud,
                "reference_type": "environment",
                "evidence_refs": ["doctor://credential/atlascloud"],
            },
            "paddleocr": {
                "status": paddleocr,
                "reference_type": "environment",
                "evidence_refs": ["doctor://credential/paddleocr"],
            },
        },
        "evidence_refs": ["doctor://current"],
        "warnings": [],
    }


@pytest.mark.parametrize(
    "host_status,expected_status,selected,action",
    [
        ("available", "ready", "builtin-imagegen", None),
        ("unavailable", "action_required", None, "configure_image_provider"),
        ("unknown", "action_required", None, "declare_host_image_capability"),
    ],
)
def test_setup_respects_explicit_host_capability_without_false_green(
    monkeypatch, host_status, expected_status, selected, action
):
    monkeypatch.setattr(setup, "doctor_report", lambda _route: doctor_fixture())

    report = setup.build_setup_report("generate", host_imagegen=host_status)

    assert report["status"] == expected_status
    assert report["selected_provider"] == selected
    assert report["primary_action"] is None if action is None else report["primary_action"]["id"] == action
    assert report["host_capabilities"]["image_generation"] == host_status


@pytest.mark.parametrize(
    "openai,atlascloud,expected_status,action",
    [
        ("missing", "missing", "action_required", "configure_image_provider"),
        ("available", "missing", "choice_required", "confirm_provider"),
        ("available", "available", "choice_required", "choose_provider"),
    ],
)
def test_setup_handles_zero_one_or_two_external_providers(
    monkeypatch, openai, atlascloud, expected_status, action
):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai=openai, atlascloud=atlascloud),
    )

    report = setup.build_setup_report("generate", host_imagegen="unavailable")

    assert report["status"] == expected_status
    assert report["primary_action"]["id"] == action
    assert sum(option["credential_status"] == "available" for option in report["provider_options"]) == (
        int(openai == "available") + int(atlascloud == "available")
    )


def test_setup_hides_builtin_when_host_is_unavailable_and_traces_recommendations(
    monkeypatch,
):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available"),
    )

    report = setup.build_setup_report("generate", host_imagegen="unavailable")

    assert [option["provider"] for option in report["provider_options"]] == [
        "openai",
        "atlascloud",
    ]
    openai = report["provider_options"][0]
    assert openai["credential_reference_type"] == "environment"
    assert openai["evidence_refs"] == ["doctor://credential/openai"]


@pytest.mark.parametrize(
    "route,expected",
    [
        ("generate", ["generate"]),
        ("direct-editable", ["edit"]),
        ("upgrade-full", ["edit"]),
        ("upgrade-selected", ["edit"]),
    ],
)
def test_setup_uses_the_four_route_capability_matrix(monkeypatch, route, expected):
    monkeypatch.setattr(setup, "doctor_report", lambda _route: doctor_fixture())

    report = setup.build_setup_report(route, host_imagegen="unknown")

    assert report["route_capabilities"] == expected


def test_setup_blocks_when_only_available_provider_lacks_required_mask(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(atlascloud="available"),
    )

    report = setup.build_setup_report(
        "generate",
        host_imagegen="unavailable",
        required_image_capabilities={"mask"},
    )

    assert report["route_capabilities"] == ["generate", "mask"]
    assert [option["provider"] for option in report["provider_options"]] == ["openai"]
    assert report["reason_code"] == "provider_capability_required"
    assert report["primary_action"]["id"] == "select_capable_provider"


def test_setup_does_not_recommend_an_explicit_but_incapable_provider(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(atlascloud="available"),
    )

    report = setup.build_setup_report(
        "generate",
        host_imagegen="unavailable",
        selected_provider="atlascloud",
        required_image_capabilities={"mask"},
    )

    assert report["reason_code"] == "provider_capability_required"
    assert "--provider openai" in report["primary_action"]["command"]
    assert "atlascloud" not in report["primary_action"]["command"]


def test_ocr_is_delayed_until_an_editable_stage_and_never_blocks_setup(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available", paddleocr="missing"),
    )

    generate = setup.build_setup_report("generate", host_imagegen="unavailable")
    editable = setup.build_setup_report(
        "direct-editable",
        host_imagegen="unavailable",
        ocr_requirement="editable_text_hints",
    )

    assert generate["optional_services"] == []
    assert all(option["provider"] != "paddleocr" for option in generate["provider_options"])
    assert editable["optional_services"] == [
        {
            "service": "paddleocr",
            "purpose": "editable_text_hints",
            "credential_status": "missing",
            "credential_reference_type": "environment",
            "required": False,
            "fallback": "builtin-ink",
            "evidence_refs": ["doctor://credential/paddleocr"],
        }
    ]
    assert editable["reason_code"] == "provider_confirmation_required"


def test_setup_accepts_only_an_explicit_available_external_provider(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available", atlascloud="available"),
    )

    report = setup.build_setup_report(
        "generate", host_imagegen="unavailable", selected_provider="openai"
    )

    assert report["status"] == "ready"
    assert report["selected_provider"] == "openai"
    assert report["primary_action"] is None


def test_setup_does_not_offer_auth_for_unavailable_builtin_provider(monkeypatch):
    monkeypatch.setattr(setup, "doctor_report", lambda _route: doctor_fixture())

    report = setup.build_setup_report(
        "generate",
        host_imagegen="unavailable",
        selected_provider="builtin-imagegen",
    )

    assert report["reason_code"] == "host_image_capability_unavailable"
    assert report["primary_action"]["id"] == "select_external_provider"
    assert "auth add --provider builtin-imagegen" not in report["primary_action"]["command"]


@pytest.mark.parametrize(
    "route,doctor,expected_reason,action",
    [
        ("arbitrary", doctor_fixture(local_status="blocked", reason_code="unknown_route"), "unknown_route", "choose_supported_route"),
        ("generate", doctor_fixture(local_status="blocked", reason_code="config_schema_too_new"), "setup_local_mechanism_blocked", "repair_runtime_config"),
        ("generate", doctor_fixture(openai="resolver_unavailable"), "credential_resolver_unavailable", "enable_credential_resolver"),
    ],
)
def test_setup_propagates_owner_failures_with_one_primary_action(
    monkeypatch, route, doctor, expected_reason, action
):
    monkeypatch.setattr(setup, "doctor_report", lambda _route: doctor)

    report = setup.build_setup_report(route, host_imagegen="unavailable")

    assert report["reason_code"] == expected_reason
    assert report["primary_action"]["id"] == action
    assert len([report["primary_action"]]) == 1
    assert report["details"]["owner_reason_codes"] == [doctor["reason_code"]]
    if route == "arbitrary":
        assert "--route arbitrary" not in report["primary_action"]["command"]


def test_setup_human_and_json_outputs_are_rendered_from_the_same_report(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available", atlascloud="available"),
    )
    report = cli.dispatch(
        parse(
            "setup",
            "--route",
            "generate",
            "--host-imagegen",
            "unavailable",
        )
    )

    human = setup.render_setup_report(report)
    machine = json.loads(setup.render_setup_json(report))

    assert machine == report
    assert f"状态: {report['status']}" in human
    assert f"原因: {report['reason_code']}" in human
    assert f"下一步: {report['primary_action']['command']}" in human
    for option in report["provider_options"]:
        assert option["provider"] in human


def test_setup_schema_version_is_fail_closed():
    with pytest.raises(setup.SetupContractError, match="setup_schema_version_unsupported"):
        setup.validate_setup_report({"schema_version": 2})


def test_setup_main_uses_nonzero_exit_for_non_ready_state(monkeypatch, capsys):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available", atlascloud="available"),
    )

    exit_code = cli.main(
        ["setup", "--route", "generate", "--host-imagegen", "unavailable"]
    )

    assert exit_code == 2
    assert "状态: choice_required" in capsys.readouterr().out


def test_setup_cli_forwards_task_capability_and_ocr_stage(monkeypatch):
    monkeypatch.setattr(
        setup,
        "doctor_report",
        lambda _route: doctor_fixture(openai="available", paddleocr="missing"),
    )

    report = cli.dispatch(
        parse(
            "setup",
            "--route",
            "direct-editable",
            "--host-imagegen",
            "unavailable",
            "--require-mask",
            "--ocr-requirement",
            "editable_text_hints",
        )
    )

    assert report["route_capabilities"] == ["edit", "mask"]
    assert report["optional_services"][0]["fallback"] == "builtin-ink"


def test_setup_does_not_persist_a_second_readiness_state(tmp_path, monkeypatch):
    home = tmp_path / "leo-home"
    home.mkdir()
    monkeypatch.setenv("LEO_PPT_HOME", str(home))

    report = setup.build_setup_report("generate", host_imagegen="available")

    assert report["status"] == "ready"
    assert list(home.iterdir()) == []


def test_every_non_ready_setup_outcome_has_exactly_one_complete_primary_action(
    monkeypatch,
):
    cases = [
        ("arbitrary", "unavailable", None, doctor_fixture(local_status="blocked", reason_code="unknown_route")),
        ("generate", "unavailable", None, doctor_fixture(local_status="blocked", reason_code="config_schema_too_new")),
        ("generate", "unknown", None, doctor_fixture()),
        ("generate", "unavailable", None, doctor_fixture()),
        ("generate", "unavailable", None, doctor_fixture(openai="available")),
        ("generate", "unavailable", None, doctor_fixture(openai="available", atlascloud="available")),
        ("generate", "unavailable", "builtin-imagegen", doctor_fixture()),
        ("generate", "unavailable", "openai", doctor_fixture()),
        ("generate", "unavailable", "unknown-provider", doctor_fixture()),
        ("generate", "unavailable", None, doctor_fixture(openai="resolver_unavailable")),
    ]
    for route, host_status, provider, doctor in cases:
        monkeypatch.setattr(setup, "doctor_report", lambda _route, value=doctor: value)
        report = setup.build_setup_report(
            route, host_imagegen=host_status, selected_provider=provider
        )
        assert report["status"] != "ready"
        assert set(report["primary_action"]) == {"id", "command", "verification"}
        assert all(report["primary_action"].values())
