from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from leo_ppt_generator import cli
from leo_ppt_generator.application.run_index import IdempotencyConflict, RunIndex
from leo_ppt_generator.editable.adapter import EditableAdapter
from leo_ppt_generator.image_deck.adapter import ImageDeckAdapter
from PIL import Image

from tests.backend_fixtures import backend_contract
from tests.ppt_fixtures import build_editable_page


def parse(*arguments: str):
    return cli.build_parser().parse_args(arguments)


def png(path: Path) -> Path:
    Image.new("RGB", (160, 90), "navy").save(path)
    return path


def test_operation_retry_and_cancel_have_stable_idempotency_contract(tmp_path):
    run = tmp_path / "run"
    index = RunIndex.create(run, route="generate", runtime_identity="runtime")
    index.begin_operation("provider-1", "fingerprint", mutation="provider.call")
    index.complete_operation("provider-1", result={"artifact": "slide.png"})

    operation = cli.dispatch(parse("run", "operation", str(run), "--id", "provider-1", "--json"))
    assert operation["operation"]["status"] == "completed"
    assert operation["safe_to_retry"] is False

    first_retry = cli.dispatch(parse("run", "retry", str(run), "--from-failed-pages"))
    second_retry = cli.dispatch(parse("run", "retry", str(run), "--from-failed-pages"))
    assert first_retry["idempotency_status"] == "created"
    assert second_retry["idempotency_status"] == "replayed"
    assert second_retry["operation_id"] == first_retry["operation_id"]
    assert second_retry["safe_to_retry"] is True

    latest = RunIndex(run).snapshot()
    RunIndex(run).update(expected_revision=latest["revision"], changes={"stage": "image.prepare"})
    with pytest.raises(IdempotencyConflict, match="retry_state_conflict"):
        cli.dispatch(parse("run", "retry", str(run), "--from-failed-pages"))

    first_cancel = cli.dispatch(parse("run", "cancel", str(run), "--wait-workers"))
    second_cancel = cli.dispatch(parse("run", "cancel", str(run), "--wait-workers"))
    assert first_cancel["safe_to_retry"] is False
    assert second_cancel["idempotency_status"] == "replayed"
    with pytest.raises(IdempotencyConflict, match="run_not_retryable"):
        cli.dispatch(parse("run", "retry", str(run)))


def test_cancelled_run_rejects_late_image_record_and_finalize(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime")
    slides = tmp_path / "slides.json"
    slides.write_text('[{"number": 1}]\n', encoding="utf-8")
    source = png(tmp_path / "slide.png")
    cli.dispatch(parse("image", "prepare", str(run), "--slides", str(slides)))
    cli.dispatch(parse("run", "cancel", str(run)))
    with pytest.raises(Exception, match="run_not_mutable"):
        cli.dispatch(
            parse(
                "image",
                "record",
                str(run),
                "--slide",
                "slide_01",
                "--result",
                str(source),
            )
        )
    with pytest.raises(Exception, match="run_cancelled_mutation_forbidden"):
        cli.dispatch(parse("image", "assemble", str(run)))


def test_scoped_cleanup_requires_terminal_run_for_input_and_exact_preview(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime")
    (run / "tmp").mkdir()
    (run / "tmp/orphan.tmp").write_text("temporary", encoding="utf-8")
    (run / "input").mkdir()
    (run / "input/source.md").write_text("private", encoding="utf-8")

    preview = cli.dispatch(
        parse("run", "cleanup", str(run), "--scope", "temp", "--dry-run")
    )["preview"]
    assert preview["entries"][0]["category"] == "temp"
    receipt = cli.dispatch(
        parse("run", "cleanup", str(run), "--scope", "temp", "--apply")
    )["receipt"]
    assert receipt["recoverable"] is False
    assert not (run / "tmp/orphan.tmp").exists()
    assert (run / "input/source.md").is_file()

    with pytest.raises(Exception, match="cleanup_input_requires_terminal_run"):
        cli.dispatch(parse("run", "cleanup", str(run), "--scope", "input", "--dry-run"))
    current = RunIndex(run).snapshot()
    RunIndex(run).update(expected_revision=current["revision"], changes={"status": "failed"})
    cli.dispatch(parse("run", "cleanup", str(run), "--scope", "input", "--dry-run"))
    cli.dispatch(parse("run", "cleanup", str(run), "--scope", "input", "--apply"))
    assert not (run / "input/source.md").exists()
    assert RunIndex(run).snapshot()["input_available"] is False
    with pytest.raises(Exception, match="input_file_missing"):
        cli.dispatch(
            parse("image", "prepare", str(run), "--slides", str(tmp_path / "slides.json"))
        )


def test_editable_dispatch_record_next_reset_and_finalize_stable_flow(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="direct-editable", runtime_identity="runtime")
    source = png(tmp_path / "source.png")
    prepared = cli.dispatch(
        parse("editable", "prepare", str(run), "--sources", str(source))
    )
    assert prepared["status"] == "ready"
    prompt = tmp_path / "prompt.md"
    prompt.write_text("rebuild", encoding="utf-8")
    dispatched = cli.dispatch(
        parse(
            "editable",
            "dispatch",
            str(run),
            "--page",
            "page_001",
            "--agent-id",
            "agent-1",
            "--prompt-file",
            str(prompt),
        )
    )
    replayed = cli.dispatch(
        parse(
            "editable",
            "dispatch",
            str(run),
            "--page",
            "page_001",
            "--agent-id",
            "agent-1",
            "--prompt-file",
            str(prompt),
        )
    )
    assert dispatched["idempotency_status"] == "created"
    assert replayed["idempotency_status"] == "replayed"
    assert Path(dispatched["dispatch"]["worker_log"]).is_file()
    assert Path(dispatched["dispatch"]["worker_log"]).stat().st_mode & 0o777 == 0o600

    worker_dir = Path(dispatched["dispatch"]["worker_dir"])
    _page, manifest = build_editable_page(source, worker_dir / "page.pptx")
    if manifest != worker_dir / "manifest.json":
        (worker_dir / "manifest.json").write_bytes(manifest.read_bytes())
    (worker_dir / "validation.json").write_text('{"passed": true}\n', encoding="utf-8")
    recorded = cli.dispatch(
        parse(
            "editable",
            "record",
            str(run),
            "--page",
            "page_001",
            "--agent-id",
            "agent-1",
        )
    )
    assert recorded["artifact"]["mode"] == "editable"
    assert recorded["operation_id"] == dispatched["operation_id"]
    assert recorded["record_operation_id"] == "editable-page_001-agent-1"
    operation = cli.dispatch(
        parse("run", "operation", str(run), "--id", recorded["operation_id"], "--json")
    )
    assert operation["operation"]["status"] == "completed"
    assert operation["safe_to_retry"] is False
    next_result = cli.dispatch(parse("editable", "next", str(run), "--json"))
    assert next_result["next_action"]["kind"] == "finalize"
    finalized = cli.dispatch(parse("editable", "finalize", str(run)))
    finalized_again = cli.dispatch(parse("editable", "finalize", str(run)))
    assert finalized["idempotency_status"] == "created"
    assert finalized_again["idempotency_status"] == "replayed"
    assert Path(finalized["pptx"]).is_file()
    assert (run / "final/validation-summary.json").is_file()

    reset = cli.dispatch(
        parse("editable", "reset", str(run), "--page", "page_001", "--confirm-lost")
    )
    assert reset["page"]["status"] == "pending"


def test_image_prepare_record_and_assemble_replay_stable_flow(tmp_path):
    run = tmp_path / "run"
    RunIndex.create(run, route="generate", runtime_identity="runtime")
    slides = tmp_path / "slides.json"
    slides.write_text('[{"number": 1, "notes": "speaker"}]\n', encoding="utf-8")
    source = png(tmp_path / "slide.png")
    prepared = cli.dispatch(
        parse("image", "prepare", str(run), "--slides", str(slides))
    )
    state_hash = prepared["state_hash"]
    arguments = (
        "image",
        "record",
        str(run),
        "--slide",
        "slide_01",
        "--agent-id",
        "agent-1",
        "--result",
        str(source),
        "--expected-state-hash",
        state_hash,
        "--worker-duration-seconds",
        "12.5",
        "--backend-duration-seconds",
        "8.25",
    )
    recorded = cli.dispatch(parse(*arguments))
    replay = cli.dispatch(parse(*arguments))
    assert recorded["idempotency_status"] == "created"
    assert replay["idempotency_status"] == "replayed"
    recorded_run = RunIndex(run).snapshot()
    operation = recorded_run["operations"][recorded["operation_id"]]
    lease = recorded_run["leases"][recorded["operation_id"]]
    assert operation["status"] == "completed"
    assert operation["safe_to_retry"] is False
    assert lease["status"] == "completed"
    assembled = cli.dispatch(parse("image", "assemble", str(run)))
    assembled_again = cli.dispatch(parse("image", "assemble", str(run)))
    assert assembled["idempotency_status"] == "created"
    assert assembled_again["idempotency_status"] == "replayed"
    assert Path(assembled["pptx"]).is_file()
    assert RunIndex(run).snapshot()["status"] == "completed"
    summary = json.loads((run / "final/validation-summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["delivery_type"] == "image"
    assert summary["quality_gates"]["pptx_structure"]["status"] == "passed"
    assert summary["quality_gates"]["visual_render"]["status"] == "not_run"
    assert summary["quality_gates"]["manual_visual_acceptance"]["status"] == "not_run"
    pending_status = cli.dispatch(parse("run", "status", str(run), "--json"))
    assert pending_status["delivery_readiness"]["status"] == "acceptance_pending"
    assert pending_status["delivery_readiness"]["missing_gates"] == [
        "visual_render",
        "manual_visual_acceptance",
    ]
    assert pending_status["next_action"]["kind"] == "record_delivery_evidence"
    assert str(run / "final/validation-summary.json") in pending_status["evidence_refs"]
    timing = json.loads((run / "reports/timing.json").read_text(encoding="utf-8"))
    assert any(stage["stage"] == "image.assemble" for stage in timing["stages"])
    assert timing["pages"] == [
        {
            "unit_id": "slide_01",
            "command": "image.record",
            "duration_seconds": 12.5,
            "status": "ready",
        }
    ]
    assert timing["backend_calls"] == [
        {
            "unit_id": "slide_01",
            "backend": "fixture",
            "duration_seconds": 8.25,
            "status": "ready",
        }
    ]
    assert json.loads((run / "logs/run.log").read_text(encoding="utf-8").splitlines()[-1])[
        "event"
    ] == "command_completed"
    before_cancel = {
        path: path.read_bytes()
        for path in (run / "run.json", run / "image-deck/slide_jobs.json")
    }
    with pytest.raises(Exception, match="cancel_state_conflict"):
        cli.dispatch(parse("run", "cancel", str(run), "--wait-workers"))
    assert {
        path: path.read_bytes()
        for path in (run / "run.json", run / "image-deck/slide_jobs.json")
    } == before_cancel


def test_upgrade_finalize_full_selected_and_explicit_partial(tmp_path):
    # Upgrade baseline 必须来自一个真实完成的 image delivery；不再允许
    # 手工 seed domain adapter 后直接 finalize 绕过 baseline 合同。
    source_run = tmp_path / "image-source"
    RunIndex.create(source_run, route="generate", runtime_identity="runtime")
    sources = [png(tmp_path / f"source-{number}.png") for number in range(1, 4)]
    slides = tmp_path / "slides.json"
    slides.write_text(
        json.dumps([{"number": number} for number in range(1, 4)]), encoding="utf-8"
    )
    cli.dispatch(parse("image", "prepare", str(source_run), "--slides", str(slides)))
    for number, source in enumerate(sources, 1):
        cli.dispatch(
            parse(
                "image",
                "record",
                str(source_run),
                "--slide",
                f"slide_{number:02d}",
                "--agent-id",
                "fixture-agent",
                "--result",
                str(source),
            )
        )
    cli.dispatch(parse("image", "assemble", str(source_run)))

    run = tmp_path / "upgrade"
    index = RunIndex.create(run, route="upgrade-selected", runtime_identity="runtime")
    index.update(expected_revision=0, changes={"selected_pages": [1, 3]})
    cli.dispatch(
        parse("upgrade", "import-baseline", str(run), "--source-run", str(source_run))
    )
    editable = EditableAdapter(run / "editable")
    editable.prepare(
        [sources[0], sources[2]], worker_available=True, page_numbers=[1, 3]
    )
    for revision, number in enumerate((1, 3)):
        page, manifest = build_editable_page(
            sources[number - 1], tmp_path / f"page-{number}.pptx"
        )
        validation = tmp_path / f"validation-{number}.json"
        validation.write_text('{"passed": true}\n', encoding="utf-8")
        editable.record(
            f"page_{number:03d}",
            page,
            validation,
            manifest,
            expected_revision=revision,
            operation_id=f"editable-{number}",
        )
    completed = cli.dispatch(parse("upgrade", "finalize", str(run)))
    replayed = cli.dispatch(parse("upgrade", "finalize", str(run)))
    assert completed["delivery_type"] == "hybrid"
    assert replayed["idempotency_status"] == "replayed"
    assert [page["mode"] for page in completed["pages"]] == [
        "editable",
        "image",
        "editable",
    ]

    partial_run = tmp_path / "partial-upgrade"
    partial_index = RunIndex.create(
        partial_run, route="upgrade-selected", runtime_identity="runtime"
    )
    partial_index.update(expected_revision=0, changes={"selected_pages": [1, 3]})
    cli.dispatch(
        parse(
            "upgrade",
            "import-baseline",
            str(partial_run),
            "--source-run",
            str(source_run),
        )
    )
    partial_editable = EditableAdapter(partial_run / "editable")
    partial_editable.prepare(
        [sources[0], sources[2]], worker_available=True, page_numbers=[1, 3]
    )
    page, manifest = build_editable_page(sources[0], tmp_path / "partial-page-1.pptx")
    validation = tmp_path / "partial-validation-1.json"
    validation.write_text('{"passed": true}\n', encoding="utf-8")
    partial_editable.record(
        "page_001",
        page,
        validation,
        manifest,
        expected_revision=0,
        operation_id="editable-1",
    )
    with pytest.raises(Exception, match="partial_hybrid_confirmation_required"):
        cli.dispatch(parse("upgrade", "finalize", str(partial_run)))
    proposed = cli.dispatch(parse("upgrade", "propose", str(partial_run)))
    assert proposed["reason_code"] == "partial_hybrid_proposed"
    proposed_confirmation = proposed["proposal"]["confirmation_fingerprint"]
    current_partial = RunIndex(partial_run).snapshot()
    RunIndex(partial_run).update(
        expected_revision=current_partial["revision"], changes={"selected_pages": [1, 2]}
    )
    with pytest.raises(Exception, match="partial_hybrid_proposal_stale"):
        cli.dispatch(
            parse(
                "upgrade",
                "finalize",
                str(partial_run),
                "--partial-confirmation",
                proposed_confirmation,
            )
        )
    current_partial = RunIndex(partial_run).snapshot()
    RunIndex(partial_run).update(
        expected_revision=current_partial["revision"], changes={"selected_pages": [1, 3]}
    )
    proposed = cli.dispatch(parse("upgrade", "propose", str(partial_run)))
    confirmation = proposed["proposal"]["confirmation_fingerprint"]
    partial = cli.dispatch(
        parse(
            "upgrade",
            "finalize",
            str(partial_run),
            "--partial-confirmation",
            confirmation,
        )
    )
    assert partial["delivery_type"] == "partial-hybrid"
    assert partial["pages"][2]["mode"] == "image"
    failure_report = json.loads(
        (partial_run / "final/failure-report.json").read_text(encoding="utf-8")
    )
    assert failure_report["failures"] == {"3": "page_rebuild_failed"}
    assert (partial_run / "final/validation-summary.json").is_file()
    confirmation_receipt = json.loads(
        (partial_run / "reports/partial-confirmation.json").read_text(encoding="utf-8")
    )
    assert confirmation_receipt["selected_pages"] == [1, 3]
    assert confirmation_receipt["failures"] == {"3": "page_rebuild_failed"}


def test_top_level_editable_prepare_uses_embedded_input_normalizer(tmp_path):
    source = png(tmp_path / "source.png")
    backend = tmp_path / "backend.json"
    backend.write_text(
        json.dumps(backend_contract(mode="edit")), encoding="utf-8"
    )
    run = tmp_path / "run"
    cli.dispatch(
        parse(
            "run",
            "create",
            "--route",
            "direct-editable",
            "--input",
            str(source),
            "--output",
            str(run),
            "--backend-contract",
            str(backend),
        )
    )
    prepared = cli.dispatch(parse("editable", "prepare", str(run)))
    assert prepared["status"] == "ready"
    execution = json.loads((run / "run.json").read_text(encoding="utf-8"))["backend_execution"]
    assert len(execution["receipt_hash"]) == 64
    assert "secret" not in json.dumps(execution)
    assert (run / "editable/upstream/pages/page_001/source.png").is_file()
    assert not (run / "editable/upstream/page_jobs.json").exists()
    assert not (run / "editable/upstream/deck_run_state.json").exists()
    assert (run / "editable/upstream").stat().st_mode & 0o777 == 0o700
    assert (run / "editable/upstream/pages/page_001/source.png").stat().st_mode & 0o777 == 0o600
    jobs = json.loads((run / "editable/page_jobs.json").read_text(encoding="utf-8"))
    assert jobs["pages"][0]["source"].endswith("editable/upstream/pages/page_001/source.png")

    prompt_builder = (
        Path(__file__).resolve().parents[2]
        / "skills/leo-ppt-generator/scripts/build-page-worker-prompt.py"
    )
    prompt = run / "editable/upstream/pages/page_001/worker-prompt.md"
    built = subprocess.run(
        [
            sys.executable,
            str(prompt_builder),
            str(run),
            "--page",
            "page_001",
            "--cli",
            sys.executable,
            "--out",
            str(prompt),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    generated = prompt.read_text(encoding="utf-8")
    assert "{{SKILL_ROOT}}" not in generated
    assert "{{LEO_PPT}}" not in generated
    resolved_cli = str(Path(sys.executable).resolve())
    assert f'"{resolved_cli}" upstream editable-ppt -- page build' in generated

    request = json.loads(
        (run / "editable/upstream/pages/page_001/page_request.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(request)
    assert "editppt image" not in serialized
    assert "leo-ppt upstream editable-ppt -- image" in serialized


def test_status_reconciles_domain_progress_retry_resets_failed_and_cancel_times_out_active(
    tmp_path, monkeypatch
):
    run = tmp_path / "run"
    RunIndex.create(run, route="direct-editable", runtime_identity="runtime")
    sources = [png(tmp_path / "one.png"), png(tmp_path / "two.png")]
    editable = EditableAdapter(run / "editable")
    editable.prepare(sources, worker_available=True)
    jobs_path = run / "editable/page_jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs["pages"][0]["status"] = "failed"
    jobs["pages"][1]["status"] = "active"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

    status = cli.dispatch(parse("run", "status", str(run), "--json"))
    assert status["status"] == "failed"
    assert status["progress"] == {
        "total_units": 2,
        "completed": 0,
        "failed": 1,
        "active": 1,
        "pending": 0,
        "estimated_remaining_seconds": None,
    }
    retry = cli.dispatch(
        parse("run", "retry", str(run), "--from-failed-pages")
    )
    assert retry["recovery"]["reset_units"] == ["page_001"]
    replay = cli.dispatch(
        parse("run", "retry", str(run), "--from-failed-pages")
    )
    assert replay["idempotency_status"] == "replayed"

    monkeypatch.setenv("LEO_PPT_CANCEL_GRACE_SECONDS", "0")
    cancelled = cli.dispatch(
        parse("run", "cancel", str(run), "--wait-workers")
    )
    assert cancelled["worker_outcome"]["timed_out_units"] == ["page_002"]
    assert cancelled["worker_outcome"]["cancelled_units"] == ["page_001"]
    assert cancelled["status"] == "cancelled"


def test_upgrade_image_delivery_alone_does_not_complete_upgrade_run(tmp_path):
    run = tmp_path / "upgrade"
    RunIndex.create(run, route="upgrade-full", runtime_identity="runtime")
    source = png(tmp_path / "source.png")
    image = ImageDeckAdapter(run / "image-deck")
    image.prepare([{"number": 1}])
    image.record(
        1,
        source,
        backend="fixture",
        expected_revision=0,
        operation_id="image-1",
    )
    image.finalize(run / "final/image-original.pptx")
    status = cli.dispatch(parse("run", "status", str(run), "--json"))
    assert status["status"] != "completed"
    assert str((run / "final/image-original.pptx").resolve()) in status["artifact_refs"]
    assert status["next_action"]["kind"] != "none"
