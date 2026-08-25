from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from leo_ppt_generator.upstream_bridge import (
    CODEX_TOOLS,
    UpstreamBridgeError,
    _current_cli_prefix,
    _isolated_env,
    _run,
    run_upstream,
)

EXPECTED_CODEX_TOOLS = {
    "assemble",
    "image",
    "prepare",
    "record-blocker",
    "record-dispatch",
    "record-result",
    "remove-chroma-key",
    "status",
}
EXPECTED_EDITABLE_COMMANDS = {
    "setup",
    "doctor",
    "config",
    "prepare",
    "run",
    "formula",
    "page",
    "image",
}


def test_vendor_subprocess_environment_never_writes_into_the_skill_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    assert _isolated_env(str(tmp_path))["PYTHONDONTWRITEBYTECODE"] == "1"


def test_upstream_bridge_consumes_frozen_backend_contract_and_returns_redacted_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from tests.backend_fixtures import backend_contract

    monkeypatch.setenv("OPENAI_API_KEY", "bridge-secret")
    contract = tmp_path / "backend-contract.json"
    contract.write_text(json.dumps(backend_contract("openai")), encoding="utf-8")

    result = run_upstream(
        "codex-ppt",
        ["prepare", "--help"],
        backend_contract=contract,
    )

    assert result["returncode"] == 0
    assert result["execution_receipt"]["provider"] == "openai"
    assert "bridge-secret" not in json.dumps(result)


def test_vendor_subprocess_timeout_is_observable_and_terminates_process():
    result = _run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout_seconds=0.05,
    )
    assert result["timed_out"] is True
    assert result["stderr"] == "upstream_subprocess_timeout"


def test_upstream_command_hints_use_proven_absolute_current_cli(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LEO_PPT_CLI_PROG", sys.executable)
    resolved = str(Path(sys.executable).resolve())
    assert _current_cli_prefix("editable-ppt") == f"{resolved} upstream editable-ppt --"
    result = run_upstream("editable-ppt", ["--help"])
    assert f"{resolved} upstream editable-ppt --" in result["stdout"]


def test_upstream_command_hints_reject_unproven_cli_override(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LEO_PPT_CLI_PROG", "leo-ppt --unsafe")
    assert _current_cli_prefix("editable-ppt") == "leo-ppt upstream editable-ppt --"


def test_every_codex_executable_tool_is_reachable_through_one_cli_bridge():
    assert set(CODEX_TOOLS) == EXPECTED_CODEX_TOOLS
    for tool in sorted(EXPECTED_CODEX_TOOLS):
        result = run_upstream("codex-ppt", [tool, "--help"])
        assert result["returncode"] == 0, (tool, result)
        assert "usage:" in result["stdout"]


def test_complete_editable_command_tree_is_reachable_through_one_cli_bridge():
    result = run_upstream("editable-ppt", ["--help"])
    assert result["returncode"] == 0
    help_text = result["stdout"]
    for command in EXPECTED_EDITABLE_COMMANDS:
        assert command in help_text
    assert "editppt " not in help_text
    assert "leo-ppt upstream editable-ppt --" in help_text


def test_legacy_setup_and_raw_config_are_adapted_to_managed_owners():
    setup = run_upstream("editable-ppt", ["setup", "--help"])
    config = run_upstream("editable-ppt", ["config", "--help"])
    assert setup["disposition"] == "adapted"
    assert "runtime_manager.py" in setup["stdout"]
    assert config["disposition"] == "adapted"
    assert "backend-contract-v1" in config["stdout"]
    with pytest.raises(UpstreamBridgeError, match="raw_credential_configuration_forbidden"):
        run_upstream("editable-ppt", ["config", "--api-key", "secret"])
    with pytest.raises(UpstreamBridgeError, match="raw_credential_configuration_forbidden"):
        run_upstream("editable-ppt", ["config", "--paddle-ocr-token", "secret"])
    with pytest.raises(UpstreamBridgeError, match="raw_credential_configuration_forbidden"):
        run_upstream("editable-ppt", ["config", "--import-codex-ppt"])


@pytest.mark.parametrize(
    ("group", "commands"),
    [
        ("run", {"next", "status", "backend", "dispatch", "record", "reset", "hints", "finalize"}),
        ("page", {"hints", "build", "contact-sheet", "validate"}),
        ("image", {"generate", "edit", "import", "process-sheet"}),
        ("formula", {"render-latex"}),
    ],
)
def test_every_editable_nested_tool_is_visible(group: str, commands: set[str]):
    result = run_upstream("editable-ppt", [group, "--help"])
    assert result["returncode"] == 0, result
    for command in commands:
        assert command in result["stdout"]


def test_page_worker_prompt_builder_uses_current_cli(tmp_path: Path):
    run = tmp_path / "run"
    page = run / "pages" / "page_001"
    page.mkdir(parents=True)
    (run / "page_jobs.json").write_text(
        json.dumps({"pages": [{"page_id": "page_001", "page_dir": "pages/page_001"}]}),
        encoding="utf-8",
    )
    (page / "page_request.json").write_text(
        json.dumps({"source_image": str(page / "source.png")}),
        encoding="utf-8",
    )
    script = (
        Path(__file__).resolve().parents[2]
        / "skills/leo-ppt-generator/scripts/build-page-worker-prompt.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            str(run),
            "--page",
            "1",
            "--cli",
            sys.executable,
            "--out",
            "worker-prompt.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    resolved_cli = str(Path(sys.executable).resolve())
    assert payload["dispatch_command_template"].startswith(
        f"{resolved_cli} upstream editable-ppt -- run dispatch"
    )
    prompt = Path(payload["prompt_file"]).read_text(encoding="utf-8")
    assert f'"{resolved_cli}" upstream editable-ppt -- page build' in prompt
    assert "{{LEO_PPT}}" not in prompt


def test_page_worker_prompt_builder_requires_absolute_managed_cli(tmp_path: Path):
    run = tmp_path / "run"
    page = run / "pages" / "page_001"
    page.mkdir(parents=True)
    (run / "page_jobs.json").write_text(
        json.dumps({"pages": [{"page_id": "page_001", "page_dir": "pages/page_001"}]}),
        encoding="utf-8",
    )
    (page / "page_request.json").write_text("{}\n", encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[2]
        / "skills/leo-ppt-generator/scripts/build-page-worker-prompt.py"
    )

    missing = subprocess.run(
        [sys.executable, str(script), str(run), "--page", "1", "--out", "worker.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    relative = subprocess.run(
        [
            sys.executable,
            str(script),
            str(run),
            "--page",
            "1",
            "--cli",
            "leo-ppt",
            "--out",
            "worker.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert missing.returncode != 0
    assert "--cli" in missing.stderr
    assert relative.returncode != 0
    assert "must be the absolute path" in relative.stderr
    assert not (page / "worker.md").exists()


def test_page_worker_prompt_builder_rejects_page_dir_outside_run(tmp_path: Path):
    run = tmp_path / "run"
    outside = tmp_path / "outside"
    run.mkdir()
    outside.mkdir()
    (outside / "page_request.json").write_text("{}\n", encoding="utf-8")
    (run / "page_jobs.json").write_text(
        json.dumps({"pages": [{"page_id": "page_001", "page_dir": str(outside)}]}),
        encoding="utf-8",
    )
    script = (
        Path(__file__).resolve().parents[2]
        / "skills/leo-ppt-generator/scripts/build-page-worker-prompt.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            str(run),
            "--page",
            "1",
            "--cli",
            sys.executable,
            "--out",
            "worker.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Page directory must live inside run dir" in completed.stderr
    assert not (outside / "worker.md").exists()


def test_editable_bridge_rejects_office_before_upstream_parser(tmp_path: Path):
    office = tmp_path / "unsafe.pptx"
    office.write_bytes(b"not-a-zip")
    with pytest.raises(UpstreamBridgeError, match="untrusted_office_input"):
        run_upstream("editable-ppt", ["prepare", str(office)])
    with pytest.raises(UpstreamBridgeError, match="untrusted_office_input"):
        run_upstream("editable-ppt", ["prepare", str(office), "--office-trusted"])


def test_codex_prompt_asset_dispatch_result_blocker_and_status_flow(tmp_path: Path):
    asset = tmp_path / "required.png"
    asset.write_bytes(b"required-asset")
    deck = tmp_path / "deck"
    spec = tmp_path / "deck_spec.json"
    spec.write_text(
        json.dumps(
            {
                "deck_name": "audit",
                "selected_image_backend": "built-in image tool",
                "sample_generation_method": {
                    "backend_used": "built-in image tool",
                    "tool_name": "image_gen",
                    "mode": "generate",
                },
                "style": {"name": "audit-style", "visual_direction": "clean"},
                "slides": [
                    {
                        "number": 1,
                        "title": "Evidence",
                        "key_points": ["Exact claim"],
                        "required_images": [
                            {"path": str(asset), "role": "strict input asset"}
                        ],
                    },
                    {"number": 2, "title": "Blocked", "key_points": ["Reason"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    prepared = run_upstream(
        "codex-ppt", ["prepare", "--spec", str(spec), "--out-dir", str(deck)]
    )
    assert prepared["returncode"] == 0, prepared
    jobs = json.loads((deck / "slide_jobs.json").read_text(encoding="utf-8"))
    prompt = json.loads((deck / "prompts/slide_01.json").read_text(encoding="utf-8"))
    assert jobs["selected_backend"] == "built-in image tool"
    assert prompt["input_images"][0]["path"] == str(asset)
    assert prompt["generation_contract"]["must_match_sample_generation_method"] is True

    dispatched = run_upstream(
        "codex-ppt",
        [
            "record-dispatch",
            str(deck),
            "--slide",
            "1",
            "--agent-id",
            "worker-1",
            "--prompt-file",
            "prompts/slide_01.json",
        ],
    )
    assert dispatched["returncode"] == 0, dispatched
    generated = tmp_path / "generated.png"
    generated.write_bytes(b"generated-image")
    recorded = run_upstream(
        "codex-ppt",
        [
            "record-result",
            str(deck),
            "--slide",
            "1",
            "--agent-id",
            "worker-1",
            "--backend-used",
            "built-in image tool",
            "--selected-source",
            str(generated),
            "--qa-note",
            "passed",
        ],
    )
    assert recorded["returncode"] == 0, recorded
    blocked = run_upstream(
        "codex-ppt",
        ["record-blocker", str(deck), "--slide", "2", "--reason", "provider unavailable"],
    )
    assert blocked["returncode"] == 0, blocked
    status = run_upstream("codex-ppt", ["status", str(deck), "--json"])
    assert status["returncode"] == 0, status
    assert status["stdout"]["counts"] == {"recorded": 1, "blocked": 1}


def test_codex_prompt_body_variant_overrides_dark_cover_reference(tmp_path: Path):
    cover = tmp_path / "dark-cover.png"
    cover.write_bytes(b"dark-cover")
    deck = tmp_path / "deck"
    spec = tmp_path / "deck_spec.json"
    spec.write_text(
        json.dumps(
            {
                "deck_name": "body-theme-regression",
                "selected_image_backend": "built-in image tool",
                "style": {
                    "name": "dark blueprint",
                    "visual_direction": "white/cyan linework on dark navy",
                    "canvas": {"background": "dark navy #0F1B33"},
                },
                "style_variants": {
                    "body": {
                        "canvas": {"background": "off-white #F5F7FA"},
                        "rules": ["MUST use the off-white body canvas; do not use dark navy."],
                        "reference_inheritance": ["grid density", "line weight", "geometry"],
                        "reference_exclusions": ["background", "palette", "foreground colors"],
                    }
                },
                "approved_style_reference": {
                    "path": str(cover),
                    "role": "approved dark cover reference",
                },
                "slides": [
                    {
                        "number": 1,
                        "title": "Body page",
                        "style_variant": "body",
                        "key_points": ["Exact claim"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    prepared = run_upstream(
        "codex-ppt", ["prepare", "--spec", str(spec), "--out-dir", str(deck)]
    )

    assert prepared["returncode"] == 0, prepared
    prompt = json.loads((deck / "prompts/slide_01.json").read_text(encoding="utf-8"))["prompt"]
    assert '"name": "body"' in prompt
    assert "off-white #F5F7FA" in prompt
    assert "MUST use the off-white body canvas; do not use dark navy." in prompt
    assert "Match only: grid density, line weight, geometry." in prompt
    assert "Do not inherit: background, palette, foreground colors." in prompt
    assert "overall visual identity" not in prompt
