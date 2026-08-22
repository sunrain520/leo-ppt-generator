#!/usr/bin/env python3
"""从唯一 canonical Skill tree 构建可复现 standalone 与 Plugin 发布包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/leo-ppt-generator"
PLUGIN_MANIFEST = ROOT / ".codex-plugin/plugin.json"
RUNTIME_PROJECT = SKILL / "runtime/pyproject.toml"
BOOTSTRAP_LOCK = SKILL / "runtime/bootstrap-lock.json"
EXCLUDED_PARTS = {"__pycache__", "build", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class ReleaseError(ValueError):
    pass


def files_under(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
        and path.suffix not in EXCLUDED_SUFFIXES
        and not any(part.endswith(".egg-info") for part in path.relative_to(root).parts)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in files_under(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def runtime_version() -> str:
    for line in RUNTIME_PROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split('"', 2)[1]
    raise ReleaseError("runtime_version_missing")


def plugin_manifest() -> dict:
    value = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    if value.get("name") != "leo-ppt-generator":
        raise ReleaseError("plugin_name_mismatch")
    if value.get("version") != runtime_version():
        raise ReleaseError("release_version_mismatch")
    if value.get("skills") != "./skills/":
        raise ReleaseError("plugin_skill_path_invalid")
    if any(field in value for field in ("apps", "mcpServers", "hooks")):
        raise ReleaseError("plugin_declares_missing_component")
    return value


def write_zip(path: Path, entries: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, name in sorted(entries, key=lambda item: item[1]):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if source.stat().st_mode & 0o111 else 0o644) << 16
            archive.writestr(info, source.read_bytes())


def skill_entries(prefix: str) -> list[tuple[Path, str]]:
    return [
        (path, f"{prefix}{path.relative_to(SKILL).as_posix()}")
        for path in files_under(SKILL)
    ]


def build(output: Path) -> dict:
    manifest = plugin_manifest()
    skill_digest = tree_hash(SKILL)
    output.mkdir(parents=True, exist_ok=True)
    standalone = output / f"leo-ppt-generator-{manifest['version']}-skill.zip"
    plugin = output / f"leo-ppt-generator-{manifest['version']}-plugin.zip"
    write_zip(standalone, skill_entries("leo-ppt-generator/"))
    write_zip(
        plugin,
        [(PLUGIN_MANIFEST, ".codex-plugin/plugin.json"), *skill_entries("skills/leo-ppt-generator/")],
    )
    bootstrap = json.loads(BOOTSTRAP_LOCK.read_text(encoding="utf-8"))
    release = {
        "schema_version": "leo-ppt-release/v1",
        "name": manifest["name"],
        "version": manifest["version"],
        "release_identity": f"{manifest['version']}+{skill_digest[:16]}",
        "cachebuster": skill_digest[:16],
        "canonical_skill_tree_sha256": skill_digest,
        "plugin_manifest_sha256": sha256_file(PLUGIN_MANIFEST),
        "bootstrap_lock_sha256": sha256_file(BOOTSTRAP_LOCK),
        "bootstrap_artifacts": {
            name: {"url": value["url"], "sha256": value["sha256"]}
            for name, value in sorted(bootstrap["artifacts"].items())
        },
        "licenses": [
            {"path": path.name, "sha256": sha256_file(path)}
            for path in sorted(SKILL.glob("LICENSE*"))
        ],
        "archives": {
            "standalone": {"path": standalone.name, "sha256": sha256_file(standalone)},
            "plugin": {"path": plugin.name, "sha256": sha256_file(plugin)},
        },
    }
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"manifest": str(manifest_path), **release}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
