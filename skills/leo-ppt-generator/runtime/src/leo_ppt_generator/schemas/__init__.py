"""机器协议 schema 的只读加载器。

提供对 ``schemas/*.json`` 的确定性加载，供 CLI、验证与测试共同消费。
Schema 文件随 runtime 包发布（见 pyproject package-data）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


class SchemaNotFound(LookupError):
    reason_code = "schema_not_found"


def _schema_path(name: str) -> str:
    if not name.endswith(".json"):
        name = f"{name}.json"
    if "/" in name or ".." in name:
        raise SchemaNotFound(name)
    return name


@lru_cache(maxsize=64)
def load_schema(name: str) -> dict[str, Any]:
    """按文件名加载 JSON schema；文件缺失返回 SchemaNotFound。"""

    try:
        text = resources.files("leo_ppt_generator.schemas").joinpath(
            _schema_path(name)
        ).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise SchemaNotFound(name) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaNotFound(f"{name}:invalid") from exc


__all__ = ["SchemaNotFound", "load_schema"]
