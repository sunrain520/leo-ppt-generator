"""leo-ppt 的版本化确定性命令接口。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .application.routes import (
    ROUTES,
    RouteContractError,
    classify_input,
    route_definition,
    select_route,
)
from .application.run_index import IdempotencyConflict, RevisionConflict, RunIndex
from .backend_execution import BackendExecutionError
from .config.backend_contract import BackendContractError, BackendRegistry
from .config.provider_registry import ProviderRegistry
from .config.receipt_store import FileReceiptStore
from .config.models import HostCapabilityState, ProviderName, RouteName
from .config.reason_codes import ReasonCode
from .config.service import ConfigService, ConfigServiceError, StatusRequest
from .config.wizard import ConfigWizard, WizardCancelled
from .config.runtime_config import (
    RuntimeConfigError,
    assert_run_quota,
    configure_openai_compatible_profile,
    default_home,
    load_runtime_config,
    openai_compatible_profile,
)
from .contracts import ContractError, PageArtifact
from .credentials import (
    PROVIDERS,
    CredentialError,
    CredentialInputResolver,
    credential_manager,
)
from .editable.adapter import EditableAdapter
from .evidence import EvidenceError, record_acceptance, record_provenance, record_visual
from .hybrid.assembler import HybridAssembler
from .image_deck.adapter import ImageDeckAdapter
from .lifecycle import CleanupConflict, Lifecycle
from .observability import (
    command_name,
    record_command,
    resolve_run_dir,
    primary_action_for,
    utc_now,
    write_delivery_reports,
)
from .setup import SetupContractError, build_setup_report, render_setup_report
from .storage import (
    atomic_write_json,
    canonical_json,
    durable_copy_file,
    fsync_directory,
    inspect_regular_file,
    secure_user_tree,
    sha256_bytes,
)
from .styles import StyleStoreError, list_styles, load_style, save_style
from .templates import TemplateError, compose_layout, compose_style, list_templates
from .upgrade.baseline import (
    import_baseline,
    inspect_image_delivery,
    load_baseline,
)
from .upstream_bridge import CODEX_TOOLS, UpstreamBridgeError, run_upstream

PROTOCOL = "leo-ppt-machine/v1"
MAX_SLIDES_CONTRACT_BYTES = 1024 * 1024


def _duration_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("duration must be a number") from exc
    if parsed < 0 or parsed > 7 * 24 * 60 * 60:
        raise argparse.ArgumentTypeError("duration must be between 0 and 604800 seconds")
    return parsed


def envelope(status: str, reason_code: str, **payload: Any) -> dict[str, Any]:
    result = {
        "protocol": PROTOCOL,
        "schema_version": 1,
        "status": status,
        "reason_code": reason_code,
        **payload,
    }
    result.setdefault("artifact_refs", [])
    result.setdefault("evidence_refs", [])
    result.setdefault("warnings", [])
    result.setdefault("blockers", [])
    result.setdefault("message", f"操作结果：{reason_code}")
    result.setdefault(
        "suggested_actions",
        ["运行 run diagnose 并按 reason-codes.md 处理"]
        if status in {"blocked", "failed", "interrupted"}
        else [],
    )
    return result


def _version_report() -> dict[str, Any]:
    """返回不读取配置、不访问网络的版本合同。"""

    runtime_identity = None
    bundle_root = None
    install_channel = None
    try:
        current = json.loads((default_home() / "current").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        current = {}
    if isinstance(current.get("runtime_identity"), str):
        runtime_identity = current["runtime_identity"]
    if isinstance(current.get("bundle_root"), str):
        bundle_root = current["bundle_root"]
    _KNOWN_CHANNELS = {"plugin", "agent-skill", "standalone"}
    recorded = current.get("install_channel")
    if isinstance(recorded, str) and recorded in _KNOWN_CHANNELS:
        install_channel = recorded
    else:
        # 元数据缺失或非法渠道（空串、手改值）时按 bundle 路径推导，不原样透传。
        normalized_bundle = str(bundle_root or "").replace("\\", "/")
        if "/plugins/" in normalized_bundle:
            install_channel = "plugin"
        elif "/.agents/skills/" in normalized_bundle:
            install_channel = "agent-skill"
        elif bundle_root:
            install_channel = "standalone"
        else:
            install_channel = "unknown"
    return {
        "protocol": "leo-ppt-version/v1",
        "schema_version": 1,
        "status": "ready",
        "reason_code": "version_reported",
        "package_version": __version__,
        "runtime_version": __version__,
        "runtime_identity": runtime_identity,
        "install_channel": install_channel,
        "config_schema_version": 1,
        "setup_schema_version": 1,
        "cli_path": str(Path(sys.argv[0]).resolve()) if sys.argv else None,
    }


def _runtime_manager_metadata() -> tuple[Path, Path] | None:
    """读取安装 manager 的受管 current 元数据。"""

    current_path = default_home() / "current"
    try:
        value = json.loads(current_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    manager = value.get("runtime_manager")
    bundle = value.get("bundle_root")
    if not isinstance(manager, str) or not isinstance(bundle, str):
        return None
    manager_path = Path(manager).expanduser().resolve()
    bundle_path = Path(bundle).expanduser().resolve()
    if not manager_path.is_file() or not bundle_path.is_dir():
        return None
    return manager_path, bundle_path


def _dispatch_runtime_lifecycle(args: argparse.Namespace) -> dict[str, Any]:
    metadata = _runtime_manager_metadata()
    if metadata is None:
        return envelope(
            "blocked",
            "runtime_manager_unavailable",
            primary_action={"kind": "run_cli", "command": "重新运行安装器或 bootstrap"},
        )
    manager, _bundle = metadata
    command = [sys.executable, str(manager)]
    confirmation_required = False
    if args.command == "update":
        ref = args.version or "main"
        if args.check:
            command.extend(["check", "--ref", ref])
        elif not args.dry_run and not args.yes:
            confirmation_required = True
            command.extend(["check", "--ref", ref])
        else:
            command.extend(["update", "--ref", ref])
            if args.dry_run:
                command.append("--dry-run")
    else:
        command.extend(["rollback"])
        if args.identity:
            command.extend(["--identity", args.identity])
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return envelope("blocked", "runtime_lifecycle_unavailable", message=str(exc))
    stream = result.stdout if result.stdout.strip() else result.stderr
    try:
        payload = json.loads(stream)
    except (TypeError, json.JSONDecodeError):
        return envelope(
            "blocked",
            "runtime_lifecycle_protocol_invalid",
            details={"stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]},
        )
    if not isinstance(payload, dict):
        return envelope("blocked", "runtime_lifecycle_protocol_invalid")
    if confirmation_required:
        if payload.get("update_available"):
            return envelope(
                "action_required",
                "update_confirmation_required",
                runtime=payload,
                primary_action={"kind": "run_cli", "command": "leo-ppt update --yes"},
            )
        return envelope(
            "ready",
            str(payload.get("reason_code", "release_current")),
            runtime=payload,
        )
    status = "ready" if result.returncode == 0 else "blocked"
    reason = str(
        payload.get(
            "reason_code",
            "runtime_update_checked" if args.command == "update" else "runtime_rolled_back",
        )
    )
    if result.returncode != 0:
        reason = str(payload.get("reason_code", "runtime_lifecycle_failed"))
    return envelope(status, reason, runtime=payload)


def doctor_report(route: str | None) -> dict[str, Any]:
    if route is not None and route not in ROUTES:
        return envelope(
            "blocked",
            "unknown_route",
            route=route,
            checks={"package_import": "passed", "route": "failed"},
            warnings=[],
        )
    required = {"generate"} if route == "generate" else ({"edit"} if route else set())
    backend = BackendRegistry.default().select("fixture", required=required)
    config_error: RuntimeConfigError | None = None
    try:
        config = load_runtime_config()
        config_report: dict[str, Any] = {
            "status": "passed",
            "path": str(config.path),
            "values": {
                key: {"value": value, "source": config.sources[key], "route": route or "all"}
                for key, value in config.values.items()
            },
            "warnings": list(config.warnings),
        }
    except RuntimeConfigError as exc:
        config_error = exc
        config_report = {
            "status": "failed",
            "reason_code": str(exc),
            "path": str(default_home() / "config.yaml"),
            "values": {},
            "warnings": [],
        }
    directory_fsync = fsync_directory(Path(__file__).resolve().parent)
    warnings = [
        "真实 provider、OCR、Office viewer 与 PowerPoint 桌面仍需分别现场验证。",
        *config_report["warnings"],
    ]
    if not directory_fsync:
        warnings.append("当前文件系统不支持目录 fsync；barrier durability 已降级。")
    office_viewer = shutil.which("libreoffice") or shutil.which("soffice")
    office_needed = route in {"direct-editable", "upgrade-full", "upgrade-selected"}
    manager = credential_manager()

    def credential_reference(provider: str) -> dict[str, Any]:
        try:
            report = manager.status(provider)
        except CredentialError:
            return {
                "status": "resolver_unavailable",
                "reference_type": "os-store",
                "evidence_refs": [f"credential://status/{provider}"],
            }
        return {
            "status": report["status"],
            "reference_type": report["reference_type"],
            "evidence_refs": report["evidence_refs"],
        }

    credential_references = {
        "builtin-imagegen": {"status": "host_check_required", "reference_type": "host-managed", "evidence_refs": ["doctor://credential/builtin-imagegen"]},
        **{provider: credential_reference(provider) for provider in PROVIDERS},
    }
    provider_available = any(
        credential_references[provider]["status"] == "available"
        for provider in ("openai", "openai-compatible", "atlascloud")
    )
    compatible_profile = openai_compatible_profile() if config_error is None else None
    readiness = {
        "local_runtime": {"status": "ready", "reason_code": "package_import_passed"},
        "config": config_report,
        "credential_reference": {
            "status": "available" if provider_available else "missing",
            "reason_code": "credential_reference_available" if provider_available else "credential_reference_missing",
        },
        "worker": {
            "status": "host_check_required",
            "reason_code": "worker_host_capability_unverified",
        },
        "provider": {
            "status": "not_probed",
            "reason_code": "provider_field_smoke_required",
        },
        "office_viewer": {
            "status": "available" if office_viewer else ("optional_missing" if office_needed else "not_required"),
            "path": office_viewer,
        },
        "manual_acceptance": {
            "status": "required",
            "reason_code": "manual_visual_acceptance_required",
        },
        "route_contract": {"status": "passed" if route else "not_requested"},
    }
    status = "blocked" if config_error else "ready"
    reason_code = str(config_error) if config_error else "ready"
    readiness_summary = {
        "local_mechanism": "blocked" if config_error else "ready",
        "field_execution": "action_required",
        "next_actions": (
            ["fix_runtime_config"]
            if config_error
            else [
                "create_and_validate_backend_contract",
                "verify_worker_capability",
                "run_provider_smoke",
                "record_manual_acceptance",
            ]
        ),
    }
    return envelope(
        status,
        reason_code,
        route=route,
        checks={
            "package_import": "passed",
            "route": "passed" if route else "not_requested",
            "image_deck_adapter": "passed",
            "editable_adapter": "passed",
            "backend_contract": backend.name,
            "directory_fsync": "passed" if directory_fsync else "degraded",
            "office_viewer": office_viewer or ("optional_missing" if office_needed else "not_required"),
        },
        config=config_report["values"],
        readiness=readiness,
        readiness_summary=readiness_summary,
        credential_references=credential_references,
        provider_profiles={
            "openai-compatible": {
                "status": "available" if compatible_profile else "missing",
                "endpoint_origin": compatible_profile.get("endpoint_origin") if compatible_profile else None,
                "model": compatible_profile.get("model") if compatible_profile else None,
            }
        },
        warnings=warnings,
    )


def _json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_pages(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(item) for item in value.split(",") if item.strip()}


def _runtime_identity(explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("LEO_PPT_RUNTIME_IDENTITY")
    if configured:
        return configured
    executable = Path(sys.executable).absolute()
    # macOS venv 的 python 通常是指向 Homebrew/framework Python 的符号链接。
    # 先沿调用路径查找受管 runtime receipt；resolve 后的解释器路径只作兼容回退。
    candidates = (executable, executable.resolve())
    seen: set[Path] = set()
    for candidate in candidates:
        for parent in candidate.parents:
            if parent in seen:
                continue
            seen.add(parent)
            receipt = parent / "runtime.json"
            if receipt.is_file():
                try:
                    value = _json_file(receipt)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                identity = value.get("runtime_identity")
                if isinstance(identity, str) and identity:
                    return identity
    return f"development-{__version__}"


def _run_path(args: argparse.Namespace) -> str:
    value = getattr(args, "run_path", None) or getattr(args, "run_dir", None)
    if not value:
        raise ContractError("run_path_required")
    return str(value)


def _state_hash(run: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(run).encode())


def _domain_path(run_path: str | Path, domain: str) -> Path:
    root = Path(run_path).resolve()
    return root / domain if (root / "run.json").is_file() else root


def _delivery_output_path(run_path: str | Path, requested: str | None) -> str:
    root = Path(run_path).resolve()
    default = root / "final/deck.pptx"
    if not (root / "run.json").is_file():
        return str(Path(requested).resolve() if requested else default)
    final_root = root / "final"
    if final_root.is_symlink():
        raise ContractError("output_path_untrusted")
    target = Path(requested).resolve() if requested else default
    try:
        target.relative_to(final_root.resolve())
    except ValueError as exc:
        raise ContractError("output_outside_run") from exc
    return str(target)


def _freeze_slides_contract(run_path: str | Path, source_path: str | Path) -> Path:
    root = Path(run_path).resolve()
    source = Path(source_path)
    if not (root / "run.json").is_file():
        return source
    try:
        source_identity = inspect_regular_file(source, max_bytes=MAX_SLIDES_CONTRACT_BYTES)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    target = root / "input/slides.json"
    try:
        if target.is_file() or target.is_symlink():
            frozen_identity = inspect_regular_file(
                target, max_bytes=MAX_SLIDES_CONTRACT_BYTES
            )
            if frozen_identity["sha256"] != source_identity["sha256"]:
                raise ContractError("slides_fingerprint_conflict")
        else:
            durable_copy_file(
                source_identity["path"], target, max_bytes=MAX_SLIDES_CONTRACT_BYTES
            )
    except ValueError as exc:
        raise ContractError(str(exc)) from exc

    index = RunIndex(root)
    snapshot = index.snapshot()
    supplemental_inputs = snapshot.get("supplemental_inputs", {})
    if not isinstance(supplemental_inputs, dict):
        raise ContractError("run_index_invalid")
    existing = supplemental_inputs.get("slides")
    if existing is not None and not isinstance(existing, dict):
        raise ContractError("run_index_invalid")
    metadata = {
        "original_path": (
            existing.get("original_path")
            if isinstance(existing, dict) and existing.get("original_path")
            else str(source_identity["path"])
        ),
        "path": "input/slides.json",
        "size": source_identity["size"],
        "sha256": source_identity["sha256"],
    }
    if existing is not None and existing.get("sha256") != metadata["sha256"]:
        raise ContractError("slides_fingerprint_conflict")
    if existing != metadata:
        supplemental_inputs = dict(supplemental_inputs)
        supplemental_inputs["slides"] = metadata
        index.update(
            expected_revision=snapshot["revision"],
            changes={"supplemental_inputs": supplemental_inputs},
        )
    return target


def _require_prepare_input(run_path: str | Path) -> None:
    index_path = Path(run_path).resolve() / "run.json"
    if index_path.is_file() and _json_file(index_path).get("input_available") is False:
        raise ContractError("input_file_missing")


def _run_input_sources(run_path: str | Path, *, pages: set[int] | None = None) -> list[str]:
    root = Path(run_path).resolve()
    source_root = root / "editable" / "sources"
    if source_root.is_dir():
        values = sorted(
            path for path in source_root.iterdir() if path.is_file() and not path.is_symlink()
        )
    else:
        run = _json_file(root / "run.json")
        values = [root / run["input"]["path"]]
    if pages:
        selected = []
        for number in sorted(pages):
            if number < 1 or number > len(values):
                raise ContractError("selection_out_of_range")
            selected.append(values[number - 1])
        values = selected
    return [str(path) for path in values]


def _normalize_run_sources(
    run_path: str | Path, *, pages: set[int] | None = None
) -> tuple[list[str], bool, dict[int, str]]:
    root = Path(run_path).resolve()
    run = _json_file(root / "run.json")
    requested_pages = pages
    if str(run.get("route", "")).startswith("upgrade-"):
        try:
            baseline = load_baseline(root)
            baseline_pages = baseline["pages"]
            sources = [str(Path(page["artifact"]).resolve()) for page in baseline_pages]
            notes = {
                int(page["number"]): str(page.get("notes", ""))
                for page in baseline_pages
                if isinstance(page.get("number"), int)
            }
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ContractError("upgrade_baseline_manifest_invalid") from exc
        if not sources or any(not Path(source).is_file() for source in sources):
            raise ContractError("upgrade_baseline_artifact_missing")
        if requested_pages is not None:
            selected = []
            for number in sorted(requested_pages):
                if number < 1 or number > len(sources):
                    raise ContractError("selection_out_of_range")
                selected.append(sources[number - 1])
            sources = selected
        return sources, bool(run["input"].get("office_trusted")), notes
    upstream_run = root / "editable" / "upstream"
    source_pages = sorted(upstream_run.glob("pages/page_*/source.png"))
    if not source_pages:
        source = root / run["input"]["path"]
        arguments = [
            "prepare",
            str(source),
            "--job-dir",
            str(upstream_run),
            "--no-text-hints",
        ]
        if run["input"].get("office_trusted"):
            arguments.append("--office-trusted")
        backend_contract = root / run["backend_contract"]["path"]
        upstream = run_upstream(
            "editable-ppt",
            arguments,
            backend_contract=backend_contract if backend_contract.is_file() else None,
        )
        _persist_execution_receipt(run_path, upstream)
        if upstream["returncode"] != 0:
            raise ContractError("editable_input_normalization_failed")
        try:
            secure_user_tree(upstream_run)
        except ValueError as exc:
            raise ContractError(str(exc)) from exc
        # 上游 prepare 为输入归一化工具，不能把 vendor 的 page_jobs 状态
        # 带入用户 run。归一化完成后只保留不可变的页面源和 notes manifest。
        for vendor_state in (
            upstream_run / "page_jobs.json",
            upstream_run / "deck_run_state.json",
        ):
            try:
                vendor_state.unlink(missing_ok=True)
            except OSError as exc:
                raise ContractError("vendor_state_cleanup_failed") from exc
        source_pages = sorted(upstream_run.glob("pages/page_*/source.png"))
    if not source_pages:
        raise ContractError("normalized_page_sources_missing")
    notes_by_page: dict[int, str] = {}
    notes_manifest = upstream_run / "notes_manifest.json"
    if notes_manifest.is_file():
        try:
            notes_value = _json_file(notes_manifest)
            for entry in notes_value.get("notes", []):
                if isinstance(entry, dict) and isinstance(entry.get("page_index"), int):
                    notes_by_page[entry["page_index"]] = str(entry.get("text", ""))
        except (OSError, ValueError, TypeError):
            raise ContractError("notes_manifest_invalid")
    selected = source_pages
    if pages:
        selected = []
        for number in sorted(pages):
            if number < 1 or number > len(source_pages):
                raise ContractError("selection_out_of_range")
            selected.append(source_pages[number - 1])
    return [str(path) for path in selected], bool(run["input"].get("office_trusted")), notes_by_page


def _upgrade_hybrid_plan(run_path: str | Path) -> dict[str, Any]:
    """读取当前 upgrade-selected 状态，生成不可变 partial 提案指纹。"""
    root = Path(run_path).resolve()
    run = _json_file(root / "run.json")
    if run.get("route") != "upgrade-selected":
        raise ContractError("upgrade_route_required")
    baseline = load_baseline(root)
    image_artifacts = [
        PageArtifact.from_source(
            page["page_id"],
            "image",
            page["artifact"],
            page["artifact"],
            None,
            notes=str(page.get("notes", "")),
            width=int(page["width"]),
            height=int(page["height"]),
        )
        for page in baseline["pages"]
    ]
    editable_by_id = {
        artifact.page_id: artifact
        for artifact in EditableAdapter(_domain_path(root, "editable")).artifacts(
            allow_incomplete=True
        )
    }
    selected = set(run.get("selected_pages", []))
    if not selected:
        raise ContractError("selection_required")
    failures = {
        number: "page_rebuild_failed"
        for number in selected
        if f"page_{number:03d}" not in editable_by_id
    }
    artifacts = [editable_by_id.get(item.page_id, item) for item in image_artifacts]
    baseline_fingerprint = HybridAssembler.baseline_fingerprint(artifacts)
    confirmation = HybridAssembler.failure_fingerprint(
        failures,
        selected_pages=selected,
        baseline_fingerprint=baseline_fingerprint,
    ) if failures else None
    return {
        "selected_pages": sorted(selected),
        "failures": {str(key): value for key, value in failures.items()},
        "artifacts": artifacts,
        "baseline_fingerprint": baseline_fingerprint,
        "confirmation_fingerprint": confirmation,
    }


def _operation_payload(
    *, operation_id: str, idempotency_status: str, safe_to_retry: bool, state_hash: str
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "idempotency_status": idempotency_status,
        "safe_to_retry": safe_to_retry,
        "state_hash": state_hash,
    }


def _record_event(run_path: str | Path, kind: str, **data: Any) -> None:
    root = Path(run_path).resolve()
    if (root / "run.json").is_file():
        RunIndex(root).event(kind, {"actor": "leo-ppt", **data})


def _mark_delivery_completed(run_path: str | Path, *, stage: str) -> None:
    """把 delivery 成功写回唯一 run lifecycle，禁止完成后再 cancel。"""
    root = Path(run_path).resolve()
    if not (root / "run.json").is_file():
        return
    owner = RunIndex(root)
    current = owner.snapshot()
    if current.get("status") == "cancelled":
        raise ContractError("run_cancelled_mutation_forbidden")
    if current.get("status") == "completed" and current.get("stage") == stage:
        return
    owner.update(
        expected_revision=current["revision"],
        changes={"status": "completed", "stage": stage},
    )


def _lease_for_operation(
    run_path: str | Path,
    *,
    unit_id: str,
    actor: str,
    operation_id: str,
    requested_lease: str | None,
    requested_generation: int | None,
) -> tuple[str | None, int | None]:
    """为顶层 run 发行或校验 lease；独立 adapter fixture 不强制此边界。"""
    root = Path(run_path).resolve()
    if not (root / "run.json").is_file():
        return requested_lease, requested_generation
    owner = RunIndex(root)
    operation = owner.snapshot().get("operations", {}).get(operation_id)
    if operation and operation.get("lease"):
        lease = operation["lease"]
        generation = int(operation.get("generation", 0))
    else:
        issued = owner.issue_lease(unit_id, actor=actor, operation_id=operation_id)
        lease = issued["lease"]
        generation = int(issued["generation"])
    if requested_lease is not None and requested_lease != lease:
        raise IdempotencyConflict("lease_invalid")
    if requested_generation is not None and requested_generation != generation:
        raise IdempotencyConflict("generation_conflict")
    if not operation or operation.get("status") != "completed":
        owner.validate_lease(operation_id=operation_id, lease=lease, generation=generation)
    return lease, generation


def _complete_worker_operation(
    run_path: str | Path, operation_id: str, *, artifact_ref: str
) -> None:
    root = Path(run_path).resolve()
    if not (root / "run.json").is_file():
        return
    RunIndex(root).complete_operation(
        operation_id,
        result={"artifact_ref": artifact_ref},
    )


def _persist_execution_receipt(run_path: str | Path, result: dict[str, Any]) -> None:
    """把 backend execution 的非秘密 receipt 绑定到 run identity。"""
    receipt = result.get("execution_receipt")
    root = Path(run_path).resolve()
    if not isinstance(receipt, dict) or not (root / "run.json").is_file():
        return
    receipt_hash = sha256_bytes(canonical_json(receipt).encode("utf-8"))
    owner = RunIndex(root)
    current = owner.snapshot()
    existing = current.get("backend_execution")
    if isinstance(existing, dict) and existing.get("receipt_hash") == receipt_hash:
        return
    owner.update(
        expected_revision=current["revision"],
        changes={
            "backend_execution": {
                "receipt_hash": receipt_hash,
                "receipt": receipt,
            }
        },
    )


def _run_result(
    status: str,
    reason_code: str,
    run: dict[str, Any],
    **payload: Any,
) -> dict[str, Any]:
    artifact_refs = [
        value
        for value in run.get("artifacts", [])
        if isinstance(value, str)
    ]
    delivery_readiness = _delivery_readiness(run)
    if delivery_readiness is not None:
        payload.setdefault("delivery_readiness", delivery_readiness)
        payload.setdefault("evidence_refs", delivery_readiness["evidence_refs"])
    return envelope(
        status,
        reason_code,
        run_id=run["run_id"],
        route=run["route"],
        stage=run["stage"],
        run=run,
        state_hash=_state_hash(run),
        progress=_progress_from_run(run),
        artifact_refs=artifact_refs,
        **payload,
    )


def _delivery_readiness(run: dict[str, Any]) -> dict[str, Any] | None:
    output_dir = run.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir:
        return None
    root = Path(output_dir).resolve()
    summary_path = root / "final/validation-summary.json"
    if not summary_path.is_file():
        if run.get("status") != "completed":
            return None
        return {
            "status": "artifact_invalid",
            "reason_code": "delivery_summary_required",
            "artifact_ready": False,
            "missing_gates": [],
            "unverified_gates": [],
            "evidence_refs": [],
        }
    try:
        summary = _json_file(summary_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "status": "artifact_invalid",
            "reason_code": "delivery_summary_invalid",
            "artifact_ready": False,
            "missing_gates": [],
            "unverified_gates": [],
            "evidence_refs": [],
        }
    if not isinstance(summary, dict) or not isinstance(summary.get("quality_gates"), dict):
        return {
            "status": "artifact_invalid",
            "reason_code": "delivery_summary_invalid",
            "artifact_ready": False,
            "missing_gates": [],
            "unverified_gates": [],
            "evidence_refs": [],
        }
    gates = summary["quality_gates"]
    required_acceptance = ("visual_render", "manual_visual_acceptance")
    missing = [
        name
        for name in required_acceptance
        if not isinstance(gates.get(name), dict) or gates[name].get("status") != "passed"
    ]
    unverified = [
        name
        for name, value in gates.items()
        if name not in required_acceptance
        and isinstance(value, dict)
        and value.get("status") not in {"passed", "not_applicable"}
    ]
    evidence_refs = [str(summary_path)]
    for value in gates.values():
        if isinstance(value, dict) and isinstance(value.get("receipt"), str):
            evidence_refs.append(value["receipt"])
    evidence_refs.extend(str(path) for path in sorted((root / "reports").glob("provenance-*.json")))
    artifact_ready = summary.get("passed") is True
    status = (
        "artifact_invalid"
        if not artifact_ready
        else ("acceptance_pending" if missing else "accepted")
    )
    return {
        "status": status,
        "reason_code": {
            "artifact_invalid": "delivery_structure_not_ready",
            "acceptance_pending": "delivery_acceptance_pending",
            "accepted": "delivery_accepted",
        }[status],
        "artifact_ready": artifact_ready,
        "missing_gates": missing,
        "unverified_gates": unverified,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
    }


def _progress_from_run(run: dict[str, Any]) -> dict[str, Any]:
    totals = {"total_units": 0, "completed": 0, "failed": 0, "active": 0, "pending": 0}
    for domain in run.get("domains", {}).values():
        if not isinstance(domain, dict):
            continue
        progress = domain.get("progress")
        if not isinstance(progress, dict):
            continue
        for key in totals:
            value = progress.get(key)
            if isinstance(value, int):
                totals[key] += value
    return {**totals, "estimated_remaining_seconds": None}


def _worker_dispatch_action(page_count: int) -> dict[str, Any]:
    maximum = load_runtime_config().values["max_concurrent_workers"]
    return {
        "kind": "request_worker_dispatch",
        "payload": {
            "dispatch_requirement": "multi_agent_required"
            if page_count > 1
            else "single_unit_current_agent_allowed",
            "page_count": page_count,
            "estimated_duration_per_page_seconds": 180,
            "suggested_max_concurrent": min(maximum, max(page_count, 1)),
            "runtime_fallback": False,
        },
    }


def _status_next_action(run: dict[str, Any]) -> dict[str, Any]:
    progress = _progress_from_run(run)
    if run.get("status") == "completed":
        readiness = _delivery_readiness(run)
        if readiness and readiness["status"] == "acceptance_pending":
            return {
                "kind": "record_delivery_evidence",
                "payload": {"missing_gates": readiness["missing_gates"]},
            }
        if readiness and readiness["status"] == "artifact_invalid":
            return {
                "kind": "repair_delivery_artifact",
                "payload": {"reason_code": readiness["reason_code"]},
            }
        return {"kind": "none", "payload": {}}
    if run.get("status") == "cancelled":
        return {"kind": "none", "payload": {}}
    if run.get("status") == "failed" or progress["failed"]:
        return {"kind": "diagnose", "payload": {"failed_units": progress["failed"]}}
    if progress["active"]:
        return {
            "kind": "wait_completion",
            "payload": {"active_units": progress["active"]},
        }
    if progress["pending"]:
        return _worker_dispatch_action(progress["pending"])
    if progress["total_units"] and progress["completed"] == progress["total_units"]:
        kind = "upgrade_finalize" if run["route"].startswith("upgrade-") else "finalize"
        return {"kind": kind, "payload": {}}
    return {"kind": "execute_step", "payload": {"step": route_definition(run["route"]).steps[0]}}


def _protocol_status(run: dict[str, Any]) -> str:
    if run.get("status") in {"completed", "cancelled", "failed"}:
        return str(run["status"])
    progress = _progress_from_run(run)
    if progress["active"] or progress["pending"]:
        return "waiting_for_worker"
    return "ready"


def _next_action(run: dict[str, Any], *, worker_available: bool, page_count: int) -> dict[str, Any]:
    route = route_definition(run["route"])
    stage = run["stage"]
    if stage == "created":
        next_step = route.steps[0]
    else:
        route.require_step(stage)
        position = route.steps.index(stage)
        if position == len(route.steps) - 1:
            return {"kind": "none", "reason_code": "route_complete"}
        next_step = route.steps[position + 1]
    if "dispatch" in next_step and page_count > 1 and not worker_available:
        return {"kind": "blocked", "step": next_step, "reason_code": "worker_capability_unavailable"}
    if "dispatch" in next_step and page_count == 1 and not worker_available:
        return {"kind": "single_unit_current_agent_allowed", "step": next_step, "reason_code": "single_unit_current_agent_allowed"}
    return {"kind": "execute_step", "step": next_step, "reason_code": "step_ready"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leo-ppt")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--route")
    doctor.add_argument("--json", action="store_true")

    version = subcommands.add_parser("version", help="查看版本与协议版本")
    version.add_argument("--json", action="store_true")
    update = subcommands.add_parser("update", help="检查或更新受管 runtime")
    update.add_argument("--check", action="store_true")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--version")
    update.add_argument("--yes", action="store_true")
    update.add_argument("--json", action="store_true")
    rollback = subcommands.add_parser("rollback", help="回滚到健康 runtime")
    rollback.add_argument("--identity")
    rollback.add_argument("--json", action="store_true")

    setup = subcommands.add_parser("setup")
    setup.add_argument("--route", required=True)
    setup.add_argument(
        "--host-imagegen",
        choices=("available", "unavailable", "unknown"),
        default="unknown",
    )
    setup.add_argument(
        "--provider",
        choices=("builtin-imagegen", "openai", "openai-compatible", "atlascloud"),
    )
    setup.add_argument("--require-mask", action="store_true")
    setup.add_argument(
        "--ocr-requirement",
        choices=("not_required", "editable_text_hints"),
        default="not_required",
    )
    setup.add_argument("--json", action="store_true")

    route = subcommands.add_parser("route")
    route.add_argument("--input-kind", required=True)
    route.add_argument("--editable", action="store_true")
    route.add_argument("--upgrade", action="store_true")
    route.add_argument("--pages")

    config = subcommands.add_parser("config")
    config.add_argument("--key-stdin", action="store_true")
    config_commands = config.add_subparsers(dest="config_command")
    config_status = config_commands.add_parser("status")
    config_status.add_argument("--route")
    config_status.add_argument(
        "--host-imagegen",
        choices=("available", "unavailable", "unknown"),
        default="unknown",
    )
    config_status.add_argument("--json", action="store_true")
    config_verify = config_commands.add_parser("verify")
    config_verify.add_argument("--route")
    config_verify.add_argument("--yes", action="store_true")
    config_verify.add_argument("--json", action="store_true")
    config_repair = config_commands.add_parser("repair")
    config_repair.add_argument("--route")
    config_repair.add_argument("--key-stdin", action="store_true")
    config_repair.add_argument("--json", action="store_true")
    config_change = config_commands.add_parser("change")
    config_change.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
    )
    config_change.add_argument("--key-stdin", action="store_true")
    config_change.add_argument("--json", action="store_true")

    config_provider = config_commands.add_parser("provider")
    provider_commands = config_provider.add_subparsers(
        dest="config_provider_command", required=True
    )
    provider_list = provider_commands.add_parser("list")
    provider_list.add_argument("--route")
    provider_list.add_argument("--json", action="store_true")
    provider_configure = provider_commands.add_parser("configure")
    provider_configure.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
        required=True,
    )
    provider_configure.add_argument("--route")
    provider_configure.add_argument("--key-stdin", action="store_true")
    provider_configure.add_argument("--json", action="store_true")
    provider_select = provider_commands.add_parser("select")
    provider_select.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
        required=True,
    )
    provider_select.add_argument("--route")
    provider_select.add_argument("--key-stdin", action="store_true")
    provider_select.add_argument("--json", action="store_true")
    provider_priority = provider_commands.add_parser("priority")
    provider_priority.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
        required=True,
    )
    provider_priority.add_argument("--value", type=int, required=True)
    provider_priority.add_argument("--json", action="store_true")
    provider_enabled = provider_commands.add_parser("enabled")
    provider_enabled.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
        required=True,
    )
    provider_enabled.add_argument("--value", choices=("true", "false"), required=True)
    provider_enabled.add_argument("--json", action="store_true")
    provider_remove = provider_commands.add_parser("remove")
    provider_remove.add_argument(
        "--provider",
        choices=("openai", "openai-compatible", "atlascloud"),
        required=True,
    )
    provider_remove.add_argument("--confirm", action="store_true")
    provider_remove.add_argument("--json", action="store_true")

    config_credential = config_commands.add_parser("credential")
    credential_commands = config_credential.add_subparsers(
        dest="config_credential_command", required=True
    )
    credential_status = credential_commands.add_parser("status")
    credential_status.add_argument("--provider")
    credential_status.add_argument("--json", action="store_true")
    credential_set = credential_commands.add_parser("set")
    credential_set.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    credential_set.add_argument("--overwrite", action="store_true")
    credential_set.add_argument("--key-stdin", action="store_true")
    credential_set.add_argument("--json", action="store_true")
    credential_remove = credential_commands.add_parser("remove")
    credential_remove.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    credential_remove.add_argument("--confirm", action="store_true")
    credential_remove.add_argument("--json", action="store_true")

    config_reset = config_commands.add_parser("reset")
    config_reset.add_argument("--confirm", action="store_true")
    config_reset.add_argument("--json", action="store_true")

    auth = subcommands.add_parser("auth")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    auth_add = auth_commands.add_parser("add")
    auth_add.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    auth_add.add_argument("--overwrite", action="store_true")
    auth_add.add_argument("--json", action="store_true")
    auth_status = auth_commands.add_parser("status")
    auth_status.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    auth_status.add_argument("--json", action="store_true")
    auth_remove = auth_commands.add_parser("remove")
    auth_remove.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    auth_remove.add_argument("--json", action="store_true")

    backend = subcommands.add_parser("backend")
    backend_commands = backend.add_subparsers(dest="backend_command", required=True)
    backend_create = backend_commands.add_parser("create")
    backend_create.add_argument(
        "--provider",
        choices=("builtin-imagegen", "openai", "openai-compatible", "atlascloud"),
    )
    backend_create.add_argument(
        "--host-imagegen",
        choices=("available", "unavailable", "unknown"),
        default="unknown",
    )
    backend_create.add_argument("--mode", choices=("generate", "edit"), required=True)
    backend_create.add_argument("--model")
    backend_create.add_argument("--output", required=True)
    backend_create.add_argument("--overwrite", action="store_true")
    backend_validate = backend_commands.add_parser("validate")
    backend_validate.add_argument("contract")

    provider = subcommands.add_parser("provider")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    provider_configure = provider_commands.add_parser("configure")
    provider_configure.add_argument("--provider", choices=("openai-compatible",), required=True)
    provider_configure.add_argument("--base-url", required=True)
    provider_configure.add_argument("--model", required=True)

    run = subcommands.add_parser("run")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    create = run_commands.add_parser("create")
    create.add_argument("--run-dir")
    create.add_argument("--output")
    create.add_argument("--project-root")
    create.add_argument("--route", required=True)
    create.add_argument("--input")
    create.add_argument("--backend-contract")
    create.add_argument("--idempotency-key")
    create.add_argument("--office-trusted", action="store_true")
    create.add_argument("--runtime-identity")
    status = run_commands.add_parser("status")
    status.add_argument("run_path", nargs="?")
    status.add_argument("--run-dir")
    status.add_argument("--json", action="store_true")
    next_step = run_commands.add_parser("next")
    next_step.add_argument("run_path", nargs="?")
    next_step.add_argument("--run-dir")
    next_step.add_argument("--page-count", type=int, required=True)
    next_step.add_argument("--worker-available", action="store_true")
    advance = run_commands.add_parser("advance")
    advance.add_argument("run_path", nargs="?")
    advance.add_argument("--run-dir")
    advance.add_argument("--expected-revision", type=int, required=True)
    advance.add_argument("--stage", required=True)
    diagnose = run_commands.add_parser("diagnose")
    diagnose.add_argument("run_path", nargs="?")
    diagnose.add_argument("--run-dir")
    diagnose.add_argument("--json", action="store_true")
    operation = run_commands.add_parser("operation")
    operation.add_argument("run_path", nargs="?")
    operation.add_argument("--run-dir")
    operation.add_argument("--id", required=True)
    operation.add_argument("--json", action="store_true")
    retry = run_commands.add_parser("retry")
    retry.add_argument("run_path", nargs="?")
    retry.add_argument("--run-dir")
    retry.add_argument("--from-failed-pages", action="store_true")
    cancel = run_commands.add_parser("cancel")
    cancel.add_argument("run_path", nargs="?")
    cancel.add_argument("--run-dir")
    cancel.add_argument("--expected-revision", type=int)
    cancel.add_argument("--wait-workers", action="store_true")
    run_cleanup = run_commands.add_parser("cleanup")
    run_cleanup.add_argument("run_path", nargs="?")
    run_cleanup.add_argument("--run-dir")
    run_cleanup.add_argument("--scope", choices=("temp", "failed-attempts", "input"), required=True)
    run_cleanup_mode = run_cleanup.add_mutually_exclusive_group(required=True)
    run_cleanup_mode.add_argument("--dry-run", action="store_true")
    run_cleanup_mode.add_argument("--apply", nargs="?", const="")
    run_cleanup.add_argument("--expected-revision", type=int)

    image = subcommands.add_parser("image")
    image_commands = image.add_subparsers(dest="image_command", required=True)
    prepare = image_commands.add_parser("prepare")
    prepare.add_argument("run_path", nargs="?")
    prepare.add_argument("--run-dir")
    prepare.add_argument("--slides")
    record = image_commands.add_parser("record")
    record.add_argument("run_path", nargs="?")
    record.add_argument("--run-dir")
    record.add_argument("--number", type=int)
    record.add_argument("--slide")
    record.add_argument("--image")
    record.add_argument("--result")
    record.add_argument("--backend", default="fixture")
    record.add_argument("--lease")
    record.add_argument("--generation", type=int)
    record.add_argument("--agent-id")
    record.add_argument("--expected-revision", type=int)
    record.add_argument("--expected-state-hash")
    record.add_argument("--operation-id")
    record.add_argument("--worker-duration-seconds", type=_duration_seconds)
    record.add_argument("--backend-duration-seconds", type=_duration_seconds)
    finalize = image_commands.add_parser("finalize")
    finalize.add_argument("run_path", nargs="?")
    finalize.add_argument("--run-dir")
    finalize.add_argument("--output")
    finalize.add_argument("--rebuild", action="store_true")
    image_assemble = image_commands.add_parser("assemble")
    image_assemble.add_argument("run_path", nargs="?")
    image_assemble.add_argument("--run-dir")
    image_assemble.add_argument("--output")
    image_assemble.add_argument("--rebuild", action="store_true")

    editable = subcommands.add_parser("editable")
    editable_commands = editable.add_subparsers(dest="editable_command", required=True)
    editable_prepare = editable_commands.add_parser("prepare")
    editable_prepare.add_argument("run_path", nargs="?")
    editable_prepare.add_argument("--run-dir")
    editable_prepare.add_argument("--sources", nargs="+")
    editable_prepare.add_argument("--pages")
    editable_prepare.add_argument("--worker-available", action="store_true")
    editable_prepare.add_argument("--office-trusted", action="store_true")
    editable_next = editable_commands.add_parser("next")
    editable_next.add_argument("run_path", nargs="?")
    editable_next.add_argument("--run-dir")
    editable_next.add_argument("--json", action="store_true")
    editable_dispatch = editable_commands.add_parser("dispatch")
    editable_dispatch.add_argument("run_path", nargs="?")
    editable_dispatch.add_argument("--run-dir")
    editable_dispatch.add_argument("--page", required=True)
    editable_dispatch.add_argument("--agent-id", required=True)
    editable_dispatch.add_argument("--prompt-file", required=True)
    editable_dispatch.add_argument("--lease")
    editable_dispatch.add_argument("--generation", type=int)
    editable_record = editable_commands.add_parser("record")
    editable_record.add_argument("run_path", nargs="?")
    editable_record.add_argument("--run-dir")
    editable_record.add_argument("--page", required=True)
    editable_record.add_argument("--agent-id")
    editable_record.add_argument("--pptx")
    editable_record.add_argument("--validation")
    editable_record.add_argument("--manifest")
    editable_record.add_argument("--expected-revision", type=int)
    editable_record.add_argument("--expected-state-hash")
    editable_record.add_argument("--operation-id")
    editable_record.add_argument("--notes", default="")
    editable_record.add_argument("--backend")
    editable_record.add_argument("--worker-duration-seconds", type=_duration_seconds)
    editable_record.add_argument("--backend-duration-seconds", type=_duration_seconds)
    editable_record.add_argument("--lease")
    editable_record.add_argument("--generation", type=int)
    editable_reset = editable_commands.add_parser("reset")
    editable_reset.add_argument("run_path", nargs="?")
    editable_reset.add_argument("--run-dir")
    editable_reset.add_argument("--page", required=True)
    editable_reset.add_argument("--confirm-lost", action="store_true")
    editable_finalize = editable_commands.add_parser("finalize")
    editable_finalize.add_argument("run_path", nargs="?")
    editable_finalize.add_argument("--run-dir")
    editable_finalize.add_argument("--output")

    upgrade = subcommands.add_parser("upgrade")
    upgrade_commands = upgrade.add_subparsers(dest="upgrade_command", required=True)
    upgrade_inspect = upgrade_commands.add_parser("inspect")
    upgrade_inspect.add_argument("--source-run", required=True)
    upgrade_import = upgrade_commands.add_parser("import-baseline")
    upgrade_import.add_argument("run_path", nargs="?")
    upgrade_import.add_argument("--run-dir")
    upgrade_import.add_argument("--source-run", required=True)
    upgrade_propose = upgrade_commands.add_parser("propose")
    upgrade_propose.add_argument("run_path", nargs="?")
    upgrade_propose.add_argument("--run-dir")
    upgrade_finalize = upgrade_commands.add_parser("finalize")
    upgrade_finalize.add_argument("run_path", nargs="?")
    upgrade_finalize.add_argument("--run-dir")
    upgrade_finalize.add_argument("--output")
    upgrade_finalize.add_argument(
        "--partial-confirmation",
        help="确认当前冻结的失败集合后才允许生成 partial-hybrid",
    )
    # 保留旧参数仅用于给出明确迁移错误，不能绕过两阶段确认。
    upgrade_finalize.add_argument("--allow-partial", action="store_true")

    delivery = subcommands.add_parser("delivery")
    delivery_commands = delivery.add_subparsers(dest="delivery_command", required=True)
    assemble = delivery_commands.add_parser("assemble")
    assemble.add_argument("--artifacts", required=True)
    assemble.add_argument("--output", required=True)
    assemble.add_argument("--selected-pages")
    assemble.add_argument("--failures")
    assemble.add_argument("--partial-confirmation")

    style = subcommands.add_parser("style")
    style_commands = style.add_subparsers(dest="style_command", required=True)
    style_list = style_commands.add_parser("list")
    style_list.add_argument("--home")
    style_load = style_commands.add_parser("load")
    style_load.add_argument("name")
    style_load.add_argument("--home")
    style_render = style_commands.add_parser("render")
    style_render.add_argument("style")
    style_render.add_argument("--home")
    style_render.add_argument("--mode", help="论证模式名（06_论证模式）")
    style_render.add_argument("--layout", help="版式名（12_版式库，如 P6 / KPI Tower）")
    style_render.add_argument("--image-type", help="信息图类型名（07_信息图类型）")
    style_render.add_argument("--list-templates", action="store_true")
    style_save = style_commands.add_parser("save")
    style_save.add_argument("name")
    style_save.add_argument("--content-file", required=True)
    style_save.add_argument("--home")
    style_save.add_argument("--overwrite", action="store_true")
    style_save.add_argument("--rename")

    evidence = subcommands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    for name in ("provenance", "visual", "accept"):
        evidence_record = evidence_commands.add_parser(name)
        evidence_record.add_argument("run_path", nargs="?")
        evidence_record.add_argument("--run-dir")
        evidence_record.add_argument("--receipt", required=True)

    cleanup = subcommands.add_parser("cleanup")
    cleanup.add_argument("--run-dir", required=True)
    mode = cleanup.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply")
    cleanup.add_argument("--expected-revision", type=int)

    upstream = subcommands.add_parser("upstream")
    upstream.add_argument("--backend-contract")
    upstream.add_argument("--timeout", type=_duration_seconds)
    upstream.add_argument("capability", choices=("codex-ppt", "editable-ppt"))
    upstream.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help=(
            "固定上游参数。codex-ppt 的第一个参数是工具名："
            + ", ".join(sorted(CODEX_TOOLS))
            + "；editable-ppt 参数与原 editppt 命令树一致。"
        ),
    )
    return parser


def _is_executable_console_script(path: Path, *, platform_name: str) -> bool:
    return path.is_file() and (
        platform_name == "nt" or os.access(path, os.X_OK)
    )


def _resolve_cli_path(*, platform_name: str | None = None) -> str | None:
    """解析当前平台可直接执行的 console script，绝不返回猜测路径。"""

    platform_name = platform_name or os.name
    script_name = "leo-ppt.exe" if platform_name == "nt" else "leo-ppt"
    candidates = (
        os.environ.get("LEO_PPT_CLI_PROG"),
        shutil.which(script_name),
        str(Path(sys.executable).with_name(script_name)),
    )
    for value in candidates:
        if not value:
            continue
        try:
            candidate = Path(value).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if _is_executable_console_script(candidate, platform_name=platform_name):
            return str(candidate)
    return None


def _module_action_materializer(shell):
    """在无 console script 的模块运行场景中保留可执行恢复命令。"""

    from .config.reason_codes import CommandRenderer

    renderer = CommandRenderer(shell)
    executable = str(Path(sys.executable).resolve())

    def materialize(intent):
        return renderer.render_prefixed(
            intent,
            executable=executable,
            prefix_arguments=("-m", "leo_ppt_generator"),
        )

    return materialize


def _config_service(manager=None) -> ConfigService:
    """从当前 runtime 事实构建统一配置服务。"""

    registry = ProviderRegistry.default()
    home = default_home()
    from .config.runtime_config import ConfigStore
    from .config.reason_codes import ShellKind

    store = ConfigStore(home)
    manager = manager or credential_manager()
    cli_path = _resolve_cli_path()
    shell = ShellKind.POWERSHELL if os.name == "nt" else ShellKind.POSIX

    def credential_reader(provider):
        facts = dict(manager.status(provider.value))
        if facts.get("reference_type") == "environment-reference":
            version = manager.environment_version(provider.value)
            if version is not None:
                facts["credential_version"] = version
        return facts

    return ConfigService(
        store,
        manager.store,
        registry,
        FileReceiptStore(home, registry),
        credential_reader=credential_reader,
        action_materializer=(
            _module_action_materializer(shell) if cli_path is None else None
        ),
        cli_path=cli_path,
        shell=shell,
    )


def _config_wizard(
    provider: str | None = None, *, key_stdin: bool = False
) -> ConfigWizard:
    """构造使用同一 CredentialManager/store 的交互式配置向导。"""

    manager = credential_manager()
    return ConfigWizard(
        _config_service(manager),
        CredentialInputResolver(manager.store, manager.environ),
        input_stream=sys.stdin,
        output_stream=sys.stdout,
        key_stdin=key_stdin,
        fixed_provider=provider,
    )


def _config_provider_list(request: StatusRequest) -> dict[str, Any]:
    service = _config_service()
    snapshot = service.config_store.read()
    report = service.status(request)
    by_name = {item.provider.value: item.to_dict() for item in report.providers}
    providers = []
    for definition in ProviderRegistry.default().definitions():
        if definition.name == "builtin-imagegen":
            continue
        current = by_name.get(definition.name, {})
        profile = snapshot.values.get("provider_profiles", {}).get(definition.name, {})
        providers.append(
            {
                "provider": definition.name,
                "selected": report.selected_provider is not None
                and report.selected_provider.value == definition.name,
                "configured": current.get("configuration_state")
                == "locally_configured",
                "enabled": profile.get("enabled", False),
                "priority": profile.get("priority"),
                "credential_status": (
                    "available"
                    if current.get("credential_reference_type")
                    in {"environment-reference", "os-store-reference"}
                    else "missing"
                ),
                "capabilities": sorted(
                    capability.value for capability in definition.supported_capabilities
                ),
                "default_model": definition.default_model,
            }
        )
    return envelope("ready", "provider_listed", providers=providers)


def _update_provider_preference(
    provider: str, *, field: str, value: Any
) -> dict[str, Any]:
    if field == "priority" and (
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000
    ):
        raise ConfigServiceError("provider_profile_invalid")
    service = _config_service()
    snapshot = service.config_store.read()
    profiles = dict(snapshot.document.get("provider_profiles", {}))
    profile = profiles.get(provider)
    if not isinstance(profile, dict):
        raise ConfigServiceError("provider_profile_invalid")
    updated = dict(profile)
    updated[field] = value
    profiles[provider] = updated
    candidate = dict(snapshot.document)
    candidate["provider_profiles"] = profiles
    service.config_store.compare_and_swap(snapshot.canonical_digest, candidate)
    return envelope("completed", "provider_preference_updated", provider=provider)


def _remove_provider_profile(provider: str) -> dict[str, Any]:
    service = _config_service()
    snapshot = service.config_store.read()
    profiles = dict(snapshot.document.get("provider_profiles", {}))
    existed = profiles.pop(provider, None) is not None
    if not existed:
        return envelope("completed", "provider_not_found", provider=provider)
    candidate = dict(snapshot.document)
    candidate["provider_profiles"] = profiles
    if candidate.get("selected_provider") == provider:
        candidate.pop("selected_provider", None)
    service.config_store.compare_and_swap(snapshot.canonical_digest, candidate)
    service.receipt_store.invalidate(
        ProviderName(provider), "provider_removed", f"provider-remove-{provider}"
    )
    return envelope(
        "completed",
        "provider_removed",
        provider=provider,
    )


def _dispatch_config_provider(args: argparse.Namespace) -> dict[str, Any]:
    command = args.config_provider_command
    request = StatusRequest(route=getattr(args, "route", None))
    if command == "list":
        return _config_provider_list(request)
    if command == "configure":
        report = _config_wizard(
            args.provider, key_stdin=args.key_stdin
        ).run(request).report
        return envelope(report.status.value, report.reason_code, report=report.to_dict())
    if command == "select":
        service = _config_service()
        snapshot = service.config_store.read()
        if args.provider not in snapshot.values.get("provider_profiles", {}):
            report = _config_wizard(
                args.provider, key_stdin=args.key_stdin
            ).run(request).report
        else:
            report = service.change(
                request,
                selected_provider=args.provider,
                operation_id=f"config-select-{args.provider}",
            )
        return envelope(report.status.value, report.reason_code, report=report.to_dict())
    if command == "priority":
        return _update_provider_preference(
            args.provider, field="priority", value=args.value
        )
    if command == "enabled":
        return _update_provider_preference(
            args.provider, field="enabled", value=args.value == "true"
        )
    if not args.confirm:
        raise ConfigServiceError("destructive_confirmation_required")
    return _remove_provider_profile(args.provider)


def _dispatch_config_credential(args: argparse.Namespace) -> dict[str, Any]:
    manager = credential_manager()
    command = args.config_credential_command
    if command == "status":
        providers = (args.provider,) if args.provider else tuple(PROVIDERS)
        return envelope(
            "ready",
            "credential_status_reported",
            credentials=[manager.status(provider) for provider in providers],
        )
    if command == "set":
        if args.key_stdin:
            if manager.store.status(args.provider) == "available" and not args.overwrite:
                raise CredentialError("credential_overwrite_confirmation_required")
            selection = CredentialInputResolver(manager.store, manager.environ).select(
                args.provider,
                key_stdin=True,
                input_stream=sys.stdin,
                tty_stream=None,
                force_new_secret=True,
            )
            try:
                if selection.secret is None:
                    raise CredentialError("credential_input_channel_unavailable")
                # store 的协议签名是 write(secret: str)；显式受让最短生命周期文本副本，
                # 由 selection.close() 负责清零，避免跨通道传递 SecretBuffer 对象。
                manager.store.write(
                    args.provider, selection.secret.reveal_text()
                )
                result = manager.status(args.provider)
            finally:
                selection.close()
        else:
            result = manager.add(args.provider, overwrite=args.overwrite)
        return envelope("completed", str(result["reason_code"]), credential=result)
    if not args.confirm:
        raise ConfigServiceError("destructive_confirmation_required")
    result = manager.remove(args.provider)
    return envelope("completed", str(result["reason_code"]), credential=result)


def _dispatch_config(args: argparse.Namespace) -> dict[str, Any]:
    request = StatusRequest(route=getattr(args, "route", None))
    command = args.config_command
    if command is None:
        report = _config_wizard(
            key_stdin=getattr(args, "key_stdin", False)
        ).run(request).report
        return envelope(
            report.status.value,
            report.reason_code,
            report=report.to_dict(),
        )

    if command == "provider":
        return _dispatch_config_provider(args)
    if command == "credential":
        return _dispatch_config_credential(args)
    if command == "reset":
        if not args.confirm:
            raise ConfigServiceError("destructive_confirmation_required")
        service = _config_service()
        snapshot = service.config_store.read()
        try:
            service.config_store.compare_and_swap(
                snapshot.canonical_digest,
                {"schema_version": 1, "provider_profiles": {}},
            )
        except RuntimeConfigError as error:
            # CAS 冲突：不破坏并发写入者的配置，也不伪装成已 reset。
            raise ConfigServiceError(str(error.reason_code)) from error
        for provider in (
            ProviderName.OPENAI,
            ProviderName.OPENAI_COMPATIBLE,
            ProviderName.ATLASCLOUD,
        ):
            service.receipt_store.invalidate(
                provider, "config_reset", "config-reset"
            )
        return envelope(
            "completed",
            "config_reset",
            credentials_preserved=True,
        )

    service = _config_service()
    if command == "status":
        host_capabilities = (
            ("generate",) if args.host_imagegen == "available" else ()
        )
        report = service.status(
            request,
            host_capability_state=args.host_imagegen,
            host_capabilities=host_capabilities,
        )
        selection = None
        selection_error = None
        if service.config_store.read().values.get("provider_profiles"):
            try:
                decision = service.resolve_provider(
                    request,
                    host_capability_state=HostCapabilityState(args.host_imagegen),
                )
                selection = {
                    "provider": decision.provider.value,
                    "source": decision.source,
                    "priority": decision.priority,
                    "config_digest": decision.config_digest,
                }
            except ConfigServiceError as error:
                selection_error = error.reason_code
                return envelope(
                    "action_required",
                    selection_error,
                    report=report.to_dict(),
                    selection=None,
                    selection_error=selection_error,
                    primary_action=primary_action_for(
                        selection_error,
                        route=str(request.route or "generate"),
                        provider="openai|openai-compatible|atlascloud",
                    ),
                )
        return envelope(
            report.status.value,
            report.reason_code,
            report=report.to_dict(),
            selection=selection,
            selection_error=selection_error,
        )
    if command == "verify":
        if not args.yes:
            return envelope(
                "action_required",
                ReasonCode.PAID_VERIFICATION_CONSENT_REQUIRED.value,
                report=service.status(request).to_dict(),
                primary_action={
                    "kind": "run_cli",
                    "command": "config",
                    "verification": "在真实交互终端运行 config 并明确同意付费验证",
                },
            )
        # Provider smoke executor 尚未接入 CLI；显式同意不能被伪装成已验证，
        # 只能返回一个诚实的不可用状态与可执行恢复命令。
        report = service.verify(request)
        return envelope(
            "action_required",
            ReasonCode.PROVIDER_SMOKE_EXECUTOR_UNAVAILABLE.value,
            report=report.to_dict(),
            primary_action={
                "kind": "run_cli",
                "command": "config",
                "verification": "Provider smoke executor 接入后，在真实终端同意重试 config verify",
            },
        )
    if command == "repair":
        report = service.repair(request)
        eligibility = getattr(getattr(report, "execution_eligibility", None), "value", None)
        if eligibility == "blocked":
            report = _config_wizard(
                key_stdin=getattr(args, "key_stdin", False)
            ).run(request).report
        return envelope(
            report.status.value,
            report.reason_code,
            report=report.to_dict(),
        )
    if command == "change":
        provider = getattr(args, "provider", None)
        if provider is None:
            report = _config_wizard(
                key_stdin=getattr(args, "key_stdin", False)
            ).run(request).report
        else:
            snapshot = service.config_store.read()
            if provider not in snapshot.values.get("provider_profiles", {}):
                report = _config_wizard(
                    provider, key_stdin=getattr(args, "key_stdin", False)
                ).run(request).report
            else:
                report = service.change(
                    request,
                    selected_provider=provider,
                    operation_id=f"config-change-{provider}",
                )
        return envelope(
            report.status.value,
            report.reason_code,
            report=report.to_dict(),
        )
    raise ValueError(f"unknown config command: {command}")


def _dispatch_impl(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "version":
        return _version_report()
    if args.command in {"update", "rollback"}:
        return _dispatch_runtime_lifecycle(args)
    if args.command == "config":
        return _dispatch_config(args)
    if args.command == "doctor":
        return doctor_report(args.route)
    if args.command == "setup":
        selected_provider = args.provider
        decision = None
        service = _config_service()
        selection_error = None
        if selected_provider is None and service.config_store.read().values.get("provider_profiles"):
            try:
                decision = service.resolve_provider(
                    StatusRequest(route=args.route),
                    host_capability_state=HostCapabilityState(args.host_imagegen),
                )
                selected_provider = decision.provider.value
            except ConfigServiceError as error:
                selection_error = error.reason_code
        report = build_setup_report(
            args.route,
            host_imagegen=args.host_imagegen,
            selected_provider=selected_provider,
            required_image_capabilities={"mask"} if args.require_mask else set(),
            ocr_requirement=args.ocr_requirement,
        )
        if decision is not None:
            report["selection"] = {
                "source": decision.source,
                "priority": decision.priority,
                "config_digest": decision.config_digest,
            }
        if selection_error is not None:
            report["status"] = "action_required"
            report["reason_code"] = selection_error
            report["selected_provider"] = None
            report["primary_action"] = primary_action_for(
                selection_error,
                route=args.route,
                provider="openai|openai-compatible|atlascloud",
            )
        return report
    if args.command == "route":
        selected = select_route(
            args.input_kind,
            editable=args.editable,
            upgrade=args.upgrade,
            selected_pages=_parse_pages(args.pages),
        )
        return envelope("ready", "route_selected", route=selected, next_action={"kind": "create_run"})
    if args.command == "auth":
        manager = credential_manager()
        if args.auth_command == "add":
            return manager.add(args.provider, overwrite=args.overwrite)
        if args.auth_command == "status":
            return manager.status(args.provider)
        return manager.remove(args.provider)
    if args.command == "provider":
        config = configure_openai_compatible_profile(
            endpoint_origin=args.base_url,
            model=args.model,
        )
        profile = config.values["provider_profiles"]["openai-compatible"]
        return envelope(
            "ready",
            "provider_profile_configured",
            provider=args.provider,
            endpoint_origin=profile["endpoint_origin"],
            model=profile["model"],
            next_action={"kind": "configure_credential_reference"},
        )
    if args.command == "backend":
        registry = BackendRegistry.default()
        if args.backend_command == "create":
            output = Path(args.output).resolve()
            if output.exists() and not args.overwrite:
                raise BackendContractError("backend_contract_exists")
            provider = args.provider
            selection_source = "user-confirmed"
            selection = None
            if provider is None:
                route = (
                    RouteName.GENERATE
                    if args.mode == "generate"
                    else RouteName.DIRECT_EDITABLE
                )
                decision = _config_service().resolve_provider(
                    StatusRequest(route=route),
                    host_capability_state=HostCapabilityState(args.host_imagegen),
                )
                provider = decision.provider.value
                selection_source = decision.source
                selection = {
                    "source": decision.source,
                    "priority": decision.priority,
                    "config_digest": decision.config_digest,
                }
            credential_source = None
            credential_ref = None
            endpoint_origin = None
            model = args.model
            profiles = load_runtime_config().values.get("provider_profiles", {})
            profile = profiles.get(provider) if selection is not None else None
            if isinstance(profile, dict):
                model = model or profile.get("model")
                credential_source = profile.get("credential_source")
                credential_ref = profile.get("credential_ref")
                endpoint_origin = profile.get("endpoint_origin")
            elif provider == "openai-compatible":
                profile = openai_compatible_profile()
                if profile is None:
                    raise BackendContractError("provider_profile_missing")
                endpoint_origin = profile["endpoint_origin"]
                model = model or profile["model"]
                credential_source = profile["credential_source"]
                credential_ref = profile["credential_ref"]
            elif provider in PROVIDERS:
                credential_source, credential_ref = credential_manager().reference(
                    provider
                )
            contract = registry.create_contract(
                provider,
                mode=args.mode,
                model=model,
                selection_source=selection_source,
                credential_source=credential_source,
                credential_ref=credential_ref,
                endpoint_origin=endpoint_origin,
                selection=selection,
            )
            try:
                atomic_write_json(output, contract)
            except OSError as exc:
                raise BackendContractError("backend_contract_unwritable") from exc
            return envelope(
                "ready",
                "backend_contract_created",
                contract_path=str(output),
                contract=contract,
                next_action={"kind": "create_run"},
            )
        try:
            contract = _json_file(args.contract)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BackendContractError("backend_contract_invalid") from exc
        if not isinstance(contract, dict):
            raise BackendContractError("backend_contract_invalid")
        backend = registry.load(contract)
        credential_source = contract["credential_source"]
        credential_ref = contract.get("credential_ref")
        if credential_source == "environment-reference":
            environment_name = str(credential_ref).removeprefix("env:")
            credential_status = "available" if os.environ.get(environment_name) else "missing"
        elif credential_source == "os-store-reference":
            credential_status = credential_manager().status(backend.name)["status"]
        else:
            credential_status = "host_check_required"
        return envelope(
            "ready",
            "backend_contract_valid",
            contract_path=str(Path(args.contract).resolve()),
            provider=backend.name,
            mode=contract["mode"],
            credential_reference_status=credential_status,
            next_action={
                "kind": "create_run" if credential_status != "missing" else "configure_credential_reference"
            },
        )
    if args.command == "run":
        if args.run_command == "create":
            output = args.output or args.run_dir
            if not output:
                raise ContractError("output_required")
            runtime_identity = _runtime_identity(args.runtime_identity)
            if args.input or args.backend_contract or args.output:
                if not args.input:
                    raise ContractError("input_required")
                if not args.backend_contract:
                    raise ContractError("backend_contract_required")
                creation = RunIndex.create_from_request(
                    output,
                    route=args.route,
                    input_path=args.input,
                    backend_contract_path=args.backend_contract,
                    runtime_identity=runtime_identity,
                    idempotency_key=args.idempotency_key,
                    office_trusted=args.office_trusted,
                    project_root=args.project_root,
                )
                index = creation.index
                run_snapshot = index.snapshot()
                operation_id = args.idempotency_key or f"create-{run_snapshot['run_id']}"
                return _run_result(
                    "ready",
                    "run_created" if creation.idempotency_status == "created" else "run_replayed",
                    run_snapshot,
                    operation_id=operation_id,
                    idempotency_status=creation.idempotency_status,
                    safe_to_retry=True,
                    next_action={"kind": "inspect_next"},
                )
            existed = (Path(output) / "run.json").is_file()
            index = RunIndex.create(output, route=args.route, runtime_identity=runtime_identity)
            run_snapshot = index.snapshot()
            return _run_result(
                "ready",
                "run_created" if not existed else "run_replayed",
                run_snapshot,
                operation_id=f"create-{run_snapshot['run_id']}",
                idempotency_status="replayed" if existed else "created",
                safe_to_retry=True,
                next_action={"kind": "inspect_next"},
            )
        run_path = _run_path(args)
        index = RunIndex(run_path)
        if args.run_command == "status":
            run_snapshot = index.reconcile_from_disk()
            return _run_result(
                _protocol_status(run_snapshot),
                "run_status",
                run_snapshot,
                next_action=_status_next_action(run_snapshot),
            )
        if args.run_command == "next":
            action = _next_action(index.snapshot(), worker_available=args.worker_available, page_count=args.page_count)
            status = "blocked" if action["kind"] == "blocked" else "ready"
            return _run_result(status, action["reason_code"], index.snapshot(), next_action=action)
        if args.run_command == "advance":
            before = index.snapshot()
            route_definition(before["route"]).require_step(args.stage)
            run = index.update(expected_revision=args.expected_revision, changes={"stage": args.stage, "status": "in_progress"})
            index.event(
                "run.stage_advanced",
                {"actor": "leo-ppt", "status": "in_progress", "subject": args.stage},
            )
            return _run_result(
                "ready",
                "stage_advanced",
                run,
                operation_id=f"advance-{before['revision']}-{args.stage}",
                idempotency_status="created",
                safe_to_retry=False,
            )
        if args.run_command == "diagnose":
            run_snapshot = index.reconcile_from_disk()
            return _run_result(
                "ready",
                "diagnosis_complete",
                run_snapshot,
                diagnosis=Lifecycle(run_path).diagnose(),
            )
        if args.run_command == "operation":
            operation = index.operation(args.id)
            return _run_result(
                "ready",
                "operation_status",
                index.snapshot(),
                operation_id=args.id,
                operation=operation,
                safe_to_retry=operation.get("safe_to_retry", False),
            )
        if args.run_command == "retry":
            index.reconcile_from_disk()
            result = index.retry(from_failed_pages=args.from_failed_pages)
            result.pop("run")
            recovery = {"reset_units": []}
            if result["idempotency_status"] == "created" and args.from_failed_pages:
                recovery = Lifecycle(run_path).reset_failed_pages()
                index.reconcile_from_disk()
            index.complete_retry(
                result["operation_id"], from_failed_pages=args.from_failed_pages
            )
            run_snapshot = index.snapshot()
            index.event(
                "run.retry",
                {
                    "actor": "leo-ppt",
                    "status": "ready",
                    "operation_id": result["operation_id"],
                },
            )
            return _run_result(
                "ready",
                "run_retry_ready",
                run_snapshot,
                **result,
                recovery=recovery,
                next_action={"kind": "inspect_next"},
            )
        if args.run_command == "cleanup":
            lifecycle = Lifecycle(run_path)
            current = index.snapshot()
            expected_revision = (
                current["revision"]
                if args.expected_revision is None
                else args.expected_revision
            )
            if args.dry_run:
                preview = lifecycle.cleanup_preview(
                    expected_revision=expected_revision, scope=args.scope
                )
                return _run_result(
                    "ready",
                    "cleanup_preview",
                    current,
                    preview=preview,
                    safe_to_retry=False,
                )
            preview_path = args.apply or str(
                Path(run_path) / f"reports/cleanup-preview-{args.scope}.json"
            )
            receipt = lifecycle.cleanup_apply(_json_file(preview_path))
            index.event(
                "run.cleanup",
                {
                    "actor": "leo-ppt",
                    "status": "completed",
                    "operation_id": f"cleanup-{receipt['fingerprint'][:16]}",
                    "evidence_refs": ["reports/cleanup-receipt.json"],
                },
            )
            return _run_result(
                "completed",
                "cleanup_applied",
                index.snapshot(),
                operation_id=f"cleanup-{receipt['fingerprint'][:16]}",
                idempotency_status="created",
                safe_to_retry=False,
                receipt=receipt,
            )
        if index.snapshot().get("status") == "completed":
            raise IdempotencyConflict("cancel_state_conflict")
        worker_outcome = None
        cancel_workers = None
        if args.wait_workers:
            grace_seconds = float(os.environ.get("LEO_PPT_CANCEL_GRACE_SECONDS", "300"))
            lifecycle = Lifecycle(run_path)
            worker_outcome = lifecycle.wait_for_workers(
                grace_seconds=grace_seconds
            )
            worker_mutation: dict[str, Any] = {}

            def cancel_workers() -> None:
                worker_mutation.update(lifecycle.cancel_worker_units())

        result = index.cancel(
            expected_revision=args.expected_revision,
            before_commit=cancel_workers,
        )
        if worker_outcome is not None:
            worker_outcome.update(worker_mutation)
        run = result.pop("run")
        index.event(
            "run.cancelled",
            {
                "actor": "leo-ppt",
                "status": "cancelled",
                "operation_id": result["operation_id"],
            },
        )
        return _run_result(
            "cancelled",
            "run_cancelled",
            run,
            **result,
            worker_outcome=worker_outcome,
            next_action={"kind": "none"},
        )
    if args.command == "image":
        run_path = _run_path(args)
        adapter = ImageDeckAdapter(_domain_path(run_path, "image-deck"))
        if args.image_command == "prepare":
            _require_prepare_input(run_path)
            slides_path = args.slides
            if not slides_path:
                candidates = (
                    Path(run_path) / "work/slides.json",
                    Path(run_path) / "input/slides.json",
                )
                slides_path = next((str(path) for path in candidates if path.is_file()), None)
            if not slides_path:
                raise ContractError("slides_required")
            slides_path = str(_freeze_slides_contract(run_path, slides_path))
            slides = _json_file(slides_path)
            if not isinstance(slides, list) or len(slides) > 50:
                raise ContractError("input_too_large")
            existed = adapter.jobs_path.is_file()
            result = adapter.prepare(slides)
            state_hash = adapter.state_hash()
            _record_event(
                run_path,
                "image.prepared",
                status="ready",
                operation_id=f"image-prepare-{state_hash[:16]}",
            )
            return envelope(
                "ready",
                "image_deck_prepared",
                result=result,
                **_operation_payload(
                    operation_id=f"image-prepare-{state_hash[:16]}",
                    idempotency_status="replayed" if existed else "created",
                    safe_to_retry=True,
                    state_hash=state_hash,
                ),
                next_action=_worker_dispatch_action(len(slides)),
            )
        if args.image_command == "record":
            number = args.number
            if number is None and args.slide:
                try:
                    number = int(args.slide.rsplit("_", 1)[-1])
                except ValueError as exc:
                    raise ContractError("invalid_slide_id") from exc
            if number is None:
                raise ContractError("slide_required")
            image_path = args.result or args.image
            if not image_path:
                raise ContractError("result_required")
            jobs = adapter._jobs()
            expected_revision = (
                jobs["revision"] if args.expected_revision is None else args.expected_revision
            )
            operation_id = args.operation_id or f"image-{number}-{args.agent_id or 'agent'}"
            idempotency_status = (
                "replayed" if operation_id in jobs.get("operations", {}) else "created"
            )
            lease, generation = _lease_for_operation(
                run_path,
                unit_id=f"slide_{number:02d}",
                actor=args.agent_id or "agent",
                operation_id=operation_id,
                requested_lease=args.lease,
                requested_generation=args.generation,
            )
            artifact = adapter.record(
                number,
                image_path,
                backend=args.backend,
                expected_revision=expected_revision,
                operation_id=operation_id,
                agent_id=args.agent_id,
                expected_state_hash=args.expected_state_hash,
                lease=lease,
                generation=generation,
            )
            _complete_worker_operation(
                run_path,
                operation_id,
                artifact_ref=artifact.artifact_path,
            )
            _record_event(
                run_path,
                "image.recorded",
                status="ready",
                slide_id=f"slide_{number:02d}",
                operation_id=operation_id,
                artifact_ref=artifact.artifact_path,
            )
            return envelope(
                "ready",
                "image_recorded",
                artifact=artifact.to_dict(),
                **_operation_payload(
                    operation_id=operation_id,
                    idempotency_status=idempotency_status,
                    safe_to_retry=False,
                    state_hash=adapter.state_hash(),
                ),
                lease=lease,
                generation=generation,
            )
        output = _delivery_output_path(run_path, args.output)
        assert_run_quota(Path(run_path).resolve(), load_runtime_config())
        result = adapter.finalize(output, rebuild=args.rebuild)
        _mark_delivery_completed(run_path, stage="image.finalize")
        report_refs = write_delivery_reports(Path(run_path).resolve(), result)
        _record_event(
            run_path,
            "image.assembled",
            status="completed",
            operation_id=f"image-assemble-{adapter.state_hash()[:16]}",
            artifact_ref=result["pptx"],
        )
        result.pop("status", None)
        return envelope(
            "completed",
            "image_delivery_completed",
            artifact_refs=[result["pptx"], *report_refs],
            evidence_refs=report_refs,
            state_hash=adapter.state_hash(),
            safe_to_retry=True,
            operation_id=f"image-assemble-{adapter.state_hash()[:16]}",
            **result,
        )
    if args.command == "editable":
        run_path = _run_path(args)
        adapter = EditableAdapter(_domain_path(run_path, "editable"))
        if args.editable_command == "prepare":
            _require_prepare_input(run_path)
            selected_pages = _parse_pages(args.pages)
            is_top_level_run = (Path(run_path) / "run.json").is_file()
            if args.sources:
                sources = args.sources
                office_trusted = args.office_trusted
                notes_by_page = {}
            elif is_top_level_run:
                sources, office_trusted, notes_by_page = _normalize_run_sources(
                    run_path, pages=selected_pages or None
                )
            else:
                sources = _run_input_sources(run_path, pages=selected_pages or None)
                office_trusted = args.office_trusted
                notes_by_page = {}
            for source in sources:
                classify_input(source, office_trusted=office_trusted)
            limit = 50 if selected_pages else 100
            if len(sources) > limit:
                raise ContractError("input_too_large")
            existed = adapter.jobs_path.is_file()
            result = adapter.prepare(
                sources,
                worker_available=args.worker_available or is_top_level_run,
                page_numbers=sorted(selected_pages) if selected_pages else None,
                notes=notes_by_page,
            )
            run_index_path = Path(run_path) / "run.json"
            if selected_pages and run_index_path.is_file():
                run_index = RunIndex(run_path)
                run_snapshot = run_index.snapshot()
                run_index.update(
                    expected_revision=run_snapshot["revision"],
                    changes={"selected_pages": sorted(selected_pages)},
                )
            _record_event(
                run_path,
                "editable.prepared",
                status=result["status"],
                operation_id=f"editable-prepare-{adapter.state_hash()[:16]}",
            )
            return envelope(
                result["status"],
                result["reason_code"],
                result=result,
                progress=result.get("progress"),
                next_action=result.get("next_action"),
                state_hash=result.get("state_hash", adapter.state_hash()),
                operation_id=f"editable-prepare-{adapter.state_hash()[:16]}",
                idempotency_status="replayed" if existed else "created",
                safe_to_retry=True,
            )
        if args.editable_command == "next":
            result = adapter.status()
            return envelope(
                "ready",
                result["reason_code"],
                next_action=result["next_action"],
                progress=result["progress"],
                state_hash=result["state_hash"],
            )
        if args.editable_command == "dispatch":
            dispatch_operation = f"dispatch-{args.page}-{args.agent_id}"
            lease, generation = _lease_for_operation(
                run_path,
                unit_id=args.page,
                actor=args.agent_id,
                operation_id=dispatch_operation,
                requested_lease=args.lease,
                requested_generation=args.generation,
            )
            result = adapter.dispatch(
                args.page,
                args.agent_id,
                args.prompt_file,
                lease=lease,
                generation=generation,
            )
            _record_event(
                run_path,
                "editable.dispatched",
                status="active",
                page_id=args.page,
                operation_id=dispatch_operation,
            )
            return envelope(
                "ready",
                "editable_dispatch_recorded",
                **_operation_payload(
                    operation_id=f"dispatch-{args.page}-{args.agent_id}",
                    idempotency_status=result["idempotency_status"],
                    safe_to_retry=True,
                    state_hash=result["state_hash"],
                ),
                dispatch=result["page"],
                lease=lease,
                generation=generation,
            )
        if args.editable_command == "reset":
            result = adapter.reset(args.page, confirm_lost=args.confirm_lost)
            _record_event(
                run_path,
                "editable.reset",
                status="pending",
                page_id=args.page,
                operation_id=f"reset-{args.page}-{result['state_hash'][:12]}",
            )
            return envelope(
                "ready",
                "editable_page_reset",
                **_operation_payload(
                    operation_id=f"reset-{args.page}-{result['state_hash'][:12]}",
                    idempotency_status="created",
                    safe_to_retry=False,
                    state_hash=result["state_hash"],
                ),
                page=result["page"],
            )
        if args.editable_command == "finalize":
            output = _delivery_output_path(run_path, args.output)
            assert_run_quota(Path(run_path).resolve(), load_runtime_config())
            result = adapter.finalize(output)
            _mark_delivery_completed(run_path, stage="editable.finalize")
            report_refs = write_delivery_reports(Path(run_path).resolve(), result)
            _record_event(
                run_path,
                "editable.finalized",
                status="completed",
                operation_id=f"editable-finalize-{adapter.state_hash()[:16]}",
                artifact_ref=result["pptx"],
            )
            return envelope(
                "completed",
                "editable_delivery_completed",
                artifact_refs=[result["pptx"], *report_refs],
                evidence_refs=report_refs,
                safe_to_retry=True,
                state_hash=adapter.state_hash(),
                operation_id=f"editable-finalize-{adapter.state_hash()[:16]}",
                **result,
            )
        jobs = adapter._jobs()
        page = next((item for item in jobs["pages"] if item["page_id"] == args.page), None)
        if page is None:
            raise ContractError("unknown_page")
        worker_dir = Path(page.get("worker_dir", "")) if page.get("worker_dir") else None
        pptx = args.pptx or (str(worker_dir / "page.pptx") if worker_dir else None)
        validation = args.validation or (str(worker_dir / "validation.json") if worker_dir else None)
        manifest = args.manifest or (str(worker_dir / "manifest.json") if worker_dir else None)
        if not pptx or not validation or not manifest:
            raise ContractError("editable_result_paths_required")
        expected_revision = jobs["revision"] if args.expected_revision is None else args.expected_revision
        operation_id = args.operation_id or f"editable-{args.page}-{args.agent_id or 'agent'}"
        idempotency_status = (
            "replayed" if operation_id in jobs.get("operations", {}) else "created"
        )
        lease_operation_id = (
            f"dispatch-{args.page}-{args.agent_id}"
            if page.get("lease")
            else operation_id
        )
        lease, generation = _lease_for_operation(
            run_path,
            unit_id=args.page,
            actor=args.agent_id or "agent",
            operation_id=lease_operation_id,
            requested_lease=args.lease,
            requested_generation=args.generation,
        )
        artifact = adapter.record(
            args.page,
            pptx,
            validation,
            manifest,
            expected_revision=expected_revision,
            operation_id=operation_id,
            notes=args.notes,
            agent_id=args.agent_id,
            expected_state_hash=args.expected_state_hash,
            lease=lease,
            generation=generation,
        )
        _complete_worker_operation(
            run_path,
            lease_operation_id,
            artifact_ref=artifact.artifact_path,
        )
        _record_event(
            run_path,
            "editable.recorded",
            status="ready",
            page_id=args.page,
            operation_id=operation_id,
            artifact_ref=artifact.artifact_path,
        )
        return envelope(
            "ready",
            "editable_recorded",
            artifact=artifact.to_dict(),
            **_operation_payload(
                operation_id=lease_operation_id,
                idempotency_status=idempotency_status,
                safe_to_retry=False,
                state_hash=adapter.state_hash(),
            ),
            record_operation_id=operation_id,
            lease=lease,
            generation=generation,
        )
    if args.command == "upgrade":
        if args.upgrade_command == "inspect":
            baseline = inspect_image_delivery(args.source_run)
            return envelope(
                "ready",
                "upgrade_baseline_inspected",
                baseline=baseline,
                state_hash=baseline["baseline_fingerprint"],
                safe_to_retry=True,
            )
        run_path = _run_path(args)
        if args.upgrade_command == "import-baseline":
            baseline = import_baseline(args.source_run, run_path)
            return envelope(
                "ready",
                "upgrade_baseline_imported",
                baseline=baseline,
                state_hash=baseline["baseline_fingerprint"],
                idempotency_status=baseline["idempotency_status"],
                safe_to_retry=True,
            )
        if args.upgrade_command == "propose":
            plan = _upgrade_hybrid_plan(run_path)
            proposal = {
                "schema_version": 1,
                "actor": os.environ.get("USER", "unknown"),
                "proposed_at": utc_now(),
                "run_id": _json_file(Path(run_path) / "run.json").get("run_id"),
                "selected_pages": plan["selected_pages"],
                "failures": plan["failures"],
                "baseline_fingerprint": plan["baseline_fingerprint"],
                "confirmation_fingerprint": plan["confirmation_fingerprint"],
            }
            proposal_path = Path(run_path).resolve() / "reports/partial-proposal.json"
            atomic_write_json(proposal_path, proposal)
            return envelope(
                "ready",
                "partial_hybrid_proposed",
                proposal=proposal,
                evidence_refs=[str(proposal_path)],
                state_hash=plan["confirmation_fingerprint"] or plan["baseline_fingerprint"],
                safe_to_retry=True,
            )
        run = _json_file(Path(run_path) / "run.json")
        if not (Path(run_path) / "image-baseline" / "baseline.json").is_file():
            raise ContractError("upgrade_baseline_required")
        output = _delivery_output_path(run_path, args.output)
        assert_run_quota(Path(run_path).resolve(), load_runtime_config())
        editable_adapter = EditableAdapter(_domain_path(run_path, "editable"))
        if run["route"] == "upgrade-full":
            result = editable_adapter.finalize(output)
        elif run["route"] == "upgrade-selected":
            plan = _upgrade_hybrid_plan(run_path)
            selected = set(plan["selected_pages"])
            failures = {int(key): value for key, value in plan["failures"].items()}
            if failures and not getattr(args, "partial_confirmation", None):
                raise ContractError("partial_hybrid_confirmation_required")
            proposal_path = Path(run_path).resolve() / "reports/partial-proposal.json"
            if failures:
                if not proposal_path.is_file():
                    raise ContractError("partial_hybrid_proposal_required")
                proposal = _json_file(proposal_path)
                if (
                    proposal.get("confirmation_fingerprint") != args.partial_confirmation
                    or proposal.get("baseline_fingerprint") != plan["baseline_fingerprint"]
                    or proposal.get("selected_pages") != plan["selected_pages"]
                    or proposal.get("failures") != plan["failures"]
                ):
                    raise ContractError("partial_hybrid_proposal_stale")
            artifacts = plan["artifacts"]
            baseline_fingerprint = plan["baseline_fingerprint"]
            confirmation = (
                args.partial_confirmation
                if failures
                else None
            )
            result = HybridAssembler().assemble(
                artifacts,
                output,
                selected_pages=selected,
                failures=failures,
                partial_confirmation=confirmation,
            )
            if failures:
                receipt_path = Path(run_path).resolve() / "reports/partial-confirmation.json"
                atomic_write_json(
                    receipt_path,
                    {
                        "schema_version": 1,
                        "actor": os.environ.get("USER", "unknown"),
                        "confirmed_at": utc_now(),
                        "baseline_fingerprint": baseline_fingerprint,
                        "selected_pages": sorted(selected),
                        "failures": {str(key): value for key, value in failures.items()},
                        "confirmation_fingerprint": confirmation,
                    },
                )
        else:
            raise ContractError("upgrade_route_required")
        upgrade_operation_id = (
            f"upgrade-finalize-{sha256_bytes(canonical_json(result).encode())[:16]}"
        )
        report_refs = write_delivery_reports(Path(run_path).resolve(), result)
        partial_receipt = Path(run_path).resolve() / "reports/partial-confirmation.json"
        if partial_receipt.is_file() and str(partial_receipt) not in report_refs:
            report_refs.append(str(partial_receipt))
        _mark_delivery_completed(run_path, stage="hybrid.finalize")
        _record_event(
            run_path,
            "upgrade.finalized",
            status="completed",
            operation_id=upgrade_operation_id,
            artifact_ref=result["pptx"],
        )
        upgrade_payload = {
            **result,
            "idempotency_status": result.get("idempotency_status", "created"),
        }
        return envelope(
            "completed",
            "upgrade_delivery_completed",
            artifact_refs=[result["pptx"], *report_refs],
            evidence_refs=report_refs,
            safe_to_retry=True,
            state_hash=sha256_bytes(canonical_json(result).encode()),
            operation_id=upgrade_operation_id,
            **upgrade_payload,
        )
    if args.command == "style":
        home = Path(args.home).expanduser().resolve() if args.home else None
        if args.style_command == "list":
            return envelope("ready", "style_listed", styles=list_styles(home=home), safe_to_retry=True)
        if args.style_command == "load":
            result = load_style(args.name, home=home)
            return envelope("ready", "style_loaded", style=result, safe_to_retry=True)
        if args.style_command == "render":
            if getattr(args, "list_templates", False):
                return envelope(
                    "ready", "templates_listed",
                    templates=list_templates(), safe_to_retry=True,
                )
            result = compose_style(args.style, mode=args.mode)
            if args.layout:
                result["layout"] = compose_layout(
                    args.layout, image_type=args.image_type
                )
            return envelope(
                "ready", "style_rendered", template=result, safe_to_retry=True,
            )
        try:
            content = Path(args.content_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise StyleStoreError("style_content_unreadable") from exc
        result = save_style(
            args.name,
            content,
            home=home,
            overwrite=args.overwrite,
            rename=args.rename,
        )
        return envelope("completed", "style_saved", style=result, safe_to_retry=False)
    if args.command == "evidence":
        run_path = _run_path(args)
        if args.evidence_command == "provenance":
            result = record_provenance(run_path, args.receipt)
            reason_code = "provenance_recorded"
        elif args.evidence_command == "visual":
            result = record_visual(run_path, args.receipt)
            reason_code = "visual_evidence_recorded"
        else:
            result = record_acceptance(run_path, args.receipt)
            reason_code = "manual_acceptance_recorded"
        return envelope(
            "completed",
            reason_code,
            evidence_refs=[result["path"]],
            receipt=result,
            idempotency_status=result["idempotency_status"],
            safe_to_retry=True,
        )
    if args.command == "delivery":
        artifacts = [PageArtifact.from_dict(value) for value in _json_file(args.artifacts)]
        failures = {int(key): value for key, value in (_json_file(args.failures) if args.failures else {}).items()}
        result = HybridAssembler().assemble(
            artifacts,
            args.output,
            selected_pages=_parse_pages(args.selected_pages) or None,
            failures=failures,
            partial_confirmation=args.partial_confirmation,
        )
        operation_id = f"delivery-{sha256_bytes(canonical_json(result).encode())[:16]}"
        delivery_payload = {**result, "idempotency_status": result.get("idempotency_status", "created")}
        return envelope(
            "completed",
            "delivery_completed",
            operation_id=operation_id,
            safe_to_retry=True,
            state_hash=sha256_bytes(canonical_json(result).encode()),
            **delivery_payload,
        )
    if args.command == "upstream":
        result = run_upstream(
            args.capability,
            args.arguments,
            backend_contract=args.backend_contract,
            timeout_seconds=args.timeout,
        )
        status = "completed" if result["returncode"] == 0 else "blocked"
        reason = (
            "upstream_tool_completed"
            if result["returncode"] == 0
            else ("upstream_subprocess_timeout" if result.get("timed_out") else "upstream_tool_failed")
        )
        return envelope(status, reason, result=result)
    lifecycle = Lifecycle(args.run_dir)
    if args.dry_run:
        if args.expected_revision is None:
            raise CleanupConflict("cleanup_revision_required")
        preview = lifecycle.cleanup_preview(expected_revision=args.expected_revision)
        return envelope("ready", "cleanup_preview", preview=preview)
    return envelope("completed", "cleanup_applied", receipt=lifecycle.cleanup_apply(_json_file(args.apply)))


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    started = time.monotonic()
    run_dir = resolve_run_dir(args)
    name = command_name(args)
    try:
        result = _dispatch_impl(args)
    except Exception as error:
        record_command(
            run_dir,
            command=name,
            started_at=started_at,
            duration_seconds=time.monotonic() - started,
            status="blocked",
            reason_code=str(error) or getattr(error, "reason_code", "unhandled_error"),
        )
        raise
    is_created = result.get("idempotency_status") != "replayed"
    unit_id = getattr(args, "page", None) or getattr(args, "slide", None)
    worker_duration = getattr(args, "worker_duration_seconds", None)
    backend_duration = getattr(args, "backend_duration_seconds", None)
    backend_name = getattr(args, "backend", None)
    page_measurement = None
    backend_measurement = None
    if is_created and unit_id and worker_duration is not None:
        page_measurement = {
            "unit_id": unit_id,
            "command": name,
            "duration_seconds": worker_duration,
            "status": result.get("status", "unknown"),
        }
    if is_created and unit_id and backend_duration is not None:
        backend_measurement = {
            "unit_id": unit_id,
            "backend": backend_name or "not_recorded",
            "duration_seconds": backend_duration,
            "status": result.get("status", "unknown"),
        }
    record_command(
        run_dir,
        command=name,
        started_at=started_at,
        duration_seconds=time.monotonic() - started,
        status=result.get("status", "unknown"),
        reason_code=result.get("reason_code", "unknown"),
        page_measurement=page_measurement,
        backend_measurement=backend_measurement,
    )
    return result


ERRORS = (
    BackendExecutionError,
    EvidenceError,
    BackendContractError,
    RuntimeConfigError,
    ConfigServiceError,
    CleanupConflict,
    ContractError,
    IdempotencyConflict,
    RevisionConflict,
    RouteContractError,
    StyleStoreError,
    UpstreamBridgeError,
    SetupContractError,
    CredentialError,
    WizardCancelled,
)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        invoked = Path(sys.argv[0]).expanduser()
        if invoked.is_absolute():
            resolved = invoked.resolve()
            if resolved.is_file() and os.access(resolved, os.X_OK):
                os.environ["LEO_PPT_CLI_PROG"] = str(resolved)
    args = build_parser().parse_args(argv)
    try:
        result = dispatch(args)
        if args.command == "version" and not args.json:
            print(f"leo-ppt {result['package_version']}")
            print(f"runtime {result['runtime_version']}")
            print(f"install channel {result['install_channel']}")
            print(f"config schema v{result['config_schema_version']}")
            print(f"setup schema v{result['setup_schema_version']}")
        elif args.command == "setup" and not args.json:
            print(render_setup_report(result))
        else:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2 if result["status"] in {"blocked", "action_required", "choice_required"} else 0
    except ERRORS as error:
        reason = str(error) or getattr(error, "reason_code", "contract_error")
        print(json.dumps(envelope("blocked", reason, next_action={"kind": "inspect_reason_code"}), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
