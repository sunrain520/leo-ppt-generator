from __future__ import annotations

import json
from pathlib import Path

import pytest
from leo_ppt_generator.application.run_index import IdempotencyConflict, RunIndex
from leo_ppt_generator.contracts import ContractError

from tests.backend_fixtures import backend_contract


def write_backend(path: Path, *, backend: str = "fixture", mode: str = "generate") -> Path:
    path.write_text(
        json.dumps(backend_contract(backend, mode=mode)) + "\n",
        encoding="utf-8",
    )
    return path


def test_create_from_request_copies_and_freezes_inputs_and_replays(tmp_path):
    source = tmp_path / "brief.md"
    source.write_text("# Deck\n", encoding="utf-8")
    backend = write_backend(tmp_path / "backend.json")
    run_dir = tmp_path / "run"

    first = RunIndex.create_from_request(
        run_dir,
        route="generate",
        input_path=source,
        backend_contract_path=backend,
        runtime_identity="runtime-a",
        idempotency_key="request-1",
    )
    snapshot = first.index.snapshot()

    assert first.idempotency_status == "created"
    assert snapshot["input"]["kind"] == "content"
    assert snapshot["input"]["original_path"] == str(source.resolve())
    assert (run_dir / snapshot["input"]["path"]).read_text(encoding="utf-8") == "# Deck\n"
    assert snapshot["backend_contract"]["backend"] == "fixture"
    assert (run_dir / snapshot["backend_contract"]["path"]).is_file()
    assert snapshot["request_fingerprint"]
    assert snapshot["output_dir"] == str(run_dir.resolve())
    assert run_dir.stat().st_mode & 0o777 == 0o700
    assert (run_dir / snapshot["input"]["path"]).stat().st_mode & 0o777 == 0o600

    replay = RunIndex.create_from_request(
        run_dir,
        route="generate",
        input_path=source,
        backend_contract_path=backend,
        runtime_identity="runtime-a",
        idempotency_key="request-1",
    )
    assert replay.idempotency_status == "replayed"
    assert replay.index.snapshot()["run_id"] == snapshot["run_id"]


def test_create_from_request_rejects_same_key_with_changed_fingerprint(tmp_path):
    source = tmp_path / "brief.md"
    source.write_text("one", encoding="utf-8")
    backend = write_backend(tmp_path / "backend.json")
    run_dir = tmp_path / "run"
    RunIndex.create_from_request(
        run_dir,
        route="generate",
        input_path=source,
        backend_contract_path=backend,
        runtime_identity="runtime-a",
        idempotency_key="request-1",
    )
    source.write_text("two", encoding="utf-8")

    with pytest.raises(IdempotencyConflict, match="idempotency_conflict"):
        RunIndex.create_from_request(
            run_dir,
            route="generate",
            input_path=source,
            backend_contract_path=backend,
            runtime_identity="runtime-a",
            idempotency_key="request-1",
        )


def test_create_from_request_rejects_symlinks_and_route_type_mismatch(tmp_path):
    source = tmp_path / "brief.md"
    source.write_text("content", encoding="utf-8")
    symlink = tmp_path / "linked.md"
    symlink.symlink_to(source)
    backend = write_backend(tmp_path / "backend.json")

    with pytest.raises(ContractError, match="input_symlink_forbidden"):
        RunIndex.create_from_request(
            tmp_path / "symlink-run",
            route="generate",
            input_path=symlink,
            backend_contract_path=backend,
            runtime_identity="runtime-a",
        )
    with pytest.raises(ContractError, match="input_route_mismatch"):
        RunIndex.create_from_request(
            tmp_path / "wrong-route",
            route="direct-editable",
            input_path=source,
            backend_contract_path=backend,
            runtime_identity="runtime-a",
        )


def test_create_from_request_rejects_raw_credential_reference(tmp_path):
    source = tmp_path / "brief.md"
    source.write_text("content", encoding="utf-8")
    backend = tmp_path / "backend.json"
    value = backend_contract("openai")
    value["credential_ref"] = "sk-raw-secret"
    backend.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(Exception, match="credential_reference_invalid"):
        RunIndex.create_from_request(
            tmp_path / "run",
            route="generate",
            input_path=source,
            backend_contract_path=backend,
            runtime_identity="runtime-a",
        )


def test_new_environment_secret_does_not_change_a_frozen_run(tmp_path, monkeypatch):
    source = tmp_path / "brief.md"
    source.write_text("content", encoding="utf-8")
    backend = write_backend(tmp_path / "backend.json", backend="openai")
    run_dir = tmp_path / "run"

    created = RunIndex.create_from_request(
        run_dir,
        route="generate",
        input_path=source,
        backend_contract_path=backend,
        runtime_identity="runtime-a",
    )
    frozen_before = (run_dir / "input/backend-contract.json").read_bytes()

    monkeypatch.setenv("ATLASCLOUD_API_KEY", "new-secret-must-not-affect-run")
    snapshot = created.index.snapshot()

    assert snapshot["backend_contract"]["backend"] == "openai"
    assert (run_dir / "input/backend-contract.json").read_bytes() == frozen_before
    assert b"new-secret-must-not-affect-run" not in frozen_before
