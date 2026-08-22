from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from leo_ppt_generator.application.run_index import (
    IdempotencyConflict,
    RevisionConflict,
    RunIndex,
)


def test_expected_revision_and_reconciliation_preserve_updates(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    assert index.snapshot()["revision"] == 0
    first = index.update(expected_revision=0, changes={"stage": "image.prepare"})
    assert first["revision"] == 1
    with pytest.raises(RevisionConflict):
        index.update(expected_revision=0, changes={"stage": "wrong"})
    reconciled = index.reconcile({"image": {"status": "completed"}})
    assert reconciled["revision"] == 2
    assert reconciled["domains"]["image"]["status"] == "completed"


def test_create_replays_only_when_run_identity_matches(tmp_path):
    run_dir = tmp_path / "run"
    first = RunIndex.create(run_dir, route="generate", runtime_identity="runtime-a")

    replay = RunIndex.create(run_dir, route="generate", runtime_identity="runtime-a")
    assert replay.snapshot()["run_id"] == first.snapshot()["run_id"]

    with pytest.raises(RevisionConflict, match="run_identity_conflict"):
        RunIndex.create(run_dir, route="direct-editable", runtime_identity="runtime-a")


def test_unknown_operation_queries_and_completion_fail_closed(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")

    with pytest.raises(IdempotencyConflict, match="unknown_operation"):
        index.operation("missing")
    with pytest.raises(IdempotencyConflict, match="unknown_operation"):
        index.complete_operation("missing", result={"ok": True})


def test_idempotency_replay_and_fingerprint_conflict(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    started = index.begin_operation("op-1", "same", mutation="image.record")
    assert started["outcome"] == "started"
    index.complete_operation("op-1", result={"artifact": "slide.png"})
    replay = index.begin_operation("op-1", "same", mutation="image.record")
    assert replay["outcome"] == "replay"
    with pytest.raises(IdempotencyConflict):
        index.begin_operation("op-1", "different", mutation="image.record")


def test_completing_worker_operation_closes_lease_and_is_idempotent(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    issued = index.issue_lease("slide_01", actor="worker-1", operation_id="op-1")

    completed = index.complete_operation("op-1", result={"artifact_ref": "slide.png"})
    revision = completed["revision"]
    assert completed["leases"]["op-1"]["status"] == "completed"
    assert completed["operations"]["op-1"]["status"] == "completed"
    assert completed["operations"]["op-1"]["safe_to_retry"] is False
    assert issued["lease"] == completed["leases"]["op-1"]["lease"]

    replay = index.complete_operation("op-1", result={"artifact_ref": "slide.png"})
    assert replay["revision"] == revision


def test_cancel_conflicts_do_not_run_domain_mutation_callback(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    current = index.snapshot()
    index.update(
        expected_revision=current["revision"],
        changes={"status": "completed", "stage": "image.finalize"},
    )
    callback_calls: list[str] = []

    with pytest.raises(IdempotencyConflict, match="cancel_state_conflict"):
        index.cancel(before_commit=lambda: callback_calls.append("called"))

    assert callback_calls == []


def test_cancel_revision_conflict_precedes_domain_mutation_callback(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    callback_calls: list[str] = []

    with pytest.raises(RevisionConflict, match="revision_conflict"):
        index.cancel(
            expected_revision=99,
            before_commit=lambda: callback_calls.append("called"),
        )

    assert callback_calls == []


def test_events_are_redacted_and_append_only(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")
    index.event("worker.result", {"page_id": "page_001", "token": "secret", "body": "private"})
    event = json.loads((tmp_path / "run/events.ndjson").read_text().splitlines()[-1])
    assert event["data"] == {"page_id": "page_001"}


def test_events_have_monotonic_sequence_under_concurrent_append(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime-a")

    def append(number: int):
        index.event(
            "worker.result",
            {
                "actor": "worker",
                "page_id": f"page_{number:03d}",
                "status": "completed",
                "operation_id": f"op-{number}",
                "prompt": "must-not-log",
            },
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, range(1, 9)))
    events = [
        json.loads(line)
        for line in (tmp_path / "run/events.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert all("prompt" not in event["data"] for event in events)
