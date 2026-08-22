"""稳定的跨能力合同。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .storage import sha256_file


class ContractError(ValueError):
    reason_code = "contract_error"


@dataclass(frozen=True)
class PageArtifact:
    schema_version: int
    page_id: str
    mode: str
    source_path: str
    source_sha256: str
    artifact_path: str
    artifact_sha256: str
    validation_path: str | None
    validation_sha256: str | None = None
    manifest_path: str | None = None
    manifest_sha256: str | None = None
    notes: str = ""
    width: int = 1600
    height: int = 900

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ContractError("unknown_contract_version")
        if self.mode not in {"image", "editable"}:
            raise ContractError("unknown_page_mode")
        if not self.page_id.startswith("page_"):
            raise ContractError("invalid_page_id")

    @classmethod
    def from_source(
        cls,
        page_id: str,
        mode: str,
        source: str | Path,
        artifact: str | Path,
        validation: str | Path | None,
        *,
        manifest: str | Path | None = None,
        notes: str = "",
        width: int | None = None,
        height: int | None = None,
    ) -> PageArtifact:
        source_path = Path(source).resolve()
        artifact_path = Path(artifact).resolve()
        if width is None or height is None:
            try:
                with Image.open(source_path) as image:
                    width, height = image.size
            except (OSError, ValueError):
                width, height = 1600, 900
        return cls(
            schema_version=1,
            page_id=page_id,
            mode=mode,
            source_path=str(source_path),
            source_sha256=sha256_file(source_path),
            artifact_path=str(artifact_path),
            artifact_sha256=sha256_file(artifact_path),
            validation_path=str(Path(validation).resolve()) if validation else None,
            validation_sha256=sha256_file(validation) if validation else None,
            manifest_path=str(Path(manifest).resolve()) if manifest else None,
            manifest_sha256=sha256_file(manifest) if manifest else None,
            notes=notes,
            width=int(width),
            height=int(height),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PageArtifact:
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify(self) -> None:
        source = Path(self.source_path)
        artifact = Path(self.artifact_path)
        if not source.is_file() or sha256_file(source) != self.source_sha256:
            raise ContractError("source_hash_mismatch")
        if not artifact.is_file() or sha256_file(artifact) != self.artifact_sha256:
            raise ContractError("artifact_hash_mismatch")
        if self.validation_path:
            validation = Path(self.validation_path)
            if not validation.is_file():
                raise ContractError("validation_missing")
            if self.validation_sha256 and sha256_file(validation) != self.validation_sha256:
                raise ContractError("validation_hash_mismatch")
        if self.mode == "editable":
            if not self.validation_path:
                raise ContractError("validation_missing")
            if not self.manifest_path or not self.manifest_sha256:
                raise ContractError("manifest_missing")
            manifest = Path(self.manifest_path)
            if not manifest.is_file() or sha256_file(manifest) != self.manifest_sha256:
                raise ContractError("manifest_hash_mismatch")
