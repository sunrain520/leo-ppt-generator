from __future__ import annotations

import json

import pytest
from leo_ppt_generator import cli
from leo_ppt_generator.application.run_index import RunIndex
from leo_ppt_generator.evidence import (
    EvidenceError,
    record_acceptance,
    record_provenance,
    record_visual,
)
from leo_ppt_generator.observability import write_delivery_reports
from leo_ppt_generator.storage import sha256_file


def _delivery(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime")
    pptx = run / "final/deck.pptx"
    pptx.parent.mkdir()
    pptx.write_bytes(b"pptx-fixture")
    write_delivery_reports(
        run,
        {"pptx": str(pptx), "pptx_sha256": sha256_file(pptx), "delivery_type": "image", "page_count": 1},
    )
    index = RunIndex(run)
    snapshot = index.snapshot()
    index.update(
        expected_revision=snapshot["revision"],
        changes={"status": "completed", "stage": "image.finalize"},
    )
    return run, pptx


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_provenance_is_redacted_hash_bound_and_idempotent(tmp_path):
    run, _pptx = _delivery(tmp_path)
    artifact = run / "image-deck/origin_image/slide_01.png"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"image-artifact")
    (run / "image-deck/slide_jobs.json").write_text(
        json.dumps({"slides": [{"slide_id": "slide_01", "artifact": "origin_image/slide_01.png", "sha256": sha256_file(artifact)}]}),
        encoding="utf-8",
    )
    receipt = _write(
        tmp_path / "provenance.json",
        {
            "schema_version": 1,
            "page_id": "slide_01",
            "provider": "openai",
            "model": "gpt-image-2",
            "endpoint_origin": "https://api.openai.com",
            "prompt_sha256": "a" * 64,
            "input_sha256": "b" * 64,
            "reference_sha256s": ["c" * 64],
            "artifact_sha256": sha256_file(artifact),
            "provider_receipt_id": "request-1",
        },
    )
    first = record_provenance(run, receipt)
    second = record_provenance(run, receipt)
    assert first["idempotency_status"] == "created"
    assert second["idempotency_status"] == "replayed"
    value = json.loads((run / "reports/provenance-slide_01.json").read_text())
    assert value["model"] == "gpt-image-2"
    receipt.write_text('{"api_key":"secret"}', encoding="utf-8")
    with pytest.raises(EvidenceError, match="evidence_sensitive_content_forbidden"):
        record_provenance(run, receipt)
    invalid = {**value, "page_id": "../../escape"}
    receipt.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(EvidenceError, match="provenance_receipt_invalid"):
        record_provenance(run, receipt)


def test_visual_and_manual_receipts_bind_current_pptx_and_update_separate_gates(tmp_path):
    run, pptx = _delivery(tmp_path)
    digest = sha256_file(pptx)
    render = tmp_path / "page-1.png"
    render.write_bytes(b"render")
    visual = _write(
        tmp_path / "visual.json",
        {"schema_version": 1, "renderer": "LibreOffice", "renderer_version": "26.2", "pptx_sha256": digest, "pages": [{"page": 1, "status": "passed", "render_path": str(render), "render_sha256": sha256_file(render), "checks": {"font": "passed", "contrast": "passed", "occlusion": "passed"}}]},
    )
    manual = _write(
        tmp_path / "manual.json",
        {"schema_version": 1, "reviewer": "owner", "client": "Microsoft PowerPoint", "client_version": "16", "pptx_sha256": digest, "pages": [{"page": 1, "decision": "accepted"}]},
    )
    assert cli.main(["evidence", "visual", str(run), "--receipt", str(visual)]) == 0
    assert cli.main(["evidence", "accept", str(run), "--receipt", str(manual)]) == 0
    summary = json.loads((run / "final/validation-summary.json").read_text())
    assert summary["quality_gates"]["visual_render"]["status"] == "passed"
    assert summary["quality_gates"]["manual_visual_acceptance"]["status"] == "passed"
    status = cli.dispatch(cli.build_parser().parse_args(["run", "status", str(run), "--json"]))
    assert status["delivery_readiness"]["status"] == "accepted"
    assert status["delivery_readiness"]["missing_gates"] == []
    assert status["next_action"]["kind"] == "none"
    assert str(run / "reports/visual-render.json") in status["evidence_refs"]
    assert str(run / "reports/manual-acceptance.json") in status["evidence_refs"]
    visual_value = json.loads(visual.read_text())
    visual_value["pptx_sha256"] = "0" * 64
    visual.write_text(json.dumps(visual_value), encoding="utf-8")
    with pytest.raises(EvidenceError, match="delivery_identity_mismatch"):
        record_visual(run, visual)


def test_manual_rejection_cannot_be_recorded_as_acceptance(tmp_path):
    run, pptx = _delivery(tmp_path)
    receipt = _write(
        tmp_path / "rejected.json",
        {"schema_version": 1, "reviewer": "owner", "client": "PowerPoint", "client_version": "16", "pptx_sha256": sha256_file(pptx), "pages": [{"page": 1, "decision": "rejected"}]},
    )
    with pytest.raises(EvidenceError, match="acceptance_receipt_invalid"):
        record_acceptance(run, receipt)


def test_completed_run_without_delivery_summary_requires_artifact_repair(tmp_path):
    run, _pptx = _delivery(tmp_path)
    (run / "final/validation-summary.json").unlink()

    status = cli.dispatch(cli.build_parser().parse_args(["run", "status", str(run), "--json"]))

    assert status["delivery_readiness"]["status"] == "artifact_invalid"
    assert status["delivery_readiness"]["reason_code"] == "delivery_summary_required"
    assert status["next_action"] == {
        "kind": "repair_delivery_artifact",
        "payload": {"reason_code": "delivery_summary_required"},
    }


def test_malformed_delivery_summary_requires_artifact_repair(tmp_path):
    run, _pptx = _delivery(tmp_path)
    (run / "final/validation-summary.json").write_text("[]\n", encoding="utf-8")

    status = cli.dispatch(cli.build_parser().parse_args(["run", "status", str(run), "--json"]))

    assert status["delivery_readiness"] == {
        "status": "artifact_invalid",
        "reason_code": "delivery_summary_invalid",
        "artifact_ready": False,
        "missing_gates": [],
        "unverified_gates": [],
        "evidence_refs": [],
    }
    assert status["next_action"]["kind"] == "repair_delivery_artifact"
