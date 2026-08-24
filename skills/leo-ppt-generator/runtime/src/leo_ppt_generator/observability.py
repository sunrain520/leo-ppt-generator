"""运行级脱敏日志、耗时与最终交付报告。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from .storage import atomic_write_json, canonical_json, sha256_file

_PRIMARY_ACTIONS: dict[str, dict[str, str]] = {
    "unknown_route": {
        "id": "choose_supported_route",
        "command": "leo-ppt setup --route <generate|direct-editable|upgrade-full|upgrade-selected>",
        "verification": "重新运行 setup，确认 route 已通过检查。",
    },
    "setup_local_mechanism_blocked": {
        "id": "repair_runtime_config",
        "command": "leo-ppt doctor --route {route} --json",
        "verification": "修复 doctor 返回的原始原因后重新运行 setup。",
    },
    "credential_resolver_unavailable": {
        "id": "enable_credential_resolver",
        "command": "leo-ppt auth status --provider {provider}",
        "verification": "凭据状态变为 available 后重新运行 setup。",
    },
    "host_image_capability_unknown": {
        "id": "declare_host_image_capability",
        "command": "leo-ppt setup --route {route} --host-imagegen <available|unavailable>",
        "verification": "setup 报告中的 host capability 不再为 unknown。",
    },
    "image_provider_configuration_required": {
        "id": "configure_image_provider",
        "command": "leo-ppt config",
        "verification": "凭据状态变为 available 后重新运行 setup。",
    },
    "host_image_capability_unavailable": {
        "id": "select_external_provider",
        "command": "leo-ppt setup --route {route} --host-imagegen unavailable --provider <openai|openai-compatible|atlascloud>",
        "verification": "selected_provider 为外部 Provider 且状态为 ready。",
    },
    "provider_confirmation_required": {
        "id": "confirm_provider",
        "command": "leo-ppt setup --route {route} --host-imagegen unavailable --provider {provider}",
        "verification": "selected_provider 与确认的 provider 一致且状态为 ready。",
    },
    "provider_choice_required": {
        "id": "choose_provider",
        "command": "leo-ppt setup --route {route} --host-imagegen unavailable --provider <openai|atlascloud>",
        "verification": "selected_provider 与选择一致且状态为 ready。",
    },
    "provider_capability_required": {
        "id": "select_capable_provider",
        "command": "leo-ppt config provider configure --provider {provider}",
        "verification": "重新运行 setup，确认所选 Provider 满足 route_capabilities。",
    },
    "selected_provider_unavailable": {
        "id": "configure_selected_provider",
        "command": "leo-ppt config provider configure --provider {provider}",
        "verification": "所选 provider 的凭据状态变为 available 后重新运行 setup。",
    },
    "provider_priority_tie": {
        "id": "resolve_provider_priority",
        "command": "leo-ppt config provider priority --provider <provider> --value <1-1000>",
        "verification": "重新运行 config status，确认自动选择返回唯一 Provider。",
    },
    "provider_selection_required": {
        "id": "configure_provider_selection",
        "command": "leo-ppt config",
        "verification": "重新运行 config status，确认存在可自动选择的 Provider。",
    },
    "requested_provider_unavailable": {
        "id": "configure_requested_provider",
        "command": "leo-ppt config provider configure --provider <provider>",
        "verification": "重新运行 setup，确认指定 Provider 满足当前 route。",
    },
    "unknown_backend": {
        "id": "choose_supported_provider",
        "command": "leo-ppt setup --route {route} --provider <builtin-imagegen|openai|openai-compatible|atlascloud>",
        "verification": "重新运行 setup，确认 provider 出现在 provider_options 中。",
    },
    "setup_schema_version_unsupported": {
        "id": "upgrade_runtime",
        "command": "运行安装器的升级命令",
        "verification": "setup-report schema_version 为 1 后重新验证。",
    },
    "openai_compatible_configuration_required": {
        "id": "configure_openai_compatible_provider",
        "command": "leo-ppt config provider configure --provider openai-compatible",
        "verification": "重新运行 setup，确认中转站端点和模型已就绪。",
    },
}


def primary_action_for(reason_code: str, **replacements: str) -> dict[str, str]:
    """返回 setup 阻断原因的唯一稳定恢复动作。"""

    try:
        action = dict(_PRIMARY_ACTIONS[reason_code])
    except KeyError as exc:
        raise ValueError("primary_action_mapping_missing") from exc
    for key in ("command", "verification"):
        action[key] = action[key].format_map(_SafeReplacements(replacements))
    return action


class _SafeReplacements(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return f"<{key}>"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def command_name(args: Any) -> str:
    parts = [getattr(args, "command", None)]
    for name in (
        "config_command",
        "config_provider_command",
        "config_credential_command",
        "backend_command",
        "run_command",
        "image_command",
        "editable_command",
        "upgrade_command",
        "delivery_command",
        "evidence_command",
    ):
        value = getattr(args, name, None)
        if value:
            parts.append(value)
    return ".".join(value for value in parts if value) or "unknown"


def resolve_run_dir(args: Any) -> Path | None:
    value = getattr(args, "run_path", None) or getattr(args, "run_dir", None)
    if not value and getattr(args, "command", None) == "run" and getattr(args, "run_command", None) == "create":
        value = getattr(args, "output", None)
    if not value:
        return None
    path = Path(value).resolve()
    return path if path.is_dir() or path.parent.is_dir() else None


def record_command(
    run_dir: Path | None,
    *,
    command: str,
    started_at: str,
    duration_seconds: float,
    status: str,
    reason_code: str,
    page_measurement: dict[str, Any] | None = None,
    backend_measurement: dict[str, Any] | None = None,
) -> None:
    if run_dir is None or not run_dir.is_dir():
        return
    logs = run_dir / "logs"
    reports = run_dir / "reports"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    reports.mkdir(parents=True, exist_ok=True, mode=0o700)
    entry = {
        "timestamp": utc_now(),
        "level": "ERROR" if status in {"blocked", "failed", "interrupted"} else "INFO",
        "component": "cli",
        "event": "command_completed",
        "command": command,
        "status": status,
        "reason_code": reason_code,
        "duration_ms": round(duration_seconds * 1000),
    }
    log_path = logs / "run.log"
    with FileLock(str(run_dir / ".run.log.lock")):
        descriptor = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (canonical_json(entry) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    timing_path = reports / "timing.json"
    with FileLock(str(run_dir / ".timing.json.lock")):
        if timing_path.is_file():
            try:
                timing = json.loads(timing_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                timing = {}
        else:
            timing = {}
        run_id = None
        run_index = run_dir / "run.json"
        if run_index.is_file():
            try:
                run_id = json.loads(run_index.read_text(encoding="utf-8")).get("run_id")
            except (OSError, json.JSONDecodeError):
                pass
        stages = timing.get("stages") if isinstance(timing.get("stages"), list) else []
        pages = timing.get("pages") if isinstance(timing.get("pages"), list) else []
        backend_calls = (
            timing.get("backend_calls")
            if isinstance(timing.get("backend_calls"), list)
            else []
        )
        stages.append(
            {
                "stage": command,
                "started_at": started_at,
                "completed_at": entry["timestamp"],
                "duration_seconds": round(duration_seconds, 6),
                "status": status,
                "reason_code": reason_code,
            }
        )
        if page_measurement:
            pages.append(page_measurement)
        if backend_measurement:
            backend_calls.append(backend_measurement)
        total = sum(float(item.get("duration_seconds", 0)) for item in stages)
        atomic_write_json(
            timing_path,
            {
                "schema_version": 1,
                "run_id": run_id,
                "stages": stages,
                "pages": pages,
                "backend_calls": backend_calls,
                "summary": {"total_duration_seconds": round(total, 6)},
            },
        )


def write_delivery_reports(run_dir: Path, result: dict[str, Any]) -> list[str]:
    """从 finalizer 的确定性结果派生验证和失败报告。"""
    if not (run_dir / "run.json").is_file():
        return []
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    pptx = Path(result["pptx"]).resolve()
    pages = result.get("pages", [])
    page_count = len(pages) if pages else int(result.get("page_count", 0))
    validation_refs = [
        page["validation_ref"]
        for page in pages
        if isinstance(page, dict) and page.get("validation_ref")
    ]
    summary_path = run_dir / "final" / "validation-summary.json"
    structural_passed = pptx.is_file() and sha256_file(pptx) == result.get(
        "pptx_sha256", sha256_file(pptx)
    )
    atomic_write_json(
        summary_path,
        {
            "schema_version": 1,
            "run_id": run["run_id"],
            "route": run["route"],
            "delivery_type": result["delivery_type"],
            "passed": structural_passed,
            "pptx": str(pptx),
            "pptx_sha256": sha256_file(pptx),
            "page_count": page_count,
            "validation_refs": validation_refs,
            "quality_gates": {
                "content_facts": {"status": "not_recorded"},
                "narrative_structure": {"status": "not_recorded"},
                "visual_render": {"status": "not_run"},
                "pptx_structure": {
                    "status": "passed" if structural_passed else "failed"
                },
                "desktop_open": {"status": "not_run"},
                "manual_visual_acceptance": {"status": "not_run"},
            },
            "claim_ceiling": "自动 finalizer 只证明 PPTX 结构与 hash；其余质量门需要独立 receipt。",
        },
    )
    refs = [str(summary_path)]
    failures = result.get("failures") or {}
    if failures:
        failure_path = run_dir / "final" / "failure-report.json"
        atomic_write_json(
            failure_path,
            {
                "schema_version": 1,
                "run_id": run["run_id"],
                "route": run["route"],
                "delivery_type": result["delivery_type"],
                "failures": failures,
                "recovery_action": "修复失败页后执行 editable reset/record，再重新 finalize。",
            },
        )
        refs.append(str(failure_path))
    return refs
