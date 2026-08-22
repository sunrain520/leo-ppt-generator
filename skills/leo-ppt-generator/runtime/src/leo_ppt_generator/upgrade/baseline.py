"""冻结已完成 image delivery，供 upgrade routes 作为唯一输入基线。"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from ..contracts import ContractError
from ..image_deck.adapter import ImageDeckAdapter
from ..storage import (
    atomic_write_json,
    canonical_json,
    durable_copy_file,
    fsync_file,
    sha256_file,
)


class BaselineError(ContractError):
    reason_code = "upgrade_baseline_error"


def load_baseline(run_dir: str | Path) -> dict:
    """读取并重新验证不可变 baseline；任何内容漂移都 fail closed。"""
    root = Path(run_dir).resolve()
    manifest_path = root / "image-baseline" / "baseline.json"
    if not manifest_path.is_file():
        raise BaselineError("upgrade_baseline_required")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages = value["pages"]
        delivery = value["delivery"]
        expected_fingerprint = value.get("manifest_fingerprint", value["baseline_fingerprint"])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise BaselineError("upgrade_baseline_manifest_invalid") from exc
    if not isinstance(pages, list) or not pages:
        raise BaselineError("upgrade_baseline_manifest_invalid")
    for page in pages:
        try:
            artifact = Path(page["artifact"])
            if not artifact.is_file() or sha256_file(artifact) != page["artifact_sha256"]:
                raise BaselineError("upgrade_baseline_artifact_changed")
            notes = str(page.get("notes", ""))
            if hashlib.sha256(notes.encode("utf-8")).hexdigest() != page.get("notes_sha256"):
                raise BaselineError("upgrade_baseline_notes_changed")
            if int(page["width"]) <= 0 or int(page["height"]) <= 0:
                raise BaselineError("upgrade_baseline_manifest_invalid")
        except BaselineError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise BaselineError("upgrade_baseline_manifest_invalid") from exc
    delivery_path = Path(delivery.get("pptx", ""))
    if not delivery_path.is_file() or sha256_file(delivery_path) != delivery.get("pptx_sha256"):
        raise BaselineError("upgrade_baseline_delivery_changed")
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"baseline_fingerprint", "manifest_fingerprint"}
    }
    fingerprint = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    if fingerprint != expected_fingerprint:
        raise BaselineError("upgrade_baseline_manifest_changed")
    return value


def inspect_image_delivery(run_dir: str | Path) -> dict:
    root = Path(run_dir).resolve()
    run_path = root / "run.json"
    if not run_path.is_file():
        raise BaselineError("upgrade_baseline_source_missing")
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
        artifacts = ImageDeckAdapter(root / "image-deck").artifacts()
        jobs = json.loads((root / "image-deck" / "slide_jobs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        raise BaselineError("upgrade_baseline_source_invalid") from exc
    delivery = jobs.get("delivery")
    if not isinstance(delivery, dict) or not Path(delivery.get("pptx", "")).is_file():
        raise BaselineError("upgrade_baseline_delivery_missing")
    pptx = Path(delivery["pptx"]).resolve()
    if sha256_file(pptx) != delivery.get("sha256"):
        raise BaselineError("upgrade_baseline_delivery_hash_mismatch")
    pages = [
        {
            "page_id": artifact.page_id,
            "number": index,
            "source": artifact.source_path,
            "source_sha256": artifact.source_sha256,
            "artifact": artifact.artifact_path,
            "artifact_sha256": artifact.artifact_sha256,
            "notes": artifact.notes,
            "notes_sha256": hashlib.sha256(artifact.notes.encode("utf-8")).hexdigest(),
            "width": artifact.width,
            "height": artifact.height,
        }
        for index, artifact in enumerate(artifacts, 1)
    ]
    payload = {
        "schema_version": 1,
        "source_run_id": run.get("run_id"),
        "source_route": run.get("route"),
        "page_count": len(pages),
        "pages": pages,
        "delivery": {
            "pptx": str(pptx),
            "pptx_sha256": sha256_file(pptx),
            "artifact_fingerprint": delivery.get("artifact_fingerprint"),
        },
    }
    payload["baseline_fingerprint"] = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return payload


def import_baseline(source_run: str | Path, target_run: str | Path) -> dict:
    source = inspect_image_delivery(source_run)
    target = Path(target_run).resolve()
    baseline_dir = target / "image-baseline"
    manifest_path = baseline_dir / "baseline.json"
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BaselineError("upgrade_baseline_manifest_invalid") from exc
        if existing.get("source_fingerprint", existing.get("baseline_fingerprint")) == source["baseline_fingerprint"]:
            return {**existing, "idempotency_status": "replayed"}
        raise BaselineError("upgrade_baseline_conflict")
    if source.get("source_route") != "generate":
        raise BaselineError("upgrade_baseline_route_mismatch")
    pages_dir = baseline_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    copied_pages = []
    for page in source["pages"]:
        source_path = Path(page["artifact"])
        destination = pages_dir / f"{page['page_id']}{source_path.suffix.lower()}"
        copied = durable_copy_file(source_path, destination, max_bytes=100 * 1024 * 1024)
        if copied["sha256"] != page["artifact_sha256"]:
            raise BaselineError("upgrade_baseline_artifact_changed")
        copied_page = {**page, "artifact": str(destination), "artifact_sha256": copied["sha256"]}
        copied_pages.append(copied_page)
    delivery_source = Path(source["delivery"]["pptx"])
    copied_delivery = durable_copy_file(
        delivery_source, baseline_dir / "image-delivery.pptx", max_bytes=100 * 1024 * 1024
    )
    if copied_delivery["sha256"] != source["delivery"]["pptx_sha256"]:
        raise BaselineError("upgrade_baseline_delivery_changed")
    manifest = {
        **source,
        "baseline_id": uuid.uuid4().hex,
        "source_run_path": str(Path(source_run).resolve()),
        "source_fingerprint": source["baseline_fingerprint"],
        "pages": copied_pages,
        "delivery": {**source["delivery"], "pptx": str(baseline_dir / "image-delivery.pptx")},
    }
    manifest_fingerprint = hashlib.sha256(
        canonical_json(
            {key: item for key, item in manifest.items() if key != "baseline_fingerprint"}
        ).encode("utf-8")
    ).hexdigest()
    # baseline_fingerprint 保持源 delivery 身份，manifest_fingerprint 绑定
    # target 内复制后的不可变路径与内容，兼容 inspect/import 的稳定 API。
    manifest["manifest_fingerprint"] = manifest_fingerprint
    manifest["baseline_fingerprint"] = source["baseline_fingerprint"]
    atomic_write_json(manifest_path, manifest)
    fsync_file(manifest_path)
    return {**manifest, "idempotency_status": "created"}
