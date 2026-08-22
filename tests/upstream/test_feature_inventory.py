import hashlib
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "skills/leo-ppt-generator"
INVENTORY = SKILL_ROOT / "upstream-capabilities.yaml"
UPSTREAM_METADATA = SKILL_ROOT / "upstreams.yaml"
UPSTREAM_ROOTS = {
    "codex-ppt": REPO_ROOT.parent / "codex-ppt-skill",
    "image-to-editable-ppt": REPO_ROOT.parent / "image-to-editable-ppt-skill",
}


def test_every_upstream_capability_has_real_integration_and_proof_owner():
    data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    capabilities = data["capabilities"]
    ids = [entry["id"] for entry in capabilities]
    assert len(ids) == len(set(ids))
    assert len(capabilities) == 60
    for entry in capabilities:
        assert entry["disposition"] in {"integrated", "enhanced", "adapted", "replaced"}
        assert (SKILL_ROOT / entry["integration"]).exists(), entry
        assert (REPO_ROOT / entry["proof"]).is_file(), entry
        proof_case = entry.get("proof_case")
        assert isinstance(proof_case, str) and "::" in proof_case, entry
        assert proof_case.startswith(f"{entry['proof']}::"), entry


def test_capability_inventory_discloses_proof_reuse_without_requiring_duplicate_tests():
    data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    proof_counts = Counter(entry["proof_case"] for entry in data["capabilities"])

    assert len(proof_counts) == 42
    assert max(proof_counts.values()) == 6


def test_every_upstream_capability_proof_case_is_collected_by_pytest():
    data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    collected = {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }
    missing = {
        entry["id"]: entry["proof_case"]
        for entry in data["capabilities"]
        if entry["proof_case"] not in collected
    }
    assert not missing


def test_file_rules_cover_only_real_integration_targets():
    data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    assert len(data["file_rules"]) == 14
    for rule in data["file_rules"]:
        assert rule["disposition"] in {
            "vendored",
            "merged",
            "exact-copy",
            "replaced",
            "adapted",
            "regression-bound",
        }
        target = SKILL_ROOT / rule["integration"]
        if not target.exists():
            target = REPO_ROOT / rule["integration"]
        assert target.exists(), rule


def test_all_twelve_builtin_styles_are_integrated():
    styles = sorted((SKILL_ROOT / "references/styles").glob("*.md"))
    assert len(styles) == 12
    assert all(path.stat().st_size > 500 for path in styles)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_upstream_python_file_is_vendored_or_explicitly_patched():
    codex_root = UPSTREAM_ROOTS["codex-ppt"]
    editable_root = UPSTREAM_ROOTS["image-to-editable-ppt"]
    if not codex_root.is_dir() or not editable_root.is_dir():
        pytest.skip("named upstream source worktrees are unavailable")

    codex_source = codex_root / "skills/codex-ppt/scripts"
    codex_vendor = SKILL_ROOT / "runtime/src/leo_ppt_generator/_vendor/codex_ppt"
    editable_source = editable_root / "skills/image-to-editable-ppt/cli/editppt"
    editable_vendor = SKILL_ROOT / "runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt"
    allowed_patches = {
        "codex-ppt:slide_run_state.py",
        "codex-ppt:assemble_ppt.py",
        "codex-ppt:remove_chroma_key.py",
        "image-to-editable-ppt:runtime/deck_run_state.py",
        "image-to-editable-ppt:runtime/_input_normalization.py",
        "image-to-editable-ppt:runtime/validate_pptx.py",
    }
    seen_patches = set()
    checked = 0
    for upstream, source_root, vendor_root in (
        ("codex-ppt", codex_source, codex_vendor),
        ("image-to-editable-ppt", editable_source, editable_vendor),
    ):
        sources = sorted(source_root.rglob("*.py"))
        assert len(sources) == (15 if upstream == "codex-ppt" else 28)
        for source in sources:
            relative = source.relative_to(source_root)
            target = vendor_root / relative
            assert target.is_file(), f"missing vendor mapping: {upstream}:{relative}"
            key = f"{upstream}:{relative.as_posix()}"
            if _digest(source) != _digest(target):
                assert key in allowed_patches, f"unregistered vendor drift: {key}"
                seen_patches.add(key)
            checked += 1
    assert checked == 43
    assert seen_patches == allowed_patches


def test_exact_contract_assets_match_named_upstreams():
    codex_root = UPSTREAM_ROOTS["codex-ppt"]
    editable_root = UPSTREAM_ROOTS["image-to-editable-ppt"]
    if not codex_root.is_dir() or not editable_root.is_dir():
        pytest.skip("named upstream source worktrees are unavailable")
    pairs = [
    ]
    source_styles = codex_root / "skills/codex-ppt/references"
    for source in sorted(source_styles.glob("*.md")):
        pairs.append((source, SKILL_ROOT / "references/styles" / source.name))
    assert len(pairs) == 12
    for source, integrated in pairs:
        assert _digest(source) == _digest(integrated), (source, integrated)


def test_adapted_slide_worker_preserves_upstream_contract_without_old_cli():
    prompt = (SKILL_ROOT / "prompts/slide-worker.md").read_text(encoding="utf-8")
    for anchor in (
        "approved sample",
        "required source images",
        "Forbidden for final slide image creation",
        "blocker=<reason>",
        "backend_used=",
        "selected_source=",
        "qa_note=",
    ):
        assert anchor in prompt
    assert "scripts/image_gen.py" not in prompt
    assert '"<absolute leo-ppt CLI path>" upstream codex-ppt -- image' in prompt
    assert "`leo-ppt upstream" not in prompt


def test_adapted_page_worker_preserves_upstream_contract_without_old_cli():
    prompt = (SKILL_ROOT / "prompts/page-worker.md").read_text(encoding="utf-8")
    for anchor in (
        "page-decision-tree.md",
        "manifest-schema.md",
        "cli-helper.md",
        "validation.json",
        "page_result.json",
        "Final Self-Check",
    ):
        assert anchor in prompt
    assert "`editppt " not in prompt
    assert '"{{LEO_PPT}}" upstream editable-ppt --' in prompt
    assert "`leo-ppt upstream" not in prompt


def test_registered_vendor_patches_apply_to_pinned_source_worktrees():
    metadata = yaml.safe_load(UPSTREAM_METADATA.read_text(encoding="utf-8"))
    cases = [
        (UPSTREAM_ROOTS[upstream], SKILL_ROOT / patch)
        for upstream, entry in metadata["upstreams"].items()
        for patch in entry["patches"]
    ]
    assert len(cases) == 6
    assert all(patch.is_file() for _, patch in cases)
    if not all(root.is_dir() for root, _ in cases):
        pytest.skip("named upstream source worktrees are unavailable")
    for root, patch in cases:
        result = subprocess.run(
            ["git", "apply", "--check", str(patch)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (patch, result.stderr)


def test_named_source_heads_match_audited_commits():
    data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    for name, source in data["audited_sources"].items():
        root = UPSTREAM_ROOTS[name]
        if not root.is_dir():
            pytest.skip("named upstream source worktrees are unavailable")
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == source["commit"]
