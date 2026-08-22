"""正式 schema v1 的非敏感 runtime 配置、来源追踪与原子存储。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit

import yaml
from filelock import FileLock
from yaml.constructor import ConstructorError


SCHEMA_VERSION = 1
EXTERNAL_PROVIDERS = ("openai", "openai-compatible", "atlascloud")
ENVIRONMENT_REFERENCES = {
    "openai": "env:OPENAI_API_KEY",
    "openai-compatible": "env:OPENAI_COMPATIBLE_API_KEY",
    "atlascloud": "env:ATLASCLOUD_API_KEY",
}
OS_STORE_REFERENCES = {
    provider: frozenset(
        {
            f"keychain:leo-ppt-generator/{provider}",
            f"host:dpapi/{provider}",
        }
    )
    for provider in EXTERNAL_PROVIDERS
}
SENSITIVE_FIELD_MARKERS = ("token", "secret", "password", "key")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)^bearer\s+\S+"),
    re.compile(r"^sk-[A-Za-z0-9_-]{8,}$"),
    re.compile(r"^(?:gh[oprsu]_|xox[a-z]-|AIza)[A-Za-z0-9_-]{8,}$"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class RuntimeConfigError(ValueError):
    """只携带稳定原因码和安全 JSON pointer 的配置错误。"""

    def __init__(self, reason_code: str, pointer: str | None = None) -> None:
        self.reason_code = reason_code
        self.pointer = pointer
        super().__init__(reason_code if pointer is None else f"{reason_code}:{pointer}")


@dataclass(frozen=True)
class ConfigIssue:
    reason_code: str
    pointer: str
    provider: str | None = None
    fatal: bool = False


DEFAULTS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "selected_provider": None,
    "max_concurrent_workers": 5,
    "max_run_bytes": 10 * 1024**3,
    "timeouts": {
        "worker_page_seconds": 600,
        "backend_api_seconds": 60,
        "backend_api_retries": 3,
    },
    "provider_profiles": {},
}


@dataclass(frozen=True)
class RuntimeConfig:
    values: dict[str, Any]
    sources: dict[str, str]
    warnings: tuple[str, ...]
    path: Path
    source_map: dict[str, str]
    canonical_digest: str | None
    validation_issues: tuple[ConfigIssue, ...]
    document: dict[str, Any]

    @property
    def digest(self) -> str | None:
        return self.canonical_digest

    @property
    def issues(self) -> tuple[ConfigIssue, ...]:
        return self.validation_issues


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate or non-string mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _expanded_absolute(
    value: str | os.PathLike[str],
    environ: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    expanded = str(value)

    variable_pattern = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
    expanded = variable_pattern.sub(
        lambda match: environment.get(
            match.group(1) or match.group(2), match.group(0)
        ),
        expanded,
    )
    expanded = re.sub(
        r"%([^%]+)%",
        lambda match: environment.get(match.group(1), match.group(0)),
        expanded,
    )
    if expanded == "~" or expanded.startswith(("~/", "~\\")):
        user_home = environment.get("HOME") or environment.get("USERPROFILE")
        if user_home:
            expanded = str(Path(user_home) / expanded[2:]) if len(expanded) > 1 else user_home
        else:
            expanded = os.path.expanduser(expanded)
    return Path(expanded).resolve()


def default_home(environ: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    override = environment.get("LEO_PPT_HOME")
    if override and override.strip():
        return _expanded_absolute(override, environment)
    if sys.platform == "darwin":
        return _expanded_absolute(
            Path.home() / "Library/Application Support/leo-ppt-generator",
            environment,
        )
    if os.name == "nt":
        base = Path(environment.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return _expanded_absolute(base / "leo-ppt-generator", environment)
    base = Path(environment.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return _expanded_absolute(base / "leo-ppt-generator", environment)


def _pointer(parent: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}" if parent else f"/{escaped}"


def _looks_like_secret(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    return any(pattern.search(candidate) for pattern in _SECRET_VALUE_PATTERNS)


def _allowed_keys(pointer: str) -> frozenset[str]:
    if pointer == "":
        return frozenset(
            {
                "schema_version",
                "selected_provider",
                "max_concurrent_workers",
                "max_run_bytes",
                "timeouts",
                "provider_profiles",
            }
        )
    if pointer == "/timeouts":
        return frozenset(
            {"worker_page_seconds", "backend_api_seconds", "backend_api_retries"}
        )
    if pointer == "/provider_profiles":
        return frozenset(EXTERNAL_PROVIDERS)
    if pointer.startswith("/provider_profiles/") and pointer.count("/") == 2:
        provider = pointer.rsplit("/", 1)[-1]
        common = {
            "model",
            "credential_source",
            "credential_ref",
            "credential_generation",
        }
        if provider == "openai-compatible":
            common.add("endpoint_origin")
        return frozenset(common)
    return frozenset()


def _scan_sensitive_fields(value: Any, pointer: str = "") -> None:
    if isinstance(value, dict):
        allowed = _allowed_keys(pointer)
        for key, child in value.items():
            child_pointer = _pointer(pointer, str(key))
            is_unknown = key not in allowed
            if is_unknown and any(marker in key.lower() for marker in SENSITIVE_FIELD_MARKERS):
                raise RuntimeConfigError("unknown_sensitive_field", child_pointer)
            if _looks_like_secret(child):
                raise RuntimeConfigError("unknown_sensitive_field", child_pointer)
            _scan_sensitive_fields(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_sensitive_fields(child, _pointer(pointer, str(index)))


def _integer(value: Any, *, minimum: int, maximum: int, pointer: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RuntimeConfigError("config_invalid", pointer)
    return value


def validate_endpoint_origin(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeConfigError("provider_profile_invalid:endpoint_origin")
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeConfigError("provider_profile_invalid:endpoint_origin") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or any(character.isspace() for character in candidate)
    ):
        raise RuntimeConfigError("provider_profile_invalid:endpoint_origin")
    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    authority = hostname if port is None else f"{hostname}:{port}"
    return f"https://{authority}"


def _model(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeConfigError("provider_profile_invalid:model")
    return value.strip()


def _validate_credential(
    provider: str,
    profile: Mapping[str, Any],
    environment: Mapping[str, str],
) -> tuple[dict[str, Any], ConfigIssue | None]:
    source = profile.get("credential_source")
    reference = profile.get("credential_ref")
    generation = profile.get("credential_generation")
    pointer = f"/provider_profiles/{provider}"
    if source not in {"environment-reference", "os-store-reference"}:
        raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_source")
    if not isinstance(reference, str):
        raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_ref")

    normalized: dict[str, Any] = {
        "credential_source": source,
        "credential_ref": reference,
    }
    if source == "environment-reference":
        expected = ENVIRONMENT_REFERENCES[provider]
        if reference != expected or generation is not None:
            raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_ref")
        variable = expected.removeprefix("env:")
        issue = None
        if not environment.get(variable, "").strip():
            issue = ConfigIssue(
                reason_code="credential_environment_missing",
                pointer=f"{pointer}/credential_ref",
                provider=provider,
            )
        return normalized, issue

    if reference not in OS_STORE_REFERENCES[provider]:
        raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_ref")
    if sys.platform == "darwin" and not reference.startswith("keychain:"):
        raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_ref")
    if os.name == "nt" and not reference.startswith("host:dpapi/"):
        raise RuntimeConfigError("provider_profile_invalid", f"{pointer}/credential_ref")
    normalized["credential_generation"] = _integer(
        generation,
        minimum=1,
        maximum=2**63 - 1,
        pointer=f"{pointer}/credential_generation",
    )
    return normalized, None


def _validate_profile(
    provider: str,
    value: Any,
    environment: Mapping[str, str],
) -> tuple[dict[str, Any], ConfigIssue | None]:
    pointer = f"/provider_profiles/{provider}"
    if not isinstance(value, dict):
        raise RuntimeConfigError("provider_profile_invalid", pointer)
    expected = {
        "model",
        "credential_source",
        "credential_ref",
    }
    if value.get("credential_source") == "os-store-reference":
        expected.add("credential_generation")
    if provider == "openai-compatible":
        expected.add("endpoint_origin")
    if set(value) != expected:
        raise RuntimeConfigError("provider_profile_invalid", pointer)

    credential, issue = _validate_credential(provider, value, environment)
    normalized: dict[str, Any] = {"model": _model(value.get("model"))}
    if provider == "openai-compatible":
        normalized["endpoint_origin"] = validate_endpoint_origin(
            value.get("endpoint_origin")
        )
    normalized.update(credential)
    return normalized, issue


def _is_development_document(raw: Mapping[str, Any]) -> bool:
    development_fields = {
        "schema_version",
        "max_concurrent_workers",
        "max_run_bytes",
        "timeouts",
    }
    if raw.get("schema_version") != SCHEMA_VERSION:
        return False
    if "provider_profiles" not in raw:
        return set(raw).issubset(development_fields)

    profiles = raw.get("provider_profiles")
    if not isinstance(profiles, dict) or not profiles:
        return False
    legacy_profile_fields = {"endpoint_origin", "model"}
    return all(
        isinstance(profile, dict)
        and bool(profile)
        and set(profile).issubset(legacy_profile_fields)
        for profile in profiles.values()
    )


def _normalize_document(
    raw: Any,
    environment: Mapping[str, str],
    *,
    detect_development: bool,
) -> tuple[dict[str, Any], tuple[ConfigIssue, ...]]:
    if not isinstance(raw, dict):
        raise RuntimeConfigError("config_invalid")
    _scan_sensitive_fields(raw)
    version = raw.get("schema_version")
    if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
        raise RuntimeConfigError("config_schema_too_new")
    if version != SCHEMA_VERSION:
        raise RuntimeConfigError("config_invalid", "/schema_version")
    if detect_development and _is_development_document(raw):
        raise RuntimeConfigError("development_config_reset_required")

    allowed = _allowed_keys("")
    unknown = set(raw) - allowed
    if unknown:
        raise RuntimeConfigError("config_invalid", _pointer("", sorted(unknown)[0]))
    if "provider_profiles" not in raw:
        raise RuntimeConfigError("config_invalid", "/provider_profiles")

    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider_profiles": {},
    }
    if "selected_provider" in raw:
        selected = raw["selected_provider"]
        if selected not in EXTERNAL_PROVIDERS:
            raise RuntimeConfigError("provider_selection_invalid", "/selected_provider")
        normalized["selected_provider"] = selected
    if "max_concurrent_workers" in raw:
        normalized["max_concurrent_workers"] = _integer(
            raw["max_concurrent_workers"],
            minimum=1,
            maximum=16,
            pointer="/max_concurrent_workers",
        )
    if "max_run_bytes" in raw:
        normalized["max_run_bytes"] = _integer(
            raw["max_run_bytes"],
            minimum=1024**2,
            maximum=100 * 1024**3,
            pointer="/max_run_bytes",
        )
    if "timeouts" in raw:
        timeouts = raw["timeouts"]
        if not isinstance(timeouts, dict) or set(timeouts) - _allowed_keys("/timeouts"):
            raise RuntimeConfigError("config_invalid", "/timeouts")
        limits = {
            "worker_page_seconds": (1, 86400),
            "backend_api_seconds": (1, 3600),
            "backend_api_retries": (0, 10),
        }
        normalized["timeouts"] = {
            key: _integer(
                value,
                minimum=limits[key][0],
                maximum=limits[key][1],
                pointer=f"/timeouts/{key}",
            )
            for key, value in timeouts.items()
        }

    profiles = raw["provider_profiles"]
    if not isinstance(profiles, dict) or set(profiles) - set(EXTERNAL_PROVIDERS):
        raise RuntimeConfigError("provider_profile_invalid", "/provider_profiles")
    issues: list[ConfigIssue] = []
    for provider in EXTERNAL_PROVIDERS:
        if provider not in profiles:
            continue
        profile, issue = _validate_profile(provider, profiles[provider], environment)
        normalized["provider_profiles"][provider] = profile
        if issue is not None:
            issues.append(issue)

    selected = normalized.get("selected_provider")
    if selected is not None and selected not in normalized["provider_profiles"]:
        raise RuntimeConfigError("provider_selection_invalid", "/selected_provider")
    return normalized, tuple(issues)


def canonical_config_json(value: Mapping[str, Any]) -> str:
    """返回用于 CAS 身份的稳定 UTF-8 JSON 表示。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_config_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_config_json(value).encode("utf-8")).hexdigest()


def _mark_source_tree(
    source_map: dict[str, str], pointer: str, value: Any, source: str
) -> None:
    if pointer:
        source_map[pointer] = source
    if isinstance(value, dict):
        for key, child in value.items():
            _mark_source_tree(source_map, _pointer(pointer, key), child, source)


def _merged_values(
    document: Mapping[str, Any], environment: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    values = copy.deepcopy(DEFAULTS)
    values["timeouts"].update(document.get("timeouts", {}))
    values["provider_profiles"] = copy.deepcopy(document["provider_profiles"])
    for key in (
        "schema_version",
        "selected_provider",
        "max_concurrent_workers",
        "max_run_bytes",
    ):
        if key in document:
            values[key] = copy.deepcopy(document[key])

    sources = {key: "default" for key in DEFAULTS}
    source_map: dict[str, str] = {}
    _mark_source_tree(source_map, "", values, "default")
    for key, child in document.items():
        sources[key] = "config.yaml"
        _mark_source_tree(source_map, _pointer("", key), child, "config.yaml")

    override = environment.get("LEO_PPT_MAX_WORKERS")
    if override is not None:
        try:
            workers = int(override)
        except (TypeError, ValueError) as exc:
            raise RuntimeConfigError(
                "config_invalid", "/max_concurrent_workers"
            ) from exc
        values["max_concurrent_workers"] = _integer(
            workers,
            minimum=1,
            maximum=16,
            pointer="/max_concurrent_workers",
        )
        sources["max_concurrent_workers"] = "environment"
        source_map["/max_concurrent_workers"] = "environment"
    return values, sources, source_map


def _load_yaml_document(path: Path) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            raise RuntimeConfigError("config_invalid")
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except RuntimeConfigError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeConfigError("config_invalid") from exc


def _snapshot(
    path: Path,
    document: dict[str, Any],
    issues: tuple[ConfigIssue, ...],
    environment: Mapping[str, str],
    *,
    persisted: bool,
) -> RuntimeConfig:
    values, sources, source_map = _merged_values(document, environment)
    warnings = tuple(issue.reason_code for issue in issues)
    return RuntimeConfig(
        values=values,
        sources=sources,
        warnings=warnings,
        path=path,
        source_map=source_map,
        canonical_digest=canonical_config_digest(document) if persisted else None,
        validation_issues=issues,
        document=copy.deepcopy(document),
    )


def _ensure_private_directory(path: Path) -> None:
    try:
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise RuntimeConfigError("config_write_failed")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(path, 0o700)
    except RuntimeConfigError:
        raise
    except OSError as exc:
        raise RuntimeConfigError("config_write_failed") from exc


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except (AttributeError, OSError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _serialize_document(document: Mapping[str, Any]) -> bytes:
    body = yaml.safe_dump(
        dict(document),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return body.encode("utf-8")


def _atomic_write_document(
    path: Path,
    document: dict[str, Any],
    environment: Mapping[str, str],
) -> None:
    _ensure_private_directory(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeConfigError("config_write_failed")

    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(_serialize_document(document))
            handle.flush()
            os.fsync(handle.fileno())

        temporary_path = Path(temporary_name)
        reparsed = _load_yaml_document(temporary_path)
        validated, _ = _normalize_document(
            reparsed, environment, detect_development=False
        )
        if canonical_config_digest(validated) != canonical_config_digest(document):
            raise RuntimeConfigError("config_write_failed")
        os.replace(temporary_path, path)
        temporary_name = None
        if os.name != "nt":
            os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    except RuntimeConfigError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeConfigError("config_write_failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


class ConfigStore:
    """schema v1 ConfigStore；以 canonical digest 提供进程间 CAS。"""

    def __init__(
        self,
        home: str | os.PathLike[str] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.environ = os.environ if environ is None else environ
        self.home = (
            default_home(self.environ)
            if home is None
            else _expanded_absolute(home, self.environ)
        )
        self.path = self.home / "config.yaml"
        self.lock_path = self.home / ".config.lock"

    def read(self) -> RuntimeConfig:
        if not self.path.exists() and not self.path.is_symlink():
            document = {
                "schema_version": SCHEMA_VERSION,
                "provider_profiles": {},
            }
            return _snapshot(
                self.path, document, (), self.environ, persisted=False
            )
        raw = _load_yaml_document(self.path)
        document, issues = _normalize_document(
            raw, self.environ, detect_development=True
        )
        return _snapshot(
            self.path, document, issues, self.environ, persisted=True
        )

    def compare_and_swap(
        self,
        expected_digest: str | None,
        candidate: Mapping[str, Any] | RuntimeConfig,
    ) -> RuntimeConfig:
        _ensure_private_directory(self.home)
        candidate_value = (
            candidate.document if isinstance(candidate, RuntimeConfig) else candidate
        )
        normalized, _ = _normalize_document(
            copy.deepcopy(candidate_value),
            self.environ,
            detect_development=False,
        )
        with FileLock(str(self.lock_path), mode=0o600):
            current = self.read()
            if current.canonical_digest != expected_digest:
                raise RuntimeConfigError("config_write_conflict")
            _atomic_write_document(self.path, normalized, self.environ)
            return self.read()


def load_runtime_config(
    *,
    home: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    return ConfigStore(home, environ=environ).read()


def openai_compatible_profile(
    *,
    home: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    profile = load_runtime_config(home=home, environ=environ).values[
        "provider_profiles"
    ].get("openai-compatible")
    return copy.deepcopy(profile) if profile is not None else None


def configure_openai_compatible_profile(
    *,
    endpoint_origin: str,
    model: str,
    credential_source: str = "environment-reference",
    credential_ref: str | None = None,
    credential_generation: int | None = None,
    home: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    """兼容旧内部命令的非敏感写入器；始终写正式完整 profile。"""

    store = ConfigStore(home, environ=environ)
    current = store.read()
    candidate = copy.deepcopy(current.document)
    if credential_ref is None:
        credential_ref = ENVIRONMENT_REFERENCES["openai-compatible"]
    if credential_source != "os-store-reference" and credential_generation is not None:
        raise RuntimeConfigError(
            "provider_profile_invalid",
            "/provider_profiles/openai-compatible/credential_generation",
        )
    profile: dict[str, Any] = {
        "endpoint_origin": endpoint_origin,
        "model": model,
        "credential_source": credential_source,
        "credential_ref": credential_ref,
    }
    if credential_source == "os-store-reference":
        profile["credential_generation"] = credential_generation
    candidate["provider_profiles"]["openai-compatible"] = profile
    candidate["selected_provider"] = "openai-compatible"
    return store.compare_and_swap(current.canonical_digest, candidate)


def run_size_bytes(run_dir: Path) -> int:
    return sum(
        path.stat().st_size
        for path in run_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def assert_run_quota(run_dir: Path, config: RuntimeConfig) -> None:
    if run_size_bytes(run_dir) > config.values["max_run_bytes"]:
        raise RuntimeConfigError("disk_quota_exceeded")
