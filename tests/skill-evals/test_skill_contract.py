from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/leo-ppt-generator/SKILL.md"


def test_all_behavior_cases_have_route_or_failure_contract_anchors():
    cases = yaml.safe_load((Path(__file__).with_name("cases.yaml")).read_text(encoding="utf-8"))["cases"]
    body = SKILL.read_text(encoding="utf-8")
    assert len(cases) == 25
    for case in cases:
        route = case["expected_route"]
        if route != "any":
            assert f"### {route}" in body
        if case.get("expected_reason"):
            assert case["expected_reason"] in body
        if case.get("expected_reference_anchor"):
            references = "\n".join(
                (SKILL.parent / path).read_text(encoding="utf-8")
                for path in case.get("required_references", [])
            )
            assert case["expected_reference_anchor"] in references


def test_progressive_route_references_and_legacy_entrypoint_ban_are_explicit():
    body = SKILL.read_text(encoding="utf-8")
    assert "generate" in body and "references/image-deck-workflow.md" in body
    assert "direct-editable" in body and "references/editable-workflow.md" in body
    assert "references/first-use.md" in body
    assert "不要让普通用户执行 runtime 初始化命令" in body
    assert "不得调用、安装或要求用户安装额外历史 CLI" in body
    assert "SKILL_DIR=" not in body
    assert "print-cli" not in body
    assert "自由文本不构成完成证据" in body


def test_bundle_has_exactly_one_discoverable_skill():
    skills = list((ROOT / "skills").rglob("SKILL.md"))
    assert skills == [SKILL]
    assert not (ROOT / "skills/leo-ppt-generator/third_party").exists()


def test_both_delivery_modes_require_non_color_accessibility_cues():
    for reference in ("references/image-deck-workflow.md", "references/editable-workflow.md"):
        body = (SKILL.parent / reference).read_text(encoding="utf-8")
        assert "不得只靠颜色" in body
        assert "第二种线索" in body
