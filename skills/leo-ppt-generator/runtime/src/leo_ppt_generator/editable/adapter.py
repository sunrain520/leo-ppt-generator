"""固定 editable 算法与状态合同的稳定 adapter。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from filelock import FileLock
from pptx import Presentation

from .._vendor.editable_ppt.editppt.runtime import (
    build_pptx_from_manifest as _vendor_builder,
)

# adapter 不导入 vendor 的领域状态模块。vendor 只作为无状态格式/构建工具；
# 用户可见的 page_jobs.json 由本 adapter 唯一持有。
from ..config.runtime_config import load_runtime_config
from ..contracts import ContractError, PageArtifact
from ..storage import (
    atomic_materialize,
    atomic_write_json,
    canonical_json,
    durable_copy_file,
    fsync_file,
    sha256_bytes,
    sha256_file,
)


class EditableAdapter:
    contract_version = 1

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.jobs_path = self.run_dir / "page_jobs.json"

    def prepare(
        self,
        sources: list[str | Path],
        *,
        worker_available: bool,
        page_numbers: list[int] | None = None,
        notes: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        if not sources or len(sources) > 100:
            raise ContractError("input_too_large" if len(sources) > 100 else "empty_deck")
        if len(sources) > 1 and not worker_available:
            return {"status": "blocked", "reason_code": "worker_capability_unavailable", "next_action": {"kind": "provide_worker_capability"}}
        if page_numbers is not None and len(page_numbers) != len(sources):
            raise ContractError("page_selection_mismatch")
        numbers = page_numbers or list(range(1, len(sources) + 1))
        pages = []
        notes = notes or {}
        for number, value in zip(numbers, sources):
            source = Path(value).resolve()
            if not source.is_file():
                raise ContractError("missing_source")
            pages.append(
                {
                    "page_id": f"page_{number:03d}",
                    "number": number,
                    "status": "pending",
                    "source": str(source),
                    "page_dir": str(source.parent),
                    "source_sha256": sha256_file(source),
                    "notes": str(notes.get(number, "")),
                }
            )
        fingerprint = sha256_bytes(
            canonical_json(
                [
                    (page["page_id"], page["source"], page["source_sha256"], page.get("notes", ""))
                    for page in pages
                ]
            ).encode()
        )
        if self.jobs_path.is_file():
            existing = self._jobs()
            if existing.get("prepare_fingerprint") == fingerprint:
                return self.status()
            raise ContractError("editable_prepare_fingerprint_conflict")
        jobs = {
            "schema_version": 1,
            "revision": 0,
            "run_status": "prepared",
            "prepare_fingerprint": fingerprint,
            "pages": pages,
            "operations": {},
        }
        atomic_write_json(self.jobs_path, jobs)
        return self.status()

    def _jobs(self) -> dict[str, Any]:
        if not self.jobs_path.is_file():
            raise ContractError("editable_not_prepared")
        return json.loads(self.jobs_path.read_text(encoding="utf-8"))

    def _assert_run_mutable(self) -> None:
        run_path = self.run_dir.parent / "run.json"
        if run_path.is_file():
            try:
                status = json.loads(run_path.read_text(encoding="utf-8")).get("status")
            except (OSError, ValueError, TypeError) as exc:
                raise ContractError("run_index_invalid") from exc
            if status == "cancelled":
                raise ContractError("run_cancelled_mutation_forbidden")

    def state_hash(self) -> str:
        return sha256_bytes(canonical_json(self._jobs()).encode())

    @staticmethod
    def _manifest_dimensions(manifest: dict[str, Any]) -> tuple[int, int]:
        source = manifest.get("source")
        if not isinstance(source, dict):
            raise ContractError("manifest_invalid")
        width = source.get("width_px")
        height = source.get("height_px")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ContractError("manifest_invalid")
        return width, height

    @staticmethod
    def slide_size_for_artifact(artifact: PageArtifact) -> tuple[float, float]:
        if artifact.mode == "editable":
            try:
                manifest = json.loads(Path(artifact.manifest_path or "").read_text(encoding="utf-8"))
                slide = manifest["slide"]
                width = float(slide["width"])
                height = float(slide["height"])
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ContractError("manifest_invalid") from exc
            if width <= 0 or height <= 0:
                raise ContractError("manifest_invalid")
            return width, height
        if artifact.width <= 0 or artifact.height <= 0:
            raise ContractError("page_size_mismatch")
        ratio = artifact.width / artifact.height
        if abs(ratio / (16 / 9) - 1) <= 0.02:
            return 10.0, 5.625
        return artifact.width / 96, artifact.height / 96

    @staticmethod
    def validate_page_artifact(
        page_pptx: str | Path,
        manifest: str | Path,
        validation: str | Path,
    ) -> dict[str, Any]:
        pptx_path = Path(page_pptx).resolve()
        manifest_path = Path(manifest).resolve()
        validation_path = Path(validation).resolve()
        if not pptx_path.is_file() or not manifest_path.is_file() or not validation_path.is_file():
            raise ContractError("page_validation_failed")
        validator = Path(_vendor_builder.__file__).with_name("validate_pptx.py")
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    str(pptx_path),
                    "--manifest",
                    str(manifest_path),
                ],
                capture_output=True,
                text=True,
                env=environment,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractError("page_validation_failed") from exc
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError("page_validation_failed") from exc
        if (
            completed.returncode != 0
            or not isinstance(report, dict)
            or report.get("passed") is not True
        ):
            raise ContractError("page_validation_failed")
        atomic_write_json(validation_path, report)
        return report

    def status(self) -> dict[str, Any]:
        jobs = self._jobs()
        counts = {name: 0 for name in ("completed", "failed", "active", "pending")}
        for page in jobs["pages"]:
            state = page["status"]
            if state == "recorded":
                counts["completed"] += 1
            elif state in {"failed", "timeout"}:
                counts["failed"] += 1
            elif state == "active":
                counts["active"] += 1
            else:
                counts["pending"] += 1
        if counts["pending"]:
            maximum = load_runtime_config().values["max_concurrent_workers"]
            action = {
                "kind": "request_worker_dispatch",
                "payload": {
                    "dispatch_requirement": "multi_agent_required"
                    if counts["pending"] > 1
                    else "single_unit_current_agent_allowed",
                    "page_count": counts["pending"],
                    "estimated_duration_per_page_seconds": 180,
                    "suggested_max_concurrent": min(maximum, counts["pending"]),
                    "runtime_fallback": False,
                },
            }
            reason = (
                "single_unit_current_agent_allowed"
                if len(jobs["pages"]) == 1
                else "worker_dispatch_required"
            )
        elif counts["active"]:
            action = {"kind": "wait_completion", "payload": {"page_count": counts["active"]}}
            reason = "worker_completion_pending"
        elif counts["failed"]:
            action = {"kind": "reset_failed_pages", "payload": {"page_count": counts["failed"]}}
            reason = "page_recovery_required"
        else:
            action = {"kind": "finalize", "payload": {}}
            reason = "editable_finalize_ready"
        return {
            "status": "ready",
            "reason_code": reason,
            "next_action": action,
            "progress": {"total_units": len(jobs["pages"]), **counts, "estimated_remaining_seconds": None},
            "state_hash": sha256_bytes(canonical_json(jobs).encode()),
            "revision": jobs["revision"],
            "pages": jobs["pages"],
        }

    def dispatch(
        self,
        page_id: str,
        agent_id: str,
        prompt_file: str | Path,
        *,
        lease: str | None = None,
        generation: int | None = None,
    ) -> dict[str, Any]:
        from filelock import FileLock

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", agent_id):
            raise ContractError("invalid_agent_id")
        prompt = Path(prompt_file)
        with FileLock(str(self.run_dir / ".page_jobs.json.lock")):
            jobs = self._jobs()
            try:
                page = next(item for item in jobs["pages"] if item["page_id"] == page_id)
            except StopIteration as exc:
                raise ContractError("unknown_page") from exc
            prompt_sha256 = sha256_file(prompt)
            if page["status"] == "active":
                if page.get("agent_id") == agent_id and page.get("prompt_sha256") == prompt_sha256:
                    return {
                        "idempotency_status": "replayed",
                        "page": page,
                        "state_hash": sha256_bytes(canonical_json(jobs).encode()),
                    }
                raise ContractError("editable_dispatch_conflict")
            if page["status"] != "pending":
                raise ContractError("editable_dispatch_state_conflict")
            worker_dir = self.run_dir / "work" / page_id / agent_id
            worker_dir.mkdir(parents=True, exist_ok=True)
            worker_dir.chmod(0o700)
            durable_copy_file(prompt, worker_dir / "prompt.md", max_bytes=1024 * 1024)
            workflow_root = (
                self.run_dir.parent
                if self.run_dir.name == "editable" and (self.run_dir.parent / "run.json").is_file()
                else self.run_dir
            )
            log_path = workflow_root / "logs" / "workers" / f"{page_id}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.parent.chmod(0o700)
            log_path.touch(mode=0o600, exist_ok=True)
            log_path.chmod(0o600)
            page.update(
                {
                    "status": "active",
                    "agent_id": agent_id,
                    "prompt": str(worker_dir / "prompt.md"),
                    "prompt_sha256": prompt_sha256,
                    "worker_dir": str(worker_dir),
                    "worker_log": str(log_path),
                    "lease": lease,
                    "generation": generation,
                }
            )
            jobs["revision"] += 1
            atomic_write_json(self.jobs_path, jobs)
        return {
            "idempotency_status": "created",
            "page": page,
            "state_hash": sha256_bytes(canonical_json(jobs).encode()),
        }

    def record(
        self,
        page_id: str,
        page_pptx: str | Path,
        validation: str | Path,
        manifest: str | Path,
        *,
        expected_revision: int,
        operation_id: str,
        notes: str = "",
        agent_id: str | None = None,
        expected_state_hash: str | None = None,
        lease: str | None = None,
        generation: int | None = None,
    ) -> PageArtifact:
        self._assert_run_mutable()
        from filelock import FileLock

        with FileLock(str(self.run_dir / ".page_jobs.json.lock")):
            jobs = self._jobs()
            validation_path = Path(validation).resolve()
            report = json.loads(validation_path.read_text(encoding="utf-8"))
            if report.get("passed") is not True:
                raise ContractError("page_validation_failed")
            pptx_path = Path(page_pptx).resolve()
            manifest_path = Path(manifest).resolve()
            try:
                manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ContractError("manifest_invalid") from exc
            if not isinstance(manifest_value, dict):
                raise ContractError("manifest_invalid")
            source_width, source_height = self._manifest_dimensions(manifest_value)
            if not pptx_path.is_file() or len(Presentation(pptx_path).slides) != 1:
                raise ContractError("invalid_editable_page")
            self.validate_page_artifact(pptx_path, manifest_path, validation_path)
            fingerprint = sha256_bytes(
                canonical_json(
                    {
                        "page_id": page_id,
                        "pptx": sha256_file(pptx_path),
                        "validation": sha256_file(validation_path),
                        "manifest": sha256_file(manifest_path),
                        "notes": notes,
                        "agent_id": agent_id,
                        "expected_state_hash": expected_state_hash,
                        "lease": lease,
                        "generation": generation,
                    }
                ).encode()
            )
            operation = jobs["operations"].get(operation_id)
            if operation:
                if operation["fingerprint"] != fingerprint:
                    raise ContractError("idempotency_conflict")
                page = next(item for item in jobs["pages"] if item["page_id"] == page_id)
                return PageArtifact.from_source(
                    page_id,
                    "editable",
                    page["source"],
                    page["artifact"],
                    page["validation"],
                    manifest=page["manifest"],
                    notes=page.get("notes", ""),
                    width=page["width"],
                    height=page["height"],
                )
            if expected_state_hash and sha256_bytes(canonical_json(jobs).encode()) != expected_state_hash:
                raise ContractError("state_hash_conflict")
            if jobs["revision"] != expected_revision:
                raise ContractError("vendor_revision_conflict")
            try:
                page = next(item for item in jobs["pages"] if item["page_id"] == page_id)
            except StopIteration as exc:
                raise ContractError("unknown_page") from exc
            if agent_id and page.get("agent_id") not in {None, agent_id}:
                raise ContractError("editable_agent_conflict")
            if page.get("lease") and page.get("lease") != lease:
                raise ContractError("lease_invalid")
            if page.get("generation") is not None and page.get("generation") != generation:
                raise ContractError("generation_conflict")
            for durable_artifact in (pptx_path, validation_path, manifest_path):
                fsync_file(durable_artifact)
            if sha256_file(page["source"]) != page["source_sha256"]:
                raise ContractError("source_hash_mismatch")
            page.update(
                {
                    "status": "recorded",
                    "artifact": str(pptx_path),
                    "artifact_sha256": sha256_file(pptx_path),
                    "validation": str(validation_path),
                    "validation_sha256": sha256_file(validation_path),
                    "manifest": str(manifest_path),
                    "manifest_sha256": sha256_file(manifest_path),
                    "notes": notes,
                    "width": source_width,
                    "height": source_height,
                    "agent_id": agent_id or page.get("agent_id"),
                    "lease": lease or page.get("lease"),
                    "generation": generation if generation is not None else page.get("generation"),
                }
            )
            jobs["operations"][operation_id] = {
                "fingerprint": fingerprint,
                "status": "completed",
                "page_id": page_id,
                "lease": lease or page.get("lease"),
                "generation": generation if generation is not None else page.get("generation"),
            }
            jobs["revision"] += 1
            atomic_write_json(self.jobs_path, jobs)
        return PageArtifact.from_source(
            page_id,
            "editable",
            page["source"],
            pptx_path,
            validation_path,
            manifest=manifest_path,
            notes=notes,
            width=source_width,
            height=source_height,
        )

    def reset(self, page_id: str, *, confirm_lost: bool = False) -> dict[str, Any]:
        from filelock import FileLock

        with FileLock(str(self.run_dir / ".page_jobs.json.lock")):
            jobs = self._jobs()
            try:
                page = next(item for item in jobs["pages"] if item["page_id"] == page_id)
            except StopIteration as exc:
                raise ContractError("unknown_page") from exc
            if page["status"] == "recorded" and not confirm_lost:
                raise ContractError("reset_confirmation_required")
            preserved = {
                "page_id": page["page_id"],
                "number": page["number"],
                "source": page["source"],
                "source_sha256": page["source_sha256"],
                "notes": page.get("notes", ""),
            }
            page.clear()
            page.update({**preserved, "status": "pending"})
            jobs["revision"] += 1
            jobs.pop("delivery", None)
            atomic_write_json(self.jobs_path, jobs)
        return {"page": page, "state_hash": sha256_bytes(canonical_json(jobs).encode())}

    def finalize(self, output: str | Path) -> dict[str, Any]:
        self._assert_run_mutable()
        lock_root = self.run_dir.parent if (self.run_dir.parent / "run.json").is_file() else self.run_dir
        with FileLock(str(lock_root / ".run-mutation.lock")):
            return self._finalize_locked(output)

    def _finalize_locked(self, output: str | Path) -> dict[str, Any]:
        artifacts = self.artifacts()
        fingerprint = sha256_bytes(
            canonical_json([artifact.manifest_sha256 for artifact in artifacts]).encode()
        )
        jobs = self._jobs()
        existing = jobs.get("delivery")
        if existing:
            existing_path = Path(existing["pptx"])
            if (
                existing.get("fingerprint") == fingerprint
                and existing_path.is_file()
                and sha256_file(existing_path) == existing.get("pptx_sha256")
            ):
                return {**existing, "idempotency_status": "replayed"}
            raise ContractError("editable_finalize_manifest_conflict")
        output_path = self.assemble_page_artifacts(artifacts, output)
        fsync_file(output_path)
        delivery = {
            "delivery_type": "editable",
            "pptx": str(output_path),
            "pptx_sha256": sha256_file(output_path),
            "fingerprint": fingerprint,
            "page_count": len(artifacts),
            "pages": [
                {
                    "page_id": artifact.page_id,
                    "source_ref": artifact.source_path,
                    "source_sha256": artifact.source_sha256,
                    "artifact_ref": artifact.artifact_path,
                    "artifact_sha256": artifact.artifact_sha256,
                    "manifest_ref": artifact.manifest_path,
                    "manifest_sha256": artifact.manifest_sha256,
                    "validation_ref": artifact.validation_path,
                    "validation_sha256": artifact.validation_sha256,
                    "notes": artifact.notes,
                }
                for artifact in artifacts
            ],
        }
        jobs["delivery"] = delivery
        jobs["run_status"] = "completed"
        jobs["revision"] += 1
        atomic_write_json(self.jobs_path, jobs)
        return {**delivery, "idempotency_status": "created"}

    @staticmethod
    def build_page_from_manifest(manifest: str | Path, output: str | Path) -> Path:
        manifest_path = Path(manifest).resolve()
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _vendor_builder.write_pptx(manifest_value, output_path, manifest_path)
        return output_path

    @staticmethod
    def assemble_page_artifacts(artifacts: list[PageArtifact], output: str | Path) -> Path:
        if not artifacts:
            raise ContractError("empty_deck")
        slide_sizes = [EditableAdapter.slide_size_for_artifact(artifact) for artifact in artifacts]
        slide_width, slide_height = slide_sizes[0]
        if any(
            abs(width - slide_width) > 1e-6 or abs(height - slide_height) > 1e-6
            for width, height in slide_sizes[1:]
        ):
            raise ContractError("page_size_mismatch")
        entries = []
        notes = []
        for number, artifact in enumerate(artifacts, 1):
            if artifact.mode == "editable":
                manifest_path = Path(artifact.manifest_path or "")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                manifest_path = Path(artifact.source_path)
                manifest = {
                    "slide": {"width": slide_width, "height": slide_height},
                    "source": {"width": artifact.width, "height": artifact.height},
                    "images": [
                        {
                            "path": artifact.source_path,
                            "left": 0,
                            "top": 0,
                            "width": slide_width,
                            "height": slide_height,
                        }
                    ],
                }
            entries.append({"manifest": manifest, "manifest_path": manifest_path})
            if artifact.notes:
                notes.append({"page_index": number, "text": artifact.notes})
        output_path = Path(output).resolve()

        def build(destination: Path) -> None:
            _vendor_builder.write_deck(
                {"slide": {"width": slide_width, "height": slide_height}},
                entries,
                destination,
                notes,
            )

        return atomic_materialize(output_path, build)

    def artifacts(self, *, allow_incomplete: bool = False) -> list[PageArtifact]:
        jobs = self._jobs()
        result = []
        for page in jobs["pages"]:
            if page["status"] != "recorded":
                if allow_incomplete:
                    continue
                raise ContractError("missing_page_artifact")
            artifact = PageArtifact(
                schema_version=1,
                page_id=page["page_id"],
                mode="editable",
                source_path=page["source"],
                source_sha256=page["source_sha256"],
                artifact_path=page["artifact"],
                artifact_sha256=page["artifact_sha256"],
                validation_path=page["validation"],
                validation_sha256=page.get("validation_sha256"),
                manifest_path=page["manifest"],
                manifest_sha256=page["manifest_sha256"],
                notes=page.get("notes", ""),
                width=page.get("width", 1600),
                height=page.get("height", 900),
            )
            artifact.verify()
            result.append(artifact)
        return result
