from __future__ import annotations

from leo_ppt_generator import cli


def parse(*arguments: str):
    return cli.build_parser().parse_args(arguments)


def test_every_planned_stable_command_parses_without_legacy_flags():
    commands = [
        ("doctor", "--route", "generate"),
        (
            "setup",
            "--route",
            "generate",
            "--host-imagegen",
            "available",
            "--json",
        ),
        (
            "backend",
            "create",
            "--provider",
            "openai",
            "--mode",
            "generate",
            "--output",
            "backend.json",
        ),
        ("backend", "validate", "backend.json"),
        (
            "run",
            "create",
            "--route",
            "generate",
            "--input",
            "project/sources/input.md",
            "--project-root",
            "project",
            "--output",
            "project/runs/run",
            "--backend-contract",
            "project/contracts/backend.json",
            "--idempotency-key",
            "request-1",
        ),
        ("run", "status", "run", "--json"),
        ("run", "diagnose", "run", "--json"),
        ("run", "operation", "run", "--id", "operation-1", "--json"),
        ("run", "retry", "run", "--from-failed-pages"),
        ("run", "cancel", "run", "--wait-workers"),
        ("run", "cleanup", "run", "--scope", "temp", "--dry-run"),
        ("run", "cleanup", "run", "--scope", "input", "--apply", "preview.json"),
        ("image", "prepare", "run"),
        (
            "image",
            "record",
            "run",
            "--slide",
            "slide_01",
            "--agent-id",
            "agent-1",
            "--result",
            "slide.png",
            "--expected-state-hash",
            "abc",
        ),
        ("image", "assemble", "run", "--rebuild"),
        ("editable", "prepare", "run", "--pages", "1,3"),
        ("editable", "next", "run", "--json"),
        (
            "editable",
            "dispatch",
            "run",
            "--page",
            "page_001",
            "--agent-id",
            "agent-1",
            "--prompt-file",
            "prompt.md",
        ),
        (
            "editable",
            "record",
            "run",
            "--page",
            "page_001",
            "--agent-id",
            "agent-1",
            "--expected-state-hash",
            "abc",
        ),
        ("editable", "reset", "run", "--page", "page_001", "--confirm-lost"),
        ("editable", "finalize", "run"),
        ("upgrade", "finalize", "run", "--allow-partial"),
    ]
    parsed = [parse(*command) for command in commands]
    assert len(parsed) == len(commands)
