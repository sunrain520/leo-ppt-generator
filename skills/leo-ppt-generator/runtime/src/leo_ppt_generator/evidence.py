"""独立 provider、视觉与人工验收证据。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from filelock import FileLock

from .storage import atomic_write_json, canonical_json, sha256_file


class EvidenceError(ValueError):
    reason_code = "evidence_error"


_SENSITIVE = re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|authorization|bearer|secret)")


def _load(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("evidence_receipt_invalid") from exc
    if not isinstance(value, dict):
        raise EvidenceError("evidence_receipt_invalid")
    if _SENSITIVE.search(canonical_json(value)):
        raise EvidenceError("evidence_sensitive_content_forbidden")
    return value


def _run(run_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(run_dir).resolve()
    try:
        value = json.loads((root / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("run_index_invalid") from exc
    return root, value


def _final_identity(root: Path) -> tuple[Path, dict[str, Any]]:
    summary = root / "final/validation-summary.json"
    try:
        value = json.loads(summary.read_text(encoding="utf-8"))
        pptx = Path(value["pptx"]).resolve()
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise EvidenceError("delivery_summary_required") from exc
    if not pptx.is_file() or sha256_file(pptx) != value.get("pptx_sha256"):
        raise EvidenceError("delivery_identity_mismatch")
    return summary, value


def _write(root: Path, name: str, receipt: dict[str, Any]) -> dict[str, Any]:
    target = root / "reports" / name
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(root / ".evidence.lock")):
        if target.is_file():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if canonical_json(existing) == canonical_json(receipt):
                return {"path": str(target), "sha256": sha256_file(target), "idempotency_status": "replayed"}
            raise EvidenceError("evidence_conflict")
        atomic_write_json(target, receipt)
    return {"path": str(target), "sha256": sha256_file(target), "idempotency_status": "created"}


def record_provenance(run_dir: str | Path, receipt_path: str | Path) -> dict[str, Any]:
    root, run = _run(run_dir)
    value = _load(receipt_path)
    required = {"page_id", "provider", "model", "prompt_sha256", "input_sha256", "artifact_sha256"}
    if not required.issubset(value) or value.get("schema_version") != 1:
        raise EvidenceError("provenance_receipt_invalid")
    if not all(isinstance(value[key], str) and value[key] for key in required):
        raise EvidenceError("provenance_receipt_invalid")
    page_id = value["page_id"]
    if not re.fullmatch(r"(?:page_\d{3}|slide_\d{2,3})", page_id):
        raise EvidenceError("provenance_receipt_invalid")
    candidates = []
    for state_path, collection in (
        (root / "image-deck/slide_jobs.json", "slides"),
        (root / "editable/page_jobs.json", "pages"),
    ):
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            candidates.extend(state.get(collection, []))
    match = next(
        (
            item
            for item in candidates
            if item.get("page_id") == page_id or item.get("slide_id") == page_id
        ),
        None,
    )
    recorded_digest = (
        match.get("sha256") or match.get("artifact_sha256")
        if isinstance(match, dict)
        else None
    )
    if not isinstance(match, dict) or recorded_digest != value["artifact_sha256"]:
        if isinstance(match, dict) and match.get("artifact"):
            artifact = Path(match["artifact"])
            if not artifact.is_absolute():
                domain = "image-deck" if match.get("slide_id") else "editable"
                artifact = root / domain / artifact
            if artifact.is_file() and sha256_file(artifact) == value["artifact_sha256"]:
                pass
            else:
                raise EvidenceError("provenance_artifact_mismatch")
        else:
            raise EvidenceError("provenance_artifact_mismatch")
    receipt = {**value, "run_id": run["run_id"], "kind": "provider_provenance"}
    return _write(root, f"provenance-{value['page_id']}.json", receipt)


def _update_gate(root: Path, gate: str, receipt: dict[str, Any]) -> None:
    summary_path, summary = _final_identity(root)
    summary["quality_gates"][gate] = {
        "status": "passed",
        "receipt": receipt["path"],
        "receipt_sha256": receipt["sha256"],
    }
    atomic_write_json(summary_path, summary)


def record_visual(run_dir: str | Path, receipt_path: str | Path) -> dict[str, Any]:
    root, run = _run(run_dir)
    _summary_path, summary = _final_identity(root)
    value = _load(receipt_path)
    pages = value.get("pages")
    required = {"renderer", "renderer_version", "pptx_sha256", "pages"}
    if value.get("schema_version") != 1 or not required.issubset(value):
        raise EvidenceError("visual_receipt_invalid")
    if value["pptx_sha256"] != summary["pptx_sha256"]:
        raise EvidenceError("delivery_identity_mismatch")
    if not isinstance(pages, list) or [page.get("page") for page in pages if isinstance(page, dict)] != list(range(1, summary["page_count"] + 1)) or any(
        not isinstance(page, dict)
        or page.get("status") != "passed"
        or not Path(page.get("render_path", "")).is_file()
        or not isinstance(page.get("render_sha256"), str)
        or sha256_file(page["render_path"]) != page["render_sha256"]
        for page in pages
    ):
        raise EvidenceError("visual_receipt_invalid")
    receipt = {**value, "run_id": run["run_id"], "kind": "independent_visual_render"}
    result = _write(root, "visual-render.json", receipt)
    _update_gate(root, "visual_render", result)
    return result


def record_acceptance(run_dir: str | Path, receipt_path: str | Path) -> dict[str, Any]:
    root, run = _run(run_dir)
    _summary_path, summary = _final_identity(root)
    value = _load(receipt_path)
    pages = value.get("pages")
    required = {"reviewer", "client", "client_version", "pptx_sha256", "pages"}
    if value.get("schema_version") != 1 or not required.issubset(value):
        raise EvidenceError("acceptance_receipt_invalid")
    if value["pptx_sha256"] != summary["pptx_sha256"]:
        raise EvidenceError("delivery_identity_mismatch")
    if not isinstance(pages, list) or [page.get("page") for page in pages if isinstance(page, dict)] != list(range(1, summary["page_count"] + 1)) or any(
        not isinstance(page, dict) or page.get("decision") != "accepted" for page in pages
    ):
        raise EvidenceError("acceptance_receipt_invalid")
    receipt = {**value, "run_id": run["run_id"], "kind": "manual_visual_acceptance"}
    result = _write(root, "manual-acceptance.json", receipt)
    _update_gate(root, "manual_visual_acceptance", result)
    return result
