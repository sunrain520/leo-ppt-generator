from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_ppt_generator.image_deck.adapter import ImageDeckAdapter
from leo_ppt_generator.upgrade.baseline import (
    BaselineError,
    import_baseline,
    inspect_image_delivery,
    load_baseline,
)
from PIL import Image


def _image(path: Path, color: str) -> Path:
    Image.new("RGB", (320, 180), color).save(path)
    return path


def _completed_image_run(tmp_path: Path) -> Path:
    run = tmp_path / "source-run"
    (run / "image-deck").mkdir(parents=True)
    adapter = ImageDeckAdapter(run / "image-deck")
    adapter.prepare([{"number": 1, "notes": "speaker"}])
    adapter.record(1, _image(tmp_path / "source.png", "red"), backend="fixture", expected_revision=0, operation_id="record-1")
    adapter.finalize(run / "deck.pptx")
    (run / "run.json").write_text(json.dumps({"run_id": "source-1", "route": "generate"}), encoding="utf-8")
    return run


def test_inspect_and_import_baseline_freezes_page_and_delivery_identity(tmp_path):
    source = _completed_image_run(tmp_path)
    target = tmp_path / "upgrade-run"
    target.mkdir()
    inspected = inspect_image_delivery(source)
    imported = import_baseline(source, target)

    assert inspected["baseline_fingerprint"] == imported["baseline_fingerprint"]
    assert imported["pages"][0]["notes"] == "speaker"
    assert Path(imported["pages"][0]["artifact"]).is_file()
    replay = import_baseline(source, target)
    assert replay["idempotency_status"] == "replayed"


def test_import_rejects_source_delivery_hash_drift(tmp_path):
    source = _completed_image_run(tmp_path)
    delivery = source / "image-deck" / "slide_jobs.json"
    jobs = json.loads(delivery.read_text(encoding="utf-8"))
    Path(jobs["delivery"]["pptx"]).write_bytes(b"tampered")

    with pytest.raises(BaselineError, match="upgrade_baseline_delivery_hash_mismatch"):
        inspect_image_delivery(source)


def test_loaded_baseline_rejects_artifact_notes_and_manifest_mutation(tmp_path):
    source = _completed_image_run(tmp_path)
    target = tmp_path / "upgrade-run"
    target.mkdir()
    imported = import_baseline(source, target)
    artifact = Path(imported["pages"][0]["artifact"])
    artifact.write_bytes(b"changed")
    with pytest.raises(BaselineError, match="upgrade_baseline_artifact_changed"):
        load_baseline(target)

    # 重新导入到另一个 target，分别验证 notes/manifest identity fence。
    target_notes = tmp_path / "upgrade-notes"
    target_notes.mkdir()
    imported_notes = import_baseline(source, target_notes)
    manifest_path = target_notes / "image-baseline/baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["notes"] = "changed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BaselineError, match="upgrade_baseline_notes_changed"):
        load_baseline(target_notes)

    target_manifest = tmp_path / "upgrade-manifest"
    target_manifest.mkdir()
    import_baseline(source, target_manifest)
    manifest_path = target_manifest / "image-baseline/baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["page_count"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BaselineError, match="upgrade_baseline_manifest_changed"):
        load_baseline(target_manifest)
