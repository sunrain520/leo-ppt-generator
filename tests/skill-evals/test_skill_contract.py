from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pytest
import yaml

from leo_ppt_generator.config.host_guard import (
    GuardDecision,
    HostProbe,
    HostReadinessGuard,
)
from leo_ppt_generator.config.models import (
    Capability,
    ConfigStatus,
    HostCapabilityState,
)
from leo_ppt_generator.config.readiness import OperationContext
from leo_ppt_generator.config.reason_codes import ReasonCode

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/leo-ppt-generator/SKILL.md"
FIRST_USE = SKILL.parent / "references/first-use.md"
HOSTS = frozenset({"codex", "claude", "kiro"})
REQUIRED_CAPABILITIES = frozenset({Capability.GENERATE})
ALL_CAPABILITIES = frozenset(Capability)


def _case_document() -> Mapping[str, Any]:
    return yaml.safe_load((Path(__file__).with_name("cases.yaml")).read_text(encoding="utf-8"))


def test_all_behavior_cases_have_route_or_failure_contract_anchors():
    cases = _case_document()["cases"]
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


def test_project_artifacts_are_scoped_to_one_project_and_run():
    body = SKILL.read_text(encoding="utf-8")
    assert "<project-root>/contracts/backend-<mode>.json" in body
    assert "--project-root <project-root>" in body
    assert "<project-root>/runs/<run-id>" in body
    assert "canonical PPTX 只写入该 run 的 `final/`" in body


def test_bundle_has_exactly_one_discoverable_skill():
    skills = list((ROOT / "skills").rglob("SKILL.md"))
    assert skills == [SKILL]
    assert not (ROOT / "skills/leo-ppt-generator/third_party").exists()


def test_both_delivery_modes_require_non_color_accessibility_cues():
    for reference in ("references/image-deck-workflow.md", "references/editable-workflow.md"):
        body = (SKILL.parent / reference).read_text(encoding="utf-8")
        assert "不得只靠颜色" in body
        assert "第二种线索" in body


def test_host_skill_eval_matrix_covers_all_supported_hosts_and_guard_paths():
    """覆盖三宿主的首次图片 guard，不需要本机安装对应宿主。"""
    specification = _case_document()["host_skill_evals"]
    cases = specification["cases"]

    if set(specification["hosts"]) != HOSTS:
        pytest.fail("三宿主 skill eval 矩阵不完整")
    if {case["id"] for case in cases} != {
        "host-available-zero-key",
        "external-unverified-first-image",
        "blocked-single-command",
        "degraded-typed-action",
        "configured-task-resume",
        "no-post-install-hook-fallback",
    }:
        pytest.fail("宿主 guard 场景集合不完整")

    for host_id in specification["hosts"]:
        for case in cases:
            _assert_contract_anchors(case, host_id)
            decision, paused = _evaluate_guard_case(case)
            _assert_guard_decision(case, host_id, decision)
            transcript = _tool_transcript(
                host_id=host_id,
                case=case,
                decision=decision,
                paused=paused,
            )
            _assert_transcript_contract(case, host_id, transcript)
            _assert_canary_absent_from_transcript(
                transcript,
                _ephemeral_canary(),
                case_id=case["id"],
                host_id=host_id,
            )


def _assert_contract_anchors(case: Mapping[str, Any], host_id: str) -> None:
    sources = {"skill": SKILL.read_text(encoding="utf-8"), "first_use": FIRST_USE.read_text(encoding="utf-8")}
    if not case.get("requires_first_use_guard"):
        _fail(case["id"], host_id, "首次使用 guard 未标记为必经")
    for anchor in case["contract_anchors"]:
        if anchor["text"] not in sources[anchor["source"]]:
            _fail(case["id"], host_id, "Skill 合同锚点缺失")


def _evaluate_guard_case(
    case: Mapping[str, Any],
) -> tuple[GuardDecision, GuardDecision | None]:
    guard = HostReadinessGuard(cli_path="/usr/local/bin/leo-ppt")
    host_state = HostCapabilityState(case["host_capability"])
    host = HostProbe(
        host_state,
        ALL_CAPABILITIES if host_state is HostCapabilityState.AVAILABLE else frozenset(),
    )
    operation_context = (
        OperationContext(
            provider="openai",
            reason_code=ReasonCode.PROVIDER_TIMEOUT,
            degraded=True,
            resume_ref=case["resume_ref"],
        )
        if case.get("operation_context") == "degraded"
        else None
    )
    initial_status = ConfigStatus(case["external_status"])

    if not case.get("recheck_external_status"):
        return (
            guard.evaluate(
                report_status=initial_status,
                required_capabilities=REQUIRED_CAPABILITIES,
                host=host,
                operation_context=operation_context,
                resume_ref=case.get("resume_ref"),
            ),
            None,
        )

    paused = guard.evaluate(
        report_status=initial_status,
        required_capabilities=REQUIRED_CAPABILITIES,
        host=host,
        resume_ref=case["resume_ref"],
    )
    return (
        guard.recheck(
            report_status=ConfigStatus(case["recheck_external_status"]),
            required_capabilities=REQUIRED_CAPABILITIES,
            host=host,
            context=paused,
            resume_ref=case["resume_ref"],
        ),
        paused,
    )


def _assert_guard_decision(
    case: Mapping[str, Any], host_id: str, decision: GuardDecision
) -> None:
    if decision.action != case["expected_action"]:
        _fail(case["id"], host_id, "guard action 不符合场景合同")
    if decision.eligibility != case["expected_eligibility"]:
        _fail(case["id"], host_id, "guard execution eligibility 不符合场景合同")
    if decision.lazy_verification is not case["expected_lazy_verification"]:
        _fail(case["id"], host_id, "首图惰性验证标记不符合场景合同")
    if case.get("resume_ref") and decision.resume_ref != case["resume_ref"]:
        _fail(case["id"], host_id, "同任务恢复引用未被保留")


def _tool_transcript(
    *,
    host_id: str,
    case: Mapping[str, Any],
    decision: GuardDecision,
    paused: GuardDecision | None,
) -> list[dict[str, Any]]:
    """只记录无敏感字段的宿主工具调用摘要，供 eval 安全扫描。"""
    transcript = [
        {"tool": "bootstrap", "arguments": {"host": host_id, "route": case["route"]}},
        {
            "tool": "setup",
            "arguments": {
                "route": case["route"],
                "host_imagegen": case["host_capability"],
            },
        },
        {"tool": "config_status", "arguments": {"route": case["route"]}},
    ]
    if paused is not None and paused.primary_action is not None:
        transcript.append({"tool": "primary_action", "arguments": dict(paused.primary_action)})
        transcript.append(
            {"tool": "config_status_recheck", "arguments": {"route": case["route"]}}
        )
    if decision.primary_action is not None:
        transcript.append({"tool": "primary_action", "arguments": dict(decision.primary_action)})
    transcript.append({"tool": f"guard_{decision.action}", "arguments": {}})
    if decision.lazy_verification:
        transcript.append({"tool": "first_business_image", "arguments": {"route": case["route"]}})
    return transcript


def _assert_transcript_contract(
    case: Mapping[str, Any], host_id: str, transcript: list[Mapping[str, Any]]
) -> None:
    tools = {event["tool"] for event in transcript}
    if not set(case["expected_transcript_tools"]).issubset(tools):
        _fail(case["id"], host_id, "工具转录缺少预期调用")
    if case.get("post_install_hook") == "unavailable" and "post_install_hook" in tools:
        _fail(case["id"], host_id, "无 post-install hook 场景错误依赖安装回调")

    primary_actions = [event["arguments"] for event in transcript if event["tool"] == "primary_action"]
    if [action.get("kind") for action in primary_actions] != case["expected_primary_action_kinds"]:
        _fail(case["id"], host_id, "Primary_Action 类型或数量不符合场景合同")
    command_count = sum(action.get("command") is not None for action in primary_actions)
    if command_count != case["expected_command_count"]:
        _fail(case["id"], host_id, "展示给用户的命令数量不符合场景合同")


def _ephemeral_canary() -> str:
    """仅作为扫描输入存在；不得进入转录、断言或磁盘。"""
    return f"skill-eval-canary-{uuid4().hex}"


def _assert_canary_absent_from_transcript(
    transcript: list[Mapping[str, Any]],
    canary: str,
    *,
    case_id: str,
    host_id: str,
) -> None:
    if _contains_text(transcript, canary):
        _fail(case_id, host_id, "工具转录包含敏感值")


def _contains_text(value: Any, marker: str) -> bool:
    if isinstance(value, str):
        return marker in value
    if isinstance(value, Mapping):
        return any(_contains_text(key, marker) or _contains_text(item, marker) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_text(item, marker) for item in value)
    return False


def _fail(case_id: str, host_id: str, reason: str) -> None:
    pytest.fail(f"host skill eval {host_id}/{case_id}: {reason}")
