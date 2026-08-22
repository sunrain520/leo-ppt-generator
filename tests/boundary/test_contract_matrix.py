from __future__ import annotations

import json
from pathlib import Path

import pytest
from leo_ppt_generator.application.run_index import IdempotencyConflict, RunIndex
from leo_ppt_generator.config.backend_contract import (
    BackendContractError,
    BackendRegistry,
)
from leo_ppt_generator.contracts import ContractError, PageArtifact
from leo_ppt_generator.hybrid.assembler import HybridAssembler
from PIL import Image

from tests.backend_fixtures import backend_contract
from tests.ppt_fixtures import build_editable_page


def artifact(tmp_path: Path, number: int, *, width=1600, height=900, validation=True):
    source = tmp_path / f"source-{number}.png"
    source_width = 160
    source_height = round(source_width * height / width)
    Image.new("RGB", (source_width, source_height), "blue").save(source)
    page, manifest = build_editable_page(
        source,
        tmp_path / f"page-{number}.pptx",
        slide_width=10,
        slide_height=10 * height / width,
    )
    if not validation:
        manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_value["text_boxes"][0]["text"] = "Changed after page build"
        manifest_value["text_inventory"] = ["Changed after page build"]
        manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
    report = tmp_path / f"validation-{number}.json"
    report.write_text(json.dumps({"passed": validation}), encoding="utf-8")
    return PageArtifact.from_source(f"page_{number:03d}", "editable", source, page, report, manifest=manifest, width=width, height=height)


def test_seven_hybrid_preconditions_fail_closed(tmp_path):
    first = artifact(tmp_path, 1)
    second = artifact(tmp_path, 2)
    assembler = HybridAssembler()

    with pytest.raises(ContractError, match="empty_deck"):
        assembler.assemble([], tmp_path / "empty.pptx")
    with pytest.raises(ContractError, match="page_order_mismatch"):
        assembler.assemble([second, first], tmp_path / "order.pptx")
    wrong_size = artifact(tmp_path, 2, width=1024, height=768)
    with pytest.raises(ContractError, match="page_size_mismatch"):
        assembler.assemble([first, wrong_size], tmp_path / "size.pptx")
    failed_validation = artifact(tmp_path, 1, validation=False)
    with pytest.raises(ContractError, match="page_validation_failed"):
        assembler.assemble([failed_validation], tmp_path / "validation.pptx")
    with pytest.raises(ContractError, match="selection_out_of_range"):
        assembler.assemble([first], tmp_path / "range.pptx", selected_pages={2})
    first_source = Path(first.source_path)
    first_source.write_bytes(b"tampered")
    with pytest.raises(ContractError, match="source_hash_mismatch"):
        assembler.assemble([first], tmp_path / "hash.pptx")
    clean = artifact(tmp_path, 1)
    with pytest.raises(ContractError, match="partial_hybrid_confirmation_required"):
        assembler.assemble([clean], tmp_path / "partial.pptx", selected_pages={1}, failures={1: "failed"})


@pytest.mark.parametrize(
    ("case", "action"),
    [
        ("config-too-new", lambda tmp: BackendRegistry.default().load({**backend_contract(), "schema_version": 2})),
        ("vendor-contract-too-new", lambda tmp: PageArtifact(schema_version=2, page_id="page_001", mode="image", source_path="x", source_sha256="x", artifact_path="x", artifact_sha256="x", validation_path=None)),
    ],
)
def test_version_contracts_fail_closed(tmp_path, case, action):
    with pytest.raises((BackendContractError, ContractError)):
        action(tmp_path)


def test_six_idempotency_replay_and_conflict_scenarios(tmp_path):
    index = RunIndex.create(tmp_path / "run", route="generate", runtime_identity="runtime")
    scenarios = [
        ("success-response-lost", "same", "same", "replay"),
        ("network-timeout", "timeout", "timeout", "replay"),
        ("provider-record", "provider", "provider", "replay"),
    ]
    for operation_id, first, replay, expected in scenarios:
        index.begin_operation(operation_id, first, mutation="record")
        index.complete_operation(operation_id, result={"ok": True})
        assert index.begin_operation(operation_id, replay, mutation="record")["outcome"] == expected
    conflicts = [
        ("success-response-lost", "different"),
        ("network-timeout", "changed-timeout"),
        ("provider-record", "changed-provider"),
    ]
    for operation_id, changed in conflicts:
        with pytest.raises(IdempotencyConflict):
            index.begin_operation(operation_id, changed, mutation="record")
