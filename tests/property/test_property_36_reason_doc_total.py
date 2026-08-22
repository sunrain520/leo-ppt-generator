# Feature: guided-provider-config, Property 36: Reason documentation is total
# and single-action

from __future__ import annotations

import re
from pathlib import Path

from leo_ppt_generator.config.reason_codes import (
    ConfigCommandVerb,
    PrimaryActionKind,
    REASON_CATALOG,
    ReasonCode,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "skills/leo-ppt-generator/references/reason-codes.md"


def _documented_reasons(document: str) -> set[str]:
    return set(re.findall(r"`([a-z][a-z0-9_]+(?::[a-z][a-z0-9_]+)?)`", document))


def test_property_36_every_user_repairable_reason_has_document_and_action():
    """**Validates: Requirements 17.6**"""
    document = DOC.read_text(encoding="utf-8")
    documented = _documented_reasons(document)

    for code, definition in REASON_CATALOG.items():
        if not definition.user_repairable:
            continue
        # 用户可修复的稳定 Reason_Code 必须有文档条目。
        assert code.value in documented, f"{code.value} 缺文档条目"
        # 用户可修复必须有恰好一个默认动作。
        assert definition.default_action is not None, f"{code.value} 缺默认动作"
        action = definition.default_action
        # run_cli 动作必须带 config 命令 verb（repair/verify/change/config）；
        # 唯一例外是 cli_path_unresolved —— 它只能使用 launcher 修复命令。
        if action.kind is PrimaryActionKind.RUN_CLI:
            if code is ReasonCode.CLI_PATH_UNRESOLVED:
                assert action.command_verb is None
            else:
                assert action.command_verb is not None, f"{code.value} run_cli 缺 verb"
                assert action.command_verb in {
                    ConfigCommandVerb.CONFIG,
                    ConfigCommandVerb.REPAIR,
                    ConfigCommandVerb.VERIFY,
                    ConfigCommandVerb.CHANGE,
                }, f"{code.value} verb 非法"


def _table_reason_codes(document: str) -> set[str]:
    """只提取 reason code 表格行中的反引号 code（表格第一列）。"""
    result: set[str] = set()
    for line in document.splitlines():
        if not line.startswith("|"):
            continue
        match = re.match(r"^\|\s*`([a-z][a-z0-9_]+(?::[a-z][a-z0-9_]+)?)`", line)
        if match:
            result.add(match.group(1))
    return result


def test_property_36_reason_document_has_no_orphan_entries():
    """**Validates: Requirements 17.6**

    只对 guided-provider-config 新增的控制面区段做孤儿检查：该区段是
    本功能文档化的全部 code，必须全部属于 ReasonCode 枚举。
    """
    document = DOC.read_text(encoding="utf-8")
    section = document.split("## 配置与验证控制面（guided-provider-config）", 1)[1]
    section = section.split("\n## ", 1)[0]
    table_codes = _table_reason_codes(section)
    known = {code.value for code in ReasonCode}
    orphans = table_codes - known
    assert not orphans, f"控制面区段表格包含未知 reason code: {sorted(orphans)}"


def test_property_36_every_stable_reason_code_is_documented():
    """**Validates: Requirements 17.6**"""
    document = DOC.read_text(encoding="utf-8")
    document_text = document
    documented = _documented_reasons(document_text)
    # 大量 catalog code 必须全部出现在文档中（test_reason_code_docs 已
    # 覆盖扫描逻辑，此处补 catalog 全集闭合）。
    for code in ReasonCode:
        assert code.value in document, f"{code.value} 未出现在 reason-codes.md"