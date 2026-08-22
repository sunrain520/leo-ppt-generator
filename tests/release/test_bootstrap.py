from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tests.integration.test_runtime_manager import make_bundle

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/leo-ppt-generator/scripts"
LOCK = ROOT / "skills/leo-ppt-generator/runtime/bootstrap-lock.json"


def make_bootstrap_bundle(tmp_path: Path) -> Path:
    bundle = make_bundle(tmp_path)
    scripts = bundle / "scripts"
    scripts.mkdir()
    shutil.copy2(SCRIPTS / "runtime_manager.py", scripts / "runtime_manager.py")
    shutil.copy2(SCRIPTS / "leo-bootstrap.sh", scripts / "leo-bootstrap.sh")
    shutil.copy2(SCRIPTS / "leo-bootstrap.ps1", scripts / "leo-bootstrap.ps1")
    shutil.copy2(LOCK, bundle / "runtime/bootstrap-lock.json")
    return bundle


def run_posix(
    bundle: Path,
    home: Path,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(environment or {})
    env["LEO_PPT_HOME"] = str(home)
    return subprocess.run(
        ["bash", str(bundle / "scripts/leo-bootstrap.sh"), "bootstrap"],
        cwd=bundle,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def write_fake_uv(path: Path) -> None:
    path.write_text(
        """#!/bin/sh
if [ "$1" = "--version" ]; then echo 'uv 0.11.19'; exit 0; fi
if [ "$1 $2" = "python install" ]; then exit "${LEO_FAKE_UV_INSTALL_EXIT:-0}"; fi
if [ "$1 $2" = "python find" ]; then printf '%s\n' "$LEO_FAKE_PYTHON"; exit 0; fi
exit 90
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def no_python_path(tmp_path: Path) -> tuple[Path, str]:
    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    return tools, f"{tools}:/usr/bin:/bin"


def test_bootstrap_lock_pins_https_artifacts_and_real_checksums():
    value = json.loads(LOCK.read_text(encoding="utf-8"))

    assert value["schema_version"] == 1
    assert value["python_version"].startswith("3.12.")
    assert value["uv_version"] == "0.11.19"
    for platform_name, artifact in value["artifacts"].items():
        assert artifact["url"].startswith(
            "https://github.com/astral-sh/uv/releases/download/0.11.19/"
        ), platform_name
        assert len(artifact["sha256"]) == 64
        int(artifact["sha256"], 16)
        assert 20_000_000 < artifact["max_bytes"] < 30_000_000


def test_posix_bootstrap_reuses_compatible_system_python(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)

    result = run_posix(bundle, tmp_path / "home")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["python_source"] == "system"
    assert payload["runtime_outcome"] == "installed"
    assert payload["runtime_identity"]
    assert "bootstrap[platform_check]" in result.stderr
    assert "bootstrap[runtime_ensure]" in result.stderr
    assert not list((tmp_path / "home").glob(".bootstrap-stage.*"))

    reused = run_posix(bundle, tmp_path / "home")
    assert reused.returncode == 0, reused.stderr
    assert json.loads(reused.stdout)["runtime_outcome"] == "reused"


def test_posix_bootstrap_uses_existing_uv_without_changing_parent_path(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    write_fake_uv(tools / "uv")
    original_path = os.environ.get("PATH")

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={
            "PATH": isolated_path,
            "LEO_FAKE_PYTHON": sys.executable,
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python_source"] == "uv-existing"
    assert os.environ.get("PATH") == original_path
    assert not list((tmp_path / "home").glob(".bootstrap-stage.*"))


def test_posix_bootstrap_reuses_existing_private_python_before_uv(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    _tools, isolated_path = no_python_path(tmp_path / "isolated")
    home = tmp_path / "home"
    private_python = home / "python/cpython-3.12/bin/python3.12"
    private_python.parent.mkdir(parents=True)
    os.link(sys.executable, private_python)

    result = run_posix(
        bundle,
        home,
        environment={"PATH": isolated_path},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python_source"] == "private-python"


def test_posix_bootstrap_downloads_and_verifies_pinned_uv(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    archive_root = tmp_path / "archive/uv-aarch64-apple-darwin"
    archive_root.mkdir(parents=True)
    write_fake_uv(archive_root / "uv")
    archive = tmp_path / "uv.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(archive_root, arcname="uv-aarch64-apple-darwin")
    lock_path = bundle / "runtime/bootstrap-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["artifacts"]["macos-arm64"]["sha256"] = hashlib.sha256(
        archive.read_bytes()
    ).hexdigest()
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    fake_curl = tools / "curl"
    fake_curl.write_text(
        """#!/bin/sh
output=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then output="$2"; shift 2; continue; fi
  shift
done
cp "$LEO_FAKE_ARCHIVE" "$output"
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={
            "PATH": isolated_path,
            "LEO_FAKE_ARCHIVE": str(archive),
            "LEO_FAKE_PYTHON": sys.executable,
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python_source"] == "uv-bootstrap"
    assert not list((tmp_path / "home").glob(".bootstrap-stage.*"))


def test_posix_bootstrap_rejects_non_allowlisted_origin_before_download(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    _tools, isolated_path = no_python_path(tmp_path / "isolated")
    lock_path = bundle / "runtime/bootstrap-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["artifacts"]["macos-arm64"]["url"] = "http://example.invalid/uv.tar.gz"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={"PATH": isolated_path},
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["reason_code"] == "bootstrap_origin_forbidden"
    assert payload["primary_action"]["id"] == "reinstall_skill"


@pytest.mark.parametrize("curl_exit", [6, 22, 28])
def test_posix_bootstrap_normalizes_download_and_proxy_failures(
    tmp_path: Path, curl_exit: int
):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    fake_curl = tools / "curl"
    fake_curl.write_text(f"#!/bin/sh\nexit {curl_exit}\n", encoding="utf-8")
    fake_curl.chmod(0o755)

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={"PATH": isolated_path},
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_download_failed"
    assert not list((tmp_path / "home").glob(".bootstrap-stage.*"))


def test_posix_bootstrap_rejects_hash_mismatch_and_cleans_stage(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    fake_curl = tools / "curl"
    fake_curl.write_text(
        """#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then printf 'tampered' >"$2"; exit 0; fi
  shift
done
exit 2
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={"PATH": isolated_path},
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_artifact_hash_mismatch"
    assert not list((tmp_path / "home").glob(".bootstrap-stage.*"))


def test_posix_bootstrap_rejects_artifact_above_manifest_limit(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    lock_path = bundle / "runtime/bootstrap-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["artifacts"]["macos-arm64"]["max_bytes"] = 4
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    fake_curl = tools / "curl"
    fake_curl.write_text(
        """#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then printf 'oversized' >"$2"; exit 0; fi
  shift
done
exit 2
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={"PATH": isolated_path},
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_artifact_size_invalid"


def test_posix_bootstrap_propagates_private_python_install_failure(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    tools, isolated_path = no_python_path(tmp_path / "isolated")
    write_fake_uv(tools / "uv")

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={
            "PATH": isolated_path,
            "LEO_FAKE_PYTHON": sys.executable,
            "LEO_FAKE_UV_INSTALL_EXIT": "33",
        },
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_python_install_failed"


def test_posix_bootstrap_rejects_incompatible_architecture_before_mutation(
    tmp_path: Path,
):
    bundle = make_bootstrap_bundle(tmp_path)
    tools = tmp_path / "tools"
    tools.mkdir()
    fake_uname = tools / "uname"
    fake_uname.write_text(
        '#!/bin/sh\nif [ "$1" = "-s" ]; then echo Darwin; else echo x86_64; fi\n',
        encoding="utf-8",
    )
    fake_uname.chmod(0o755)

    result = run_posix(
        bundle,
        tmp_path / "home",
        environment={"PATH": f"{tools}:{os.environ['PATH']}"},
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_platform_unsupported"
    assert not (tmp_path / "home").exists()


def test_posix_bootstrap_reports_unwritable_private_home(tmp_path: Path):
    bundle = make_bootstrap_bundle(tmp_path)
    _tools, isolated_path = no_python_path(tmp_path / "isolated")
    parent = tmp_path / "read-only"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        result = run_posix(
            bundle,
            parent / "home",
            environment={"PATH": isolated_path},
        )
    finally:
        parent.chmod(0o700)

    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "bootstrap_home_unwritable"


def test_powershell_launcher_reuses_python_in_windows_compatibility_run(tmp_path: Path):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required")
    bundle = make_bootstrap_bundle(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "OS": "Windows_NT",
            "PROCESSOR_ARCHITECTURE": "AMD64",
            "LEO_PPT_HOME": str(tmp_path / "windows-home"),
            "LOCALAPPDATA": str(tmp_path / "local-app-data"),
        }
    )
    environment.pop("PROCESSOR_ARCHITEW6432", None)

    result = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(bundle / "scripts/leo-bootstrap.ps1"),
            "bootstrap",
        ],
        cwd=bundle,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["platform"] == "windows"
    assert payload["architecture"] == "x64"
    assert payload["python_source"] == "system"
    assert "bootstrap[platform_check]" in result.stderr
