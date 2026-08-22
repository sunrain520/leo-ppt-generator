from __future__ import annotations

import json
import os

import pytest
from leo_ppt_generator.application.run_index import IdempotencyConflict, RunIndex
from leo_ppt_generator.image_deck.adapter import ImageDeckAdapter
from leo_ppt_generator.lifecycle import CleanupConflict, Lifecycle
from leo_ppt_generator.storage import sha256_file
from PIL import Image


def test_diagnose_returns_one_safe_action_and_cleanup_is_fingerprint_guarded(tmp_path):
    run = tmp_path / "run"
    index = RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    (run / "tmp").mkdir()
    (run / "tmp/orphan.tmp").write_text("x", encoding="utf-8")
    report = Lifecycle(run).diagnose()
    assert report["next_action"]["kind"] == "cleanup_preview"
    preview = Lifecycle(run).cleanup_preview(expected_revision=index.snapshot()["revision"])
    (run / "tmp/other.tmp").write_text("y", encoding="utf-8")
    try:
        Lifecycle(run).cleanup_apply(preview)
    except CleanupConflict as exc:
        assert exc.reason_code == "cleanup_fingerprint_drift"
    else:
        raise AssertionError("fingerprint drift must prevent deletion")


def test_cancel_revokes_generation_bound_worker_lease(tmp_path):
    run = tmp_path / "run"
    index = RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    lease = index.issue_lease("slide_01", actor="worker-1", operation_id="op-1")
    index.validate_lease(
        operation_id="op-1", lease=lease["lease"], generation=lease["generation"]
    )
    index.cancel()
    with pytest.raises(IdempotencyConflict, match="lease_revoked|generation_conflict|run_not_mutable"):
        index.validate_lease(
            operation_id="op-1", lease=lease["lease"], generation=lease["generation"]
        )


def test_concurrent_image_finalize_has_one_delivery_revision(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    source = tmp_path / "slide.png"
    Image.new("RGB", (160, 90), "navy").save(source)
    adapter = ImageDeckAdapter(run / "image-deck")
    adapter.prepare([{"number": 1}])
    adapter.record(1, source, backend="fixture", expected_revision=0, operation_id="record-1")

    from concurrent.futures import ThreadPoolExecutor

    def finalize():
        return adapter.finalize(run / "final/deck.pptx")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: finalize(), (1, 2)))
    assert sorted(result["idempotency_status"] for result in results) == ["created", "replayed"]
    jobs = json.loads((run / "image-deck/slide_jobs.json").read_text(encoding="utf-8"))
    assert jobs["delivery"]["revision"] == 1
    assert len(list((run / "final").glob("*.pptx"))) == 1


def test_cleanup_apply_is_scoped_and_terminal_diagnosis_is_read_only(tmp_path):
    run = tmp_path / "run"
    index = RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    (run / "tmp").mkdir()
    (run / "tmp/orphan.tmp").write_text("x", encoding="utf-8")
    (run / "keep.txt").write_text("keep", encoding="utf-8")
    preview = Lifecycle(run).cleanup_preview(expected_revision=0)
    receipt = Lifecycle(run).cleanup_apply(preview)
    assert receipt["removed"] == ["tmp/orphan.tmp"]
    assert (run / "keep.txt").read_text() == "keep"
    index.update(expected_revision=0, changes={"status": "completed"})
    assert Lifecycle(run).diagnose()["next_action"]["reason_code"] == "terminal_run"


def test_cleanup_rejects_a_symlinked_scope_root(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("keep", encoding="utf-8")
    os.symlink(outside, run / "tmp")

    with pytest.raises(CleanupConflict, match="cleanup_symlink_escape"):
        Lifecycle(run).cleanup_preview(expected_revision=0)

    assert protected.read_text(encoding="utf-8") == "keep"


def test_diagnose_reports_but_does_not_mutate_invalid_event_tail(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    events = run / "events.ndjson"
    events.write_text(events.read_text(encoding="utf-8") + '{"partial":', encoding="utf-8")
    before = events.read_bytes()
    report = Lifecycle(run).diagnose()
    assert report["event_log"]["tail_invalid"] is True
    assert report["next_action"]["reason_code"] == "event_log_tail_invalid"
    assert report["runtime"]["status"] == "passed"
    assert report["protocol"] == {
        "run_schema": "passed",
        "route": "passed",
        "stage": "passed",
    }
    assert report["config"]["status"] == "passed"
    assert events.read_bytes() == before


def test_diagnose_reports_missing_run_index_without_creating_files(tmp_path):
    run = tmp_path / "missing-run"
    run.mkdir()
    before = list(run.iterdir())
    report = Lifecycle(run).diagnose()
    assert report["status"] == "failed"
    assert report["protocol"]["run_schema"] == "failed"
    assert report["next_action"]["reason_code"] == "run_index_missing"
    assert list(run.iterdir()) == before


def test_diagnose_reports_frozen_input_hash_mismatch_read_only(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    source = run / "input/source.md"
    source.parent.mkdir()
    source.write_text("original", encoding="utf-8")
    state = json.loads((run / "run.json").read_text(encoding="utf-8"))
    state["input"] = {
        "path": "input/source.md",
        "sha256": sha256_file(source),
    }
    state["input_available"] = True
    (run / "run.json").write_text(json.dumps(state), encoding="utf-8")
    source.write_text("changed", encoding="utf-8")
    before = source.read_bytes()

    report = Lifecycle(run).diagnose()

    assert report["integrity"]["input"]["status"] == "failed"
    assert report["integrity"]["input"]["reason_code"] == "source_hash_mismatch"
    assert report["next_action"]["reason_code"] == "source_hash_mismatch"
    assert source.read_bytes() == before


def test_diagnose_reports_invalid_timing_without_overwriting_it(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime-a")
    timing = run / "reports/timing.json"
    timing.parent.mkdir()
    timing.write_text('{"partial":', encoding="utf-8")
    before = timing.read_bytes()

    report = Lifecycle(run).diagnose()

    assert report["observability"]["timing"]["status"] == "failed"
    assert report["observability"]["timing"]["reason_code"] == "timing_report_invalid"
    assert timing.read_bytes() == before
