from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "skills/leo-ppt-generator/runtime/src/leo_ppt_generator"
DOC = ROOT / "skills/leo-ppt-generator/references/reason-codes.md"


def test_every_owned_reason_code_is_documented():
    codes: set[str] = {
        "upstream_setup_replaced_by_runtime_manager",
        "raw_credential_configuration_forbidden",
    }
    error_types = {
        "ContractError",
        "RouteContractError",
        "BackendContractError",
        "BackendExecutionError",
        "SetupContractError",
        "CleanupConflict",
        "IdempotencyConflict",
        "EvidenceError",
        "RevisionConflict",
        "UpstreamBridgeError",
    }
    for path in PACKAGE.rglob("*.py"):
        if "_vendor" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                else:
                    continue
                index = 1 if name in {"envelope", "_run_result"} else 0
                if name in error_types | {"envelope", "_run_result"} and len(node.args) > index:
                    value = node.args[index]
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and re.fullmatch(r"[a-z][a-z0-9_]+", value.value)
                    ):
                        codes.add(value.value)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(target, ast.Name) and target.id == "reason_code" for target in targets):
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        codes.add(value.value)
    document = DOC.read_text(encoding="utf-8")
    missing = sorted(code for code in codes if f"`{code}`" not in document)
    assert missing == []
