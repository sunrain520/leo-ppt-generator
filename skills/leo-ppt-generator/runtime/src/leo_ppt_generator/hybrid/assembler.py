"""不读取 vendor 私有状态地组装 image/editable 页面。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from filelock import FileLock
from pptx import Presentation

from ..contracts import ContractError, PageArtifact
from ..editable.adapter import EditableAdapter
from ..storage import atomic_write_json, canonical_json, fsync_file, sha256_file


class HybridAssembler:
    @staticmethod
    def baseline_fingerprint(artifacts: list[PageArtifact]) -> str:
        return hashlib.sha256(
            canonical_json(
                [
                    {
                        "page_id": item.page_id,
                        "source_sha256": item.source_sha256,
                        "artifact_sha256": item.artifact_sha256,
                        "validation_sha256": item.validation_sha256,
                        "manifest_sha256": item.manifest_sha256,
                        "notes": item.notes,
                        "width": item.width,
                        "height": item.height,
                    }
                    for item in artifacts
                ]
            ).encode()
        ).hexdigest()

    @staticmethod
    def failure_fingerprint(
        failures: dict[int, str],
        *,
        selected_pages: set[int] | None = None,
        baseline_fingerprint: str | None = None,
    ) -> str:
        normalized = {
            "failures": {str(key): value for key, value in sorted(failures.items())},
            "selected_pages": sorted(selected_pages or failures),
            "baseline_fingerprint": baseline_fingerprint,
        }
        return hashlib.sha256(canonical_json(normalized).encode()).hexdigest()

    def assemble(
        self,
        artifacts: list[PageArtifact],
        output: str | Path,
        *,
        selected_pages: set[int] | None = None,
        failures: dict[int, str] | None = None,
        partial_confirmation: str | None = None,
    ) -> dict:
        requested_output = Path(output).resolve()
        lock_root = requested_output.parent
        run_root = requested_output.parent.parent if (requested_output.parent.parent / "run.json").is_file() else lock_root
        with FileLock(str(run_root / ".run-mutation.lock")):
            return self._assemble_locked(
                artifacts,
                output,
                selected_pages=selected_pages,
                failures=failures,
                partial_confirmation=partial_confirmation,
            )

    def _assemble_locked(
        self,
        artifacts: list[PageArtifact],
        output: str | Path,
        *,
        selected_pages: set[int] | None = None,
        failures: dict[int, str] | None = None,
        partial_confirmation: str | None = None,
    ) -> dict:
        output_root = Path(output).resolve().parent
        run_root = output_root.parent if (output_root.parent / "run.json").is_file() else None
        if run_root is not None:
            try:
                status = json.loads((run_root / "run.json").read_text(encoding="utf-8")).get("status")
            except (OSError, ValueError, TypeError) as exc:
                raise ContractError("run_index_invalid") from exc
            if status == "cancelled":
                raise ContractError("run_cancelled_mutation_forbidden")
        if not artifacts:
            raise ContractError("empty_deck")
        failures = failures or {}
        selected_pages = selected_pages or set(range(1, len(artifacts) + 1))
        if any(number < 1 or number > len(artifacts) for number in selected_pages):
            raise ContractError("selection_out_of_range")
        if not set(failures).issubset(selected_pages):
            raise ContractError("failure_set_mismatch")
        if len(selected_pages) > 50:
            raise ContractError("input_too_large")
        expected_ids = [f"page_{number:03d}" for number in range(1, len(artifacts) + 1)]
        if [item.page_id for item in artifacts] != expected_ids:
            raise ContractError("page_order_mismatch")
        baseline_fingerprint = self.baseline_fingerprint(artifacts)
        if failures and partial_confirmation != self.failure_fingerprint(
            failures,
            selected_pages=selected_pages,
            baseline_fingerprint=baseline_fingerprint,
        ):
            raise ContractError("partial_hybrid_confirmation_required")
        request_fingerprint = hashlib.sha256(
            canonical_json(
                {
                    "baseline_fingerprint": baseline_fingerprint,
                    "artifacts": [
                        {
                            "page_id": item.page_id,
                            "source_sha256": item.source_sha256,
                            "artifact_sha256": item.artifact_sha256,
                            "validation_sha256": item.validation_sha256,
                            "manifest_sha256": item.manifest_sha256,
                            "notes": item.notes,
                            "width": item.width,
                            "height": item.height,
                        }
                        for item in artifacts
                    ],
                    "selected_pages": sorted(selected_pages),
                    "failures": {str(key): value for key, value in sorted(failures.items())},
                }
            ).encode()
        ).hexdigest()
        requested_output = Path(output).resolve()
        revision = 1
        existing_manifests = sorted(
            requested_output.parent.glob(f"{requested_output.stem}*.delivery.json")
        )
        latest_revision = 0
        for existing_manifest_path in existing_manifests:
            try:
                existing = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractError("delivery_manifest_invalid") from exc
            latest_revision = max(latest_revision, int(existing.get("artifact_revision", 1)))
            existing_pptx = Path(existing.get("pptx", ""))
            if (
                existing.get("request_fingerprint") == request_fingerprint
                and existing_pptx.is_file()
                and sha256_file(existing_pptx) == existing.get("pptx_sha256")
            ):
                return {**existing, "idempotency_status": "replayed"}
        if existing_manifests:
            revision = latest_revision + 1
            output = requested_output.with_name(
                f"{requested_output.stem}.r{revision}{requested_output.suffix}"
            )
        manifest_pages = []
        delivery_artifacts = []
        expected_slide_size: tuple[float, float] | None = None
        for number, artifact in enumerate(artifacts, 1):
            current_artifact = artifact
            requested_editable = number in selected_pages and number not in failures
            try:
                artifact.verify()
            except ContractError as exc:
                # The editable validator may legitimately refresh its canonical
                # report; source/artifact/manifest drift must still fail before
                # that refresh is attempted.
                if not (requested_editable and str(exc) == "validation_hash_mismatch"):
                    raise
            slide_size = EditableAdapter.slide_size_for_artifact(artifact)
            if expected_slide_size is None:
                expected_slide_size = slide_size
            elif any(abs(left - right) > 1e-6 for left, right in zip(slide_size, expected_slide_size)):
                raise ContractError("page_size_mismatch")
            if requested_editable and artifact.mode != "editable":
                raise ContractError("selected_page_not_editable")
            if requested_editable:
                validation = EditableAdapter.validate_page_artifact(
                    artifact.artifact_path,
                    artifact.manifest_path or "",
                    artifact.validation_path or "",
                )
                if validation.get("passed") is not True:
                    raise ContractError("page_validation_failed")
                # The independent validator writes its canonical report. Rebind
                # the artifact identity to that report before verification so a
                # legitimate validator refresh is not mistaken for tampering.
                current_artifact = PageArtifact.from_source(
                    artifact.page_id,
                    artifact.mode,
                    artifact.source_path,
                    artifact.artifact_path,
                    artifact.validation_path,
                    manifest=artifact.manifest_path,
                    notes=artifact.notes,
                    width=artifact.width,
                    height=artifact.height,
                )
            current_artifact.verify()
            mode = "editable" if requested_editable else "image"
            if mode == "editable":
                delivery_artifacts.append(current_artifact)
            else:
                delivery_artifacts.append(
                    PageArtifact.from_source(
                        current_artifact.page_id,
                        "image",
                        current_artifact.source_path,
                        current_artifact.source_path,
                        None,
                        notes=current_artifact.notes,
                        width=current_artifact.width,
                        height=current_artifact.height,
                    )
                )
            manifest_pages.append(
                {
                    "page_id": artifact.page_id,
                    "mode": mode,
                    "source_sha256": current_artifact.source_sha256,
                    "validation_ref": current_artifact.validation_path,
                }
            )
        output_path = Path(output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        EditableAdapter.assemble_page_artifacts(delivery_artifacts, output_path)
        fsync_file(output_path)
        if len(Presentation(output_path).slides) != len(artifacts):
            raise ContractError("page_count_mismatch")
        delivery_type = "partial-hybrid" if failures else ("editable" if all(item["mode"] == "editable" for item in manifest_pages) else "hybrid")
        manifest = {
            "schema_version": 1,
            "delivery_type": delivery_type,
            "pptx": str(output_path),
            "pptx_sha256": sha256_file(output_path),
            "pages": manifest_pages,
            "failures": {str(key): value for key, value in sorted(failures.items())},
            "request_fingerprint": request_fingerprint,
            "baseline_fingerprint": baseline_fingerprint,
            "artifact_revision": revision,
        }
        atomic_write_json(output_path.with_suffix(".delivery.json"), manifest)
        return {**manifest, "idempotency_status": "created"}
