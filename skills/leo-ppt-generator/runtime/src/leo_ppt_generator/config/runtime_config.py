"""版本化非敏感 runtime 配置与来源追踪。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RuntimeConfigError(ValueError):
    reason_code = "config_invalid"


DEFAULTS: dict[str, Any] = {
    "max_concurrent_workers": min(max((os.cpu_count() or 2) // 2, 1), 4),
    "max_run_bytes": 10 * 1024**3,
    "timeouts": {
        "worker_page_seconds": 600,
        "backend_api_seconds": 60,
        "backend_api_retries": 3,
    },
}


@dataclass(frozen=True)
class RuntimeConfig:
    values: dict[str, Any]
    sources: dict[str, str]
    warnings: tuple[str, ...]
    path: Path


def default_home() -> Path:
    override = os.environ.get("LEO_PPT_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library/Application Support/leo-ppt-generator").resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return (base / "leo-ppt-generator").resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return (base / "leo-ppt-generator").resolve()


def _integer(value: Any, *, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RuntimeConfigError(f"config_invalid:{field}")
    return value


def load_runtime_config() -> RuntimeConfig:
    home = default_home()
    path = home / "config.yaml"
    raw: dict[str, Any] = {}
    warnings: list[str] = []
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise RuntimeConfigError("config_invalid") from exc
        if not isinstance(loaded, dict):
            raise RuntimeConfigError("config_invalid")
        raw = loaded
        version = raw.get("schema_version")
        if version != 1:
            reason = "config_schema_too_new" if isinstance(version, int) and version > 1 else "config_invalid"
            raise RuntimeConfigError(reason)
        allowed = {"schema_version", "max_concurrent_workers", "max_run_bytes", "timeouts"}
        for key in raw:
            if key in allowed:
                continue
            if any(marker in key.lower() for marker in ("token", "secret", "password", "key")):
                raise RuntimeConfigError("unknown_sensitive_field")
            warnings.append(f"unknown_optional_config:{key}")

    values = {**DEFAULTS, "timeouts": dict(DEFAULTS["timeouts"])}
    sources = {key: "default" for key in values}
    if "max_concurrent_workers" in raw:
        values["max_concurrent_workers"] = _integer(
            raw["max_concurrent_workers"], minimum=1, maximum=16, field="max_concurrent_workers"
        )
        sources["max_concurrent_workers"] = "config.yaml"
    if "max_run_bytes" in raw:
        values["max_run_bytes"] = _integer(
            raw["max_run_bytes"], minimum=1024**2, maximum=100 * 1024**3, field="max_run_bytes"
        )
        sources["max_run_bytes"] = "config.yaml"
    if "timeouts" in raw:
        timeouts = raw["timeouts"]
        if not isinstance(timeouts, dict) or set(timeouts) - set(values["timeouts"]):
            raise RuntimeConfigError("config_invalid:timeouts")
        limits = {
            "worker_page_seconds": (1, 86400),
            "backend_api_seconds": (1, 3600),
            "backend_api_retries": (0, 10),
        }
        for key, value in timeouts.items():
            values["timeouts"][key] = _integer(value, minimum=limits[key][0], maximum=limits[key][1], field=f"timeouts.{key}")
        sources["timeouts"] = "config.yaml"
    if "LEO_PPT_MAX_WORKERS" in os.environ:
        try:
            workers = int(os.environ["LEO_PPT_MAX_WORKERS"])
        except ValueError as exc:
            raise RuntimeConfigError("config_invalid:max_concurrent_workers") from exc
        values["max_concurrent_workers"] = _integer(
            workers, minimum=1, maximum=16, field="max_concurrent_workers"
        )
        sources["max_concurrent_workers"] = "environment"
    return RuntimeConfig(values, sources, tuple(warnings), path)


def run_size_bytes(run_dir: Path) -> int:
    return sum(
        path.stat().st_size
        for path in run_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def assert_run_quota(run_dir: Path, config: RuntimeConfig) -> None:
    if run_size_bytes(run_dir) > config.values["max_run_bytes"]:
        raise RuntimeConfigError("disk_quota_exceeded")
