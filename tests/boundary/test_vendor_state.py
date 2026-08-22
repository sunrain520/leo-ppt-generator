from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from leo_ppt_generator._vendor.editable_ppt.editppt.runtime import deck_run_state


def test_vendor_locked_state_serializes_concurrent_record_updates(tmp_path):
    target = tmp_path / "page_jobs.json"
    deck_run_state.write_json(target, {"revision": 0, "values": []})

    def append(number):
        with deck_run_state.locked_json(target) as state:
            state["values"].append(number)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(append, range(30)))
    result = deck_run_state.read_json(target)
    assert result["revision"] == 30
    assert sorted(result["values"]) == list(range(30))


def test_vendor_expected_revision_conflict_is_fail_closed(tmp_path):
    target = tmp_path / "page_jobs.json"
    deck_run_state.write_json(target, {"revision": 2})
    with (
        pytest.raises(ValueError, match="vendor_revision_conflict"),
        deck_run_state.locked_json(target, expected_revision=1),
    ):
        pass


def test_vendor_atomic_write_replaces_old_state_with_valid_json(tmp_path):
    target = tmp_path / "page_jobs.json"
    deck_run_state.write_json(target, {"revision": 1})
    deck_run_state.write_json(target, {"revision": 2, "status": "recorded"})
    assert deck_run_state.read_json(target) == {"revision": 2, "status": "recorded"}
