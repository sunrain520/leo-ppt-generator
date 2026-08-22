"""四条由代码拥有的有限产品 route。"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

from ..config.models import Capability, RouteName


class RouteContractError(ValueError):
    reason_code = "route_contract_error"


DEFAULT_ROUTE = RouteName.GENERATE
TASK_CAPABILITIES = frozenset({Capability.MASK, Capability.REFERENCE})


@dataclass(frozen=True)
class RouteDefinition:
    name: str
    steps: tuple[str, ...]
    terminal_delivery: str
    base_capabilities: frozenset[Capability]

    def require_step(self, step: str) -> str:
        if step not in self.steps:
            raise RouteContractError("unknown_step")
        return step

    def required_capabilities(
        self,
        task_capabilities: Iterable[Capability | str] = (),
    ) -> frozenset[Capability]:
        """合并 Route 基础能力与任务实际使用的附加图片能力。"""

        try:
            normalized = frozenset(Capability(value) for value in task_capabilities)
        except (TypeError, ValueError) as exc:
            raise RouteContractError("task_capability_invalid") from exc
        if not normalized.issubset(TASK_CAPABILITIES):
            raise RouteContractError("task_capability_invalid")
        return self.base_capabilities | normalized


ROUTES = {
    "generate": RouteDefinition(
        "generate",
        ("image.prepare", "image.dispatch", "image.finalize"),
        "image",
        frozenset({Capability.GENERATE}),
    ),
    "direct-editable": RouteDefinition(
        "direct-editable",
        ("editable.prepare", "editable.dispatch", "editable.finalize"),
        "editable",
        frozenset({Capability.EDIT}),
    ),
    "upgrade-full": RouteDefinition(
        "upgrade-full",
        ("image.inspect", "editable.prepare", "editable.dispatch", "editable.finalize"),
        "editable",
        frozenset({Capability.EDIT}),
    ),
    "upgrade-selected": RouteDefinition(
        "upgrade-selected",
        ("image.inspect", "editable.prepare-selected", "editable.dispatch", "hybrid.assemble"),
        "hybrid",
        frozenset({Capability.EDIT}),
    ),
}


class RouteCapabilityResolver:
    """Route required-capabilities 的唯一解析入口。"""

    def resolve(
        self,
        route: RouteName | str | None = None,
        task_capabilities: Iterable[Capability | str] = (),
    ) -> frozenset[Capability]:
        selected_route = DEFAULT_ROUTE.value if route is None else str(route)
        return route_definition(selected_route).required_capabilities(task_capabilities)


ROUTE_CAPABILITY_RESOLVER = RouteCapabilityResolver()


def route_definition(name: str) -> RouteDefinition:
    try:
        return ROUTES[name]
    except KeyError as exc:
        raise RouteContractError("unknown_route") from exc


def select_route(kind: str, *, editable: bool, upgrade: bool, selected_pages=()) -> str:
    if kind == "content" and not upgrade:
        return "generate"
    if kind in {"image", "pdf", "office"} and editable and not upgrade:
        return "direct-editable"
    if kind == "image-deck" and editable and upgrade:
        return "upgrade-selected" if tuple(selected_pages) else "upgrade-full"
    raise RouteContractError("route_confirmation_required")


def _office_safe(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            lowered_names = {name.lower() for name in names}
            if any("vbaproject" in name or "/embeddings/" in name for name in lowered_names):
                return False
            for name in names:
                if name.lower().endswith(".rels"):
                    body = archive.read(name).decode("utf-8", errors="replace").lower()
                    if "targetmode=\"external\"" in body or "targetmode='external'" in body:
                        return False
    except (OSError, zipfile.BadZipFile):
        return False
    return True


def classify_input(path: str | Path, *, office_trusted: bool = False) -> str:
    value = Path(path)
    suffix = value.suffix.lower()
    if suffix in {".md", ".txt"}:
        return "content"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".ppt", ".pptx"}:
        if not office_trusted or suffix == ".ppt" or not _office_safe(value):
            raise RouteContractError("untrusted_office_input")
        return "office"
    raise RouteContractError("unsupported_input")


def validate_input_content(path: str | Path, kind: str) -> None:
    """确认扩展名声明与最小解析签名一致。"""
    value = Path(path)
    try:
        if kind == "content":
            text = value.read_text(encoding="utf-8")
            if "\x00" in text:
                raise RouteContractError("input_type_mismatch")
        elif kind == "image":
            with Image.open(value) as image:
                image.verify()
        elif kind == "pdf":
            with value.open("rb") as handle:
                header = handle.read(8)
            if not header.startswith(b"%PDF-"):
                raise RouteContractError("input_type_mismatch")
        elif kind == "office":
            with zipfile.ZipFile(value) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                    raise RouteContractError("input_type_mismatch")
    except RouteContractError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, zipfile.BadZipFile) as exc:
        raise RouteContractError("input_type_mismatch") from exc
