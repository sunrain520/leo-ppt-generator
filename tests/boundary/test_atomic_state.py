from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from leo_ppt_generator.application.run_index import RevisionConflict, RunIndex
from leo_ppt_generator.storage import atomic_materialize, atomic_write_json


@pytest.mark.parametrize(
    "point",
    [
        "before_temp_write",
        "after_temp_write",
        "before_file_fsync",
        "after_file_fsync",
        "before_replace",
        "after_replace",
        "after_directory_fsync",
        "after_commit",
    ],
)
def test_eight_checkpoint_interruptions_never_leave_invalid_json(tmp_path, point):
    target = tmp_path / "state.json"
    target.write_text('{"revision": 1}\n', encoding="utf-8")

    def crash(name):
        if name == point:
            raise RuntimeError(f"crash:{name}")

    with pytest.raises(RuntimeError, match="crash"):
        atomic_write_json(target, {"revision": 2, "payload": "x" * 1000}, checkpoint=crash)
    observed = json.loads(target.read_text(encoding="utf-8"))
    assert observed["revision"] in {1, 2}


def test_concurrent_expected_revision_has_one_winner_and_no_lost_update(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime")

    def update(stage):
        try:
            return index.update(expected_revision=0, changes={"stage": stage})["stage"]
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ("image.prepare", "image.dispatch")))
    assert results.count("conflict") == 1
    assert index.snapshot()["revision"] == 1


@pytest.mark.parametrize("point", ["before_write", "after_write", "after_file_fsync", "after_replace", "after_directory_fsync"])
def test_atomic_binary_materialize_checkpoint_never_leaves_partial_delivery(tmp_path, point):
    target = tmp_path / "deck.pptx"
    target.write_bytes(b"old")

    def crash(name):
        if name == point:
            raise RuntimeError(f"crash:{name}")

    def writer(path):
        path.write_bytes(b"new" * 100)

    with pytest.raises(RuntimeError, match="crash"):
        atomic_materialize(target, writer, checkpoint=crash)
    assert target.read_bytes() in {b"old", b"new" * 100}
    assert not list(tmp_path.glob(".deck.pptx.*.tmp"))
