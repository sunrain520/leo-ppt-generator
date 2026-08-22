#!/usr/bin/env python3
"""验证发布 manifest、两个归档和 canonical Skill tree 一致。"""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

from build_release import (
    BOOTSTRAP_LOCK,
    PLUGIN_MANIFEST,
    SKILL,
    plugin_manifest,
    sha256_file,
    tree_hash,
)


class ReleaseValidationError(ValueError):
    pass


def extracted_tree_hash(archive: Path, prefix: str) -> str:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as value:
            names = value.namelist()
            if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                raise ReleaseValidationError("release_archive_path_invalid")
            value.extractall(root)
        skill = root / prefix
        if not (skill / "SKILL.md").is_file():
            raise ReleaseValidationError("release_skill_missing")
        if len(list(root.rglob("SKILL.md"))) != 1:
            raise ReleaseValidationError("release_skill_count_invalid")
        return tree_hash(skill)


def validate(path: Path) -> dict:
    release = json.loads(path.read_text(encoding="utf-8"))
    if release.get("schema_version") != "leo-ppt-release/v1":
        raise ReleaseValidationError("release_schema_invalid")
    plugin = plugin_manifest()
    expected_tree = tree_hash(SKILL)
    if release.get("version") != plugin["version"]:
        raise ReleaseValidationError("release_version_mismatch")
    if release.get("canonical_skill_tree_sha256") != expected_tree:
        raise ReleaseValidationError("release_skill_tree_drift")
    if release.get("cachebuster") != expected_tree[:16]:
        raise ReleaseValidationError("release_cachebuster_stale")
    if release.get("plugin_manifest_sha256") != sha256_file(PLUGIN_MANIFEST):
        raise ReleaseValidationError("release_plugin_manifest_drift")
    if release.get("bootstrap_lock_sha256") != sha256_file(BOOTSTRAP_LOCK):
        raise ReleaseValidationError("release_bootstrap_lock_drift")
    if len(release.get("licenses", [])) < 3:
        raise ReleaseValidationError("release_licenses_missing")
    directory = path.parent
    archive_hashes = {}
    for kind, prefix in (
        ("standalone", "leo-ppt-generator"),
        ("plugin", "skills/leo-ppt-generator"),
    ):
        record = release.get("archives", {}).get(kind, {})
        archive = directory / str(record.get("path", ""))
        if not archive.is_file() or sha256_file(archive) != record.get("sha256"):
            raise ReleaseValidationError(f"release_{kind}_archive_drift")
        archive_hashes[kind] = extracted_tree_hash(archive, prefix)
    if set(archive_hashes.values()) != {expected_tree}:
        raise ReleaseValidationError("release_channel_tree_mismatch")
    return {
        "schema_version": "leo-ppt-release-validation/v1",
        "status": "passed",
        "release_identity": release["release_identity"],
        "canonical_skill_tree_sha256": expected_tree,
        "archives": archive_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.manifest.resolve()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
