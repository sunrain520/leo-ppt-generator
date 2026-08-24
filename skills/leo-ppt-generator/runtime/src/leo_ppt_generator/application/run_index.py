"""轻量跨阶段 run index；领域状态仍保持权威。"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock

from ..storage import (
    atomic_write_json,
    canonical_json,
    durable_copy_file,
    inspect_regular_file,
    sha256_bytes,
)

MAX_INPUT_BYTES = 100 * 1024 * 1024
MAX_BACKEND_CONTRACT_BYTES = 1024 * 1024


class RevisionConflict(RuntimeError):
    reason_code = "revision_conflict"


class IdempotencyConflict(RuntimeError):
    reason_code = "idempotency_conflict"


@dataclass(frozen=True)
class RunCreation:
    index: RunIndex
    idempotency_status: str


class RunIndex:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.path = self.run_dir / "run.json"
        self.lock = FileLock(str(self.run_dir / ".run.json.lock"))

    @classmethod
    def create(cls, run_dir: str | Path, *, route: str, runtime_identity: str) -> RunIndex:
        from .routes import route_definition

        route_definition(route)
        owner = cls(run_dir)
        owner.run_dir.mkdir(parents=True, exist_ok=True)
        created = False
        with owner.lock:
            if owner.path.exists():
                current = owner.snapshot()
                if current.get("route") != route or current.get("runtime_identity") != runtime_identity:
                    raise RevisionConflict("run_identity_conflict")
                return owner
            atomic_write_json(
                owner.path,
                {
                    "schema_version": 1,
                    "run_id": uuid.uuid4().hex,
                    "route": route,
                    "runtime_identity": runtime_identity,
                    "output_dir": str(owner.run_dir),
                    "revision": 0,
                    "generation": 0,
                    "leases": {},
                    "status": "created",
                    "stage": "created",
                    "domains": {},
                    "supplemental_inputs": {},
                    "operations": {},
                },
            )
            created = True
        if created:
            owner.event(
                "run.created",
                {
                    "actor": "leo-ppt",
                    "status": "created",
                    "subject": owner.snapshot()["run_id"],
                },
            )
        return owner

    @classmethod
    def create_from_request(
        cls,
        output_dir: str | Path,
        *,
        route: str,
        input_path: str | Path,
        backend_contract_path: str | Path,
        runtime_identity: str,
        idempotency_key: str | None = None,
        office_trusted: bool = False,
        project_root: str | Path | None = None,
    ) -> RunCreation:
        """创建计划稳定合同的 run，并冻结所有恢复所需输入。"""
        from ..config.backend_contract import BackendRegistry
        from ..contracts import ContractError
        from .routes import classify_input, route_definition, validate_input_content

        route_definition(route)
        try:
            source_identity = inspect_regular_file(input_path, max_bytes=MAX_INPUT_BYTES)
            backend_identity = inspect_regular_file(
                backend_contract_path, max_bytes=MAX_BACKEND_CONTRACT_BYTES
            )
        except ValueError as exc:
            raise ContractError(str(exc)) from exc

        kind = classify_input(source_identity["path"], office_trusted=office_trusted)
        validate_input_content(source_identity["path"], kind)
        allowed_kinds = {
            "generate": {"content"},
            "direct-editable": {"image", "pdf", "office"},
            "upgrade-full": {"office"},
            "upgrade-selected": {"office"},
        }
        if kind not in allowed_kinds[route]:
            raise ContractError("input_route_mismatch")
        try:
            backend_value = json.loads(
                Path(backend_identity["path"]).read_text(encoding="utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("backend_contract_invalid") from exc
        if not isinstance(backend_value, dict):
            raise ContractError("backend_contract_invalid")
        required = {"generate"} if route == "generate" else {"edit"}
        backend = BackendRegistry.default().load(backend_value, required=required)
        expected_mode = "generate" if route == "generate" else "edit"
        if backend_value.get("mode") != expected_mode:
            raise ContractError("backend_mode_route_mismatch")

        owner = cls(output_dir)
        requested_project_root = Path(project_root) if project_root else None
        if requested_project_root is not None and (
            requested_project_root.is_symlink()
            or any(
                (requested_project_root / directory).is_symlink()
                for directory in ("sources", "contracts", "samples", "runs", "deliveries")
            )
        ):
            raise ContractError("project_path_untrusted")
        resolved_project_root = (
            requested_project_root.resolve() if requested_project_root is not None else None
        )
        if resolved_project_root is not None:
            runs_root = (resolved_project_root / "runs").resolve()
            try:
                relative_run = owner.run_dir.relative_to(runs_root)
            except ValueError as exc:
                raise ContractError("run_output_outside_project") from exc
            if not relative_run.parts:
                raise ContractError("run_output_outside_project")
            for identity, directory, reason_code in (
                (source_identity, "sources", "input_outside_project"),
                (backend_identity, "contracts", "backend_contract_outside_project"),
            ):
                try:
                    identity["path"].relative_to((resolved_project_root / directory).resolve())
                except ValueError as exc:
                    raise ContractError(reason_code) from exc

        fingerprint_payload = {
            "schema_version": 1,
            "route": route,
            "input_sha256": source_identity["sha256"],
            "input_kind": kind,
            "backend_contract_sha256": backend_identity["sha256"],
            "runtime_identity": runtime_identity,
            "office_trusted": office_trusted,
        }
        if resolved_project_root is not None:
            fingerprint_payload["project_root"] = str(resolved_project_root)
        fingerprint = sha256_bytes(canonical_json(fingerprint_payload).encode())
        if resolved_project_root is not None:
            for directory in ("sources", "contracts", "samples", "runs", "deliveries"):
                path = resolved_project_root / directory
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(path, 0o700)
        owner.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(owner.run_dir, 0o700)
        with owner.lock:
            if owner.path.exists():
                current = owner.snapshot()
                same_key = current.get("idempotency_key") == idempotency_key
                if idempotency_key and same_key and current.get("request_fingerprint") == fingerprint:
                    return RunCreation(owner, "replayed")
                raise IdempotencyConflict("idempotency_conflict")

            input_name = Path(source_identity["path"]).name
            input_relative = Path("input") / input_name
            copied_input = durable_copy_file(
                source_identity["path"],
                owner.run_dir / input_relative,
                max_bytes=MAX_INPUT_BYTES,
            )
            backend_relative = Path("input") / "backend-contract.json"
            copied_backend = durable_copy_file(
                backend_identity["path"],
                owner.run_dir / backend_relative,
                max_bytes=MAX_BACKEND_CONTRACT_BYTES,
            )
            if copied_input["sha256"] != source_identity["sha256"]:
                raise ContractError("input_changed_during_copy")
            if copied_backend["sha256"] != backend_identity["sha256"]:
                raise ContractError("backend_contract_changed_during_copy")
            for directory in ("tmp", "work", "image-deck", "editable", "logs", "reports", "final"):
                path = owner.run_dir / directory
                path.mkdir(exist_ok=True, mode=0o700)
                os.chmod(path, 0o700)
            atomic_write_json(
                owner.path,
                {
                    "schema_version": 1,
                    "run_id": uuid.uuid4().hex,
                    "route": route,
                    "runtime_identity": runtime_identity,
                    "revision": 0,
                    "generation": 0,
                    "leases": {},
                    "status": "created",
                    "stage": "created",
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "output_dir": str(owner.run_dir),
                    "project_root": str(resolved_project_root) if resolved_project_root else None,
                    "idempotency_key": idempotency_key,
                    "request_fingerprint": fingerprint,
                    "input": {
                        "original_path": str(source_identity["path"]),
                        "path": input_relative.as_posix(),
                        "kind": kind,
                        "size": copied_input["size"],
                        "sha256": copied_input["sha256"],
                        "office_trusted": office_trusted,
                    },
                    "input_available": True,
                    "backend_contract": {
                        "path": backend_relative.as_posix(),
                        "sha256": copied_backend["sha256"],
                        "backend": backend.name,
                        "backend_kind": backend.backend_kind,
                        "model": backend_value["model"],
                        "mode": backend_value["mode"],
                        "credential_source": backend_value["credential_source"],
                        "selection_source": backend_value["selection_source"],
                        "selection": backend_value.get("selection"),
                        "capabilities": backend_value["capabilities"],
                        "schema_version": backend_value["schema_version"],
                    },
                    "selected_pages": [],
                    "page_order": [],
                    "notes": {},
                    "supplemental_inputs": {},
                    "domains": {
                        "image": {"path": "image-deck"},
                        "editable": {"path": "editable"},
                    },
                    "operations": {},
                    "artifacts": [],
                },
            )
        owner.event(
            "run.created",
            {
                "actor": "leo-ppt",
                "status": "created",
                "subject": owner.snapshot()["run_id"],
                "operation_id": idempotency_key,
            },
        )
        return RunCreation(owner, "created")

    def snapshot(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _mutate(self, callback) -> dict[str, Any]:
        with self.lock:
            current = self.snapshot()
            changed = callback(current)
            if changed is None:
                return current
            atomic_write_json(self.path, changed)
            return changed

    def update(self, *, expected_revision: int, changes: dict[str, Any]) -> dict[str, Any]:
        def apply(current):
            if current["revision"] != expected_revision:
                raise RevisionConflict("revision_conflict")
            protected = {
                "schema_version",
                "run_id",
                "route",
                "runtime_identity",
                "operations",
                "input",
                "input_available",
                "prepare_disabled_reason",
                "backend_contract",
                "request_fingerprint",
                "idempotency_key",
            }
            if protected.intersection(changes):
                raise RevisionConflict("immutable_run_field")
            current.update(changes)
            current["revision"] += 1
            return current

        return self._mutate(apply)

    def checkpoint_readiness_pause(
        self,
        *,
        expected_revision: int,
        stage: str,
        required_capabilities: tuple[str, ...] = (),
        operation_id: str | None = None,
        artifact_refs: tuple[str, ...] = (),
        recovery_ref: str | None = None,
    ) -> dict[str, Any]:
        """原子记录非敏感 readiness 暂停 checkpoint；不保存用户材料或 secret。

        用于 Host_Readiness_Guard 在图片节点暂停；复查 allowed 后清除 pause
        并从同一节点恢复。
        """

        checkpoint = {
            "stage": stage,
            "required_capabilities": list(required_capabilities),
            "operation_id": operation_id,
            "artifact_refs": list(artifact_refs),
            "recovery_ref": recovery_ref,
        }
        return self.update(
            expected_revision=expected_revision,
            changes={"readiness_pause": checkpoint},
        )

    def clear_readiness_pause(self, *, expected_revision: int) -> dict[str, Any]:
        return self.update(
            expected_revision=expected_revision,
            changes={"readiness_pause": None},
        )

    def reconcile(
        self,
        domains: dict[str, Any],
        *,
        artifacts: list[str] | None = None,
        status: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        def apply(current):
            desired_domains = {**current["domains"], **domains}
            changed = desired_domains != current["domains"]
            if artifacts is not None and artifacts != current.get("artifacts", []):
                current["artifacts"] = artifacts
                changed = True
            if status is not None and status != current.get("status"):
                current["status"] = status
                changed = True
            if stage is not None and stage != current.get("stage"):
                current["stage"] = stage
                changed = True
            if not changed:
                return None
            current["domains"] = desired_domains
            current["revision"] += 1
            return current

        return self._mutate(apply)

    def reconcile_from_disk(self) -> dict[str, Any]:
        """只把可由领域状态与正式 hash 唯一推导的事实写回轻量索引。"""
        from ..contracts import ContractError
        from ..storage import sha256_file

        domains: dict[str, Any] = {}
        artifacts: list[str] = []

        def progress(items: list[dict[str, Any]], *, complete_state: str) -> dict[str, Any]:
            counts = {
                "total_units": len(items),
                "completed": 0,
                "failed": 0,
                "active": 0,
                "pending": 0,
            }
            for item in items:
                state = item.get("status")
                if state == complete_state:
                    counts["completed"] += 1
                elif state in {"failed", "blocked", "timeout"}:
                    counts["failed"] += 1
                elif state in {"active", "dispatched", "running"}:
                    counts["active"] += 1
                elif state != "cancelled":
                    counts["pending"] += 1
            return {**counts, "estimated_remaining_seconds": None}

        image_path = self.run_dir / "image-deck/slide_jobs.json"
        if image_path.is_file():
            image = json.loads(image_path.read_text(encoding="utf-8"))
            image_progress = progress(image.get("slides", []), complete_state="recorded")
            domain = {
                "path": "image-deck",
                "state_hash": sha256_bytes(canonical_json(image).encode()),
                "progress": image_progress,
                "status": image.get("run_status", "prepared"),
            }
            delivery = image.get("delivery")
            if delivery:
                path = Path(delivery.get("pptx", ""))
                if not path.is_file() or sha256_file(path) != delivery.get("sha256"):
                    raise ContractError("state_mismatch")
                artifacts.append(str(path.resolve()))
                domain["delivery"] = delivery
            domains["image"] = domain

        editable_path = self.run_dir / "editable/page_jobs.json"
        if editable_path.is_file():
            editable = json.loads(editable_path.read_text(encoding="utf-8"))
            editable_progress = progress(editable.get("pages", []), complete_state="recorded")
            domain = {
                "path": "editable",
                "state_hash": sha256_bytes(canonical_json(editable).encode()),
                "progress": editable_progress,
                "status": editable.get("run_status", "prepared"),
            }
            delivery = editable.get("delivery")
            if delivery:
                path = Path(delivery.get("pptx", ""))
                expected = delivery.get("pptx_sha256")
                if not path.is_file() or sha256_file(path) != expected:
                    raise ContractError("state_mismatch")
                artifacts.append(str(path.resolve()))
                domain["delivery"] = delivery
            domains["editable"] = domain

        delivery_manifests = sorted((self.run_dir / "final").glob("*.delivery.json"))
        if delivery_manifests:
            candidates = []
            for manifest_path in delivery_manifests:
                value = json.loads(manifest_path.read_text(encoding="utf-8"))
                pptx = Path(value.get("pptx", ""))
                if not pptx.is_file() or sha256_file(pptx) != value.get("pptx_sha256"):
                    raise ContractError("state_mismatch")
                candidates.append((int(value.get("artifact_revision", 1)), pptx, manifest_path))
            _, latest_pptx, latest_manifest = max(candidates, key=lambda item: item[0])
            artifacts.extend([str(latest_pptx.resolve()), str(latest_manifest.resolve())])

        current = self.snapshot()
        progress_values = [
            domain["progress"] for domain in domains.values() if "progress" in domain
        ]
        route = current["route"]
        if route == "generate":
            completed_delivery = bool(domains.get("image", {}).get("delivery"))
        elif route in {"direct-editable", "upgrade-full"}:
            completed_delivery = bool(domains.get("editable", {}).get("delivery"))
        else:
            completed_delivery = bool(delivery_manifests)
        has_failed = any(value["failed"] for value in progress_values)
        has_active = any(value["active"] for value in progress_values)
        has_pending = any(value["pending"] for value in progress_values)
        if current.get("status") == "cancelled":
            derived_status = "cancelled"
        elif completed_delivery:
            derived_status = "completed"
        elif has_failed:
            derived_status = "failed"
        elif has_active or has_pending or progress_values:
            derived_status = "in_progress"
        else:
            derived_status = current.get("status", "created")
        if route == "generate":
            derived_stage = "image.finalize" if completed_delivery else (
                "image.dispatch" if "image" in domains else current.get("stage", "created")
            )
        elif route == "direct-editable":
            derived_stage = "editable.finalize" if completed_delivery else (
                "editable.dispatch" if "editable" in domains else current.get("stage", "created")
            )
        elif route == "upgrade-full":
            derived_stage = "editable.finalize" if completed_delivery else (
                "editable.dispatch" if "editable" in domains else "image.inspect"
            )
        else:
            derived_stage = "hybrid.assemble" if completed_delivery else (
                "editable.dispatch" if "editable" in domains else "image.inspect"
            )
        artifacts = list(dict.fromkeys(artifacts))
        return self.reconcile(
            domains,
            artifacts=artifacts,
            status=derived_status,
            stage=derived_stage,
        )

    def begin_operation(self, operation_id: str, fingerprint: str, *, mutation: str) -> dict[str, Any]:
        outcome: dict[str, str] = {}

        def apply(current):
            existing = current["operations"].get(operation_id)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise IdempotencyConflict("idempotency_conflict")
                outcome["value"] = "replay" if existing["status"] == "completed" else "in_progress"
                return None
            current["operations"][operation_id] = {
                "mutation": mutation,
                "fingerprint": fingerprint,
                "status": "started",
                "safe_to_retry": True,
            }
            current["revision"] += 1
            outcome["value"] = "started"
            return current

        changed = self._mutate(apply)
        return {"outcome": outcome["value"], "operation": changed["operations"][operation_id]}

    def complete_operation(self, operation_id: str, *, result: dict[str, Any]) -> dict[str, Any]:
        def apply(current):
            operation = current["operations"].get(operation_id)
            if not operation:
                raise IdempotencyConflict("unknown_operation")
            if operation.get("status") == "completed":
                return None
            operation.update({"status": "completed", "safe_to_retry": False, "result": result})
            lease = current.get("leases", {}).get(operation_id)
            if lease is not None:
                lease["status"] = "completed"
            current["revision"] += 1
            return current

        return self._mutate(apply)

    def operation(self, operation_id: str) -> dict[str, Any]:
        operation = self.snapshot().get("operations", {}).get(operation_id)
        if operation is None:
            raise IdempotencyConflict("unknown_operation")
        return operation

    def issue_lease(self, unit_id: str, *, actor: str, operation_id: str) -> dict[str, Any]:
        """在当前 generation 下发行一次性 worker lease。"""
        outcome: dict[str, Any] = {}

        def apply(current):
            if current.get("status") in {"cancelled", "completed"}:
                raise IdempotencyConflict("run_not_mutable")
            leases = current.setdefault("leases", {})
            existing = leases.get(operation_id)
            if existing:
                outcome.update(existing)
                return None
            lease = {
                "lease": uuid.uuid4().hex,
                "unit_id": unit_id,
                "actor": actor,
                "generation": int(current.get("generation", 0)),
                "operation_id": operation_id,
                "status": "active",
            }
            leases[operation_id] = lease
            current.setdefault("operations", {}).setdefault(
                operation_id,
                {
                    "mutation": "worker.record",
                    "fingerprint": operation_id,
                    "status": "started",
                    "safe_to_retry": True,
                    "lease": lease["lease"],
                    "generation": lease["generation"],
                },
            )
            current["revision"] += 1
            outcome.update(lease)
            return current

        self._mutate(apply)
        return dict(outcome)

    def validate_lease(self, *, operation_id: str, lease: str, generation: int) -> dict[str, Any]:
        current = self.snapshot()
        value = current.get("leases", {}).get(operation_id)
        if not value or value.get("lease") != lease:
            raise IdempotencyConflict("lease_invalid")
        if value.get("status") != "active" or value.get("generation") != generation:
            raise IdempotencyConflict("lease_revoked")
        if current.get("generation", 0) != generation:
            raise IdempotencyConflict("generation_conflict")
        if current.get("status") in {"cancelled", "completed"}:
            raise IdempotencyConflict("run_not_mutable")
        return value

    def retry(self, *, from_failed_pages: bool) -> dict[str, Any]:
        outcome: dict[str, Any] = {}

        def apply(current):
            if current.get("status") in {"cancelled", "completed"}:
                raise IdempotencyConflict("run_not_retryable")
            state_fingerprint = sha256_bytes(
                canonical_json(
                    {
                        "stage": current["stage"],
                        "domains": current["domains"],
                        "from_failed_pages": from_failed_pages,
                    }
                ).encode()
            )
            prior = [
                (operation_id, operation)
                for operation_id, operation in current["operations"].items()
                if operation.get("mutation") == "run.retry"
            ]
            if prior:
                operation_id, operation = prior[-1]
                if state_fingerprint not in {
                    operation["fingerprint"],
                    operation.get("result_fingerprint"),
                }:
                    raise IdempotencyConflict("retry_state_conflict")
                outcome.update(
                    {
                        "operation_id": operation_id,
                        "idempotency_status": "replayed",
                        "safe_to_retry": operation["safe_to_retry"],
                    }
                )
                return None
            operation_id = f"retry-{state_fingerprint[:16]}"
            current["operations"][operation_id] = {
                "mutation": "run.retry",
                "fingerprint": state_fingerprint,
                "status": "completed",
                "safe_to_retry": True,
                "from_failed_pages": from_failed_pages,
            }
            current["status"] = "in_progress"
            current["revision"] += 1
            outcome.update(
                {
                    "operation_id": operation_id,
                    "idempotency_status": "created",
                    "safe_to_retry": True,
                }
            )
            return current

        run = self._mutate(apply)
        return {**outcome, "run": run}

    def complete_retry(self, operation_id: str, *, from_failed_pages: bool) -> dict[str, Any]:
        def apply(current):
            operation = current["operations"].get(operation_id)
            if not operation or operation.get("mutation") != "run.retry":
                raise IdempotencyConflict("unknown_operation")
            result_fingerprint = sha256_bytes(
                canonical_json(
                    {
                        "stage": current["stage"],
                        "domains": current["domains"],
                        "from_failed_pages": from_failed_pages,
                    }
                ).encode()
            )
            if operation.get("result_fingerprint") == result_fingerprint:
                return None
            operation["result_fingerprint"] = result_fingerprint
            current["revision"] += 1
            return current

        return self._mutate(apply)

    def cancel(
        self,
        *,
        expected_revision: int | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {}

        def apply(current):
            if current.get("status") == "cancelled":
                existing = next(
                    (
                        (operation_id, operation)
                        for operation_id, operation in current["operations"].items()
                        if operation.get("mutation") == "run.cancel"
                    ),
                    (f"cancel-{current['run_id']}", {"safe_to_retry": False}),
                )
                outcome.update(
                    {
                        "operation_id": existing[0],
                        "idempotency_status": "replayed",
                        "safe_to_retry": False,
                    }
                )
                return None
            if current.get("status") == "completed":
                raise IdempotencyConflict("cancel_state_conflict")
            if expected_revision is not None and current["revision"] != expected_revision:
                raise RevisionConflict("revision_conflict")
            if before_commit is not None:
                before_commit()
            fingerprint = sha256_bytes(
                canonical_json(
                    {
                        "revision": current["revision"],
                        "status": current["status"],
                        "stage": current["stage"],
                    }
                ).encode()
            )
            operation_id = f"cancel-{fingerprint[:16]}"
            current["operations"][operation_id] = {
                "mutation": "run.cancel",
                "fingerprint": fingerprint,
                "status": "completed",
                "safe_to_retry": False,
            }
            current["status"] = "cancelled"
            current["generation"] = int(current.get("generation", 0)) + 1
            for lease in current.get("leases", {}).values():
                if lease.get("status") == "active":
                    lease["status"] = "revoked"
            current["revision"] += 1
            outcome.update(
                {
                    "operation_id": operation_id,
                    "idempotency_status": "created",
                    "safe_to_retry": False,
                }
            )
            return current

        run = self._mutate(apply)
        return {**outcome, "run": run}

    def event(self, kind: str, data: dict[str, Any]) -> None:
        allowed_keys = {
            "actor",
            "page_id",
            "slide_id",
            "subject",
            "status",
            "reason_code",
            "operation_id",
            "artifact_ref",
            "evidence_refs",
        }
        allowed = {key: value for key, value in data.items() if key in allowed_keys}
        event_path = self.run_dir / "events.ndjson"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.run_dir / ".events.ndjson.lock")):
            sequence = 0
            if event_path.is_file():
                for raw_line in event_path.read_text(encoding="utf-8").splitlines():
                    try:
                        previous = json.loads(raw_line)
                    except json.JSONDecodeError:
                        break
                    if isinstance(previous.get("seq"), int):
                        sequence = max(sequence, previous["seq"])
            line = canonical_json(
                {
                    "schema_version": 1,
                    "seq": sequence + 1,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "kind": kind,
                    "data": allowed,
                }
            ) + "\n"
            descriptor = os.open(
                event_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
            )
            try:
                os.write(descriptor, line.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
