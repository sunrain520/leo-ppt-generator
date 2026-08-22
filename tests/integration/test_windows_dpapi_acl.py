"""Windows x64 上对当前用户 DPAPI 与文件 ACL 的真实集成验证。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from leo_ppt_generator.credentials import (
    CredentialError,
    WindowsDPAPIStore,
    _enforce_windows_acl,
    _windows_acl_is_private,
)


_WINDOWS_X64 = os.name == "nt" and platform.machine().casefold() in {
    "amd64",
    "x86_64",
    "x64",
}
_USERS_SID = "*S-1-5-32-545"
_FORBIDDEN_ACL_IDENTITIES = (
    "everyone",
    "authenticated users",
    "builtin\\users",
    "s-1-1-0",
    "s-1-5-11",
    "s-1-5-32-545",
)
_WRITE_RIGHTS = ("(F)", "(M)", "(W)", "(WD)", "(AD)", "(DC)", "(WA)", "(WEA)", "(WO)", "(GW)", "(GA)")
_OTHER_USER_RUNNER_ENV = "LEO_PPT_DPAPI_OTHER_USER_RUNNER"

pytestmark = pytest.mark.skipif(
    not _WINDOWS_X64,
    reason="requires a native Windows x64 process with current-user DPAPI and NTFS ACLs",
)


def _run_icacls(*arguments: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["icacls", *arguments, "/c"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def _assert_no_users_or_everyone_write(path: Path) -> None:
    output = _run_icacls(str(path)).stdout.casefold()
    insecure_lines = [
        line
        for line in output.splitlines()
        if any(identity in line for identity in _FORBIDDEN_ACL_IDENTITIES)
        and any(right in line.upper() for right in _WRITE_RIGHTS)
    ]
    assert not insecure_lines, f"{path} grants Users/Everyone write access: {insecure_lines}"
    assert _windows_acl_is_private(path), f"{path} must pass the store ACL checker"


def _grant_users(path: Path, permission: str) -> None:
    _run_icacls(str(path), "/grant", f"{_USERS_SID}:{permission}")


def _public_probe_directory() -> Path:
    public_root = Path(os.environ.get("PUBLIC", r"C:\\Users\\Public")) / "Documents"
    directory = public_root / f"leo-ppt-dpapi-other-user-{uuid.uuid4().hex}"
    try:
        directory.mkdir(parents=True)
        _enforce_windows_acl(directory, True)
        _grant_users(directory, "(OI)(CI)(RX)")
    except (CredentialError, OSError, AssertionError) as exc:
        shutil.rmtree(directory, ignore_errors=True)
        pytest.skip(f"other-user DPAPI probe staging is unavailable: {exc}")
    return directory


def _write_other_user_probe(path: Path) -> None:
    runtime_source = Path(__file__).resolve().parents[2] / "skills/leo-ppt-generator/runtime/src"
    path.write_text(
        "\n".join(
            (
                "from pathlib import Path",
                "import sys",
                f"sys.path.insert(0, {str(runtime_source)!r})",
                "from leo_ppt_generator.credentials import _dpapi_unprotect",
                "try:",
                "    blob = Path(sys.argv[1]).read_bytes()",
                "except OSError:",
                "    print('DPAPI_BLOB_UNREADABLE')",
                "    raise SystemExit(2)",
                "try:",
                "    _dpapi_unprotect(blob)",
                "except Exception:",
                "    print('DPAPI_DECRYPT_REJECTED')",
                "    raise SystemExit(3)",
                "print('DPAPI_DECRYPTED')",
                "raise SystemExit(0)",
            )
        ),
        encoding="utf-8",
    )


# Validates: Requirements 14.2, 14.4, 14.5
def test_current_user_dpapi_roundtrip_uses_private_acl(tmp_path: Path) -> None:
    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(root)
    secret = f"dpapi-current-user-{uuid.uuid4().hex}"

    store.write("openai", secret)

    blob_path = root / "openai.dpapi"
    blob = blob_path.read_bytes()
    assert blob
    assert secret.encode("utf-8") not in blob
    assert store.read("openai") == secret
    _assert_no_users_or_everyone_write(root)
    _assert_no_users_or_everyone_write(blob_path)
    assert not list(root.glob(".*.tmp"))


# Validates: Requirements 14.4, 14.5
def test_corrupt_dpapi_blob_fails_closed_without_temp_fallback(tmp_path: Path) -> None:
    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(root)
    store.write("openai", f"dpapi-corrupt-{uuid.uuid4().hex}")
    blob_path = root / "openai.dpapi"
    corrupted_blob = b"not-a-dpapi-blob\x00"
    blob_path.write_bytes(corrupted_blob)

    with pytest.raises(CredentialError) as error:
        store.read("openai")

    assert str(error.value) in {
        "credential_blob_invalid",
        "credential_dpapi_decrypt_failed",
    }
    assert blob_path.read_bytes() == corrupted_blob
    assert sorted(path.name for path in root.iterdir()) == ["openai.dpapi"]


# Validates: Requirements 14.4, 14.5
@pytest.mark.parametrize("target_name", ("credentials", "openai.dpapi"))
def test_users_write_acl_fails_closed_for_directory_and_blob(
    tmp_path: Path, target_name: str
) -> None:
    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(root)
    store.write("openai", f"dpapi-acl-{uuid.uuid4().hex}")
    target = root if target_name == "credentials" else root / target_name

    _grant_users(target, "(W)")

    assert not _windows_acl_is_private(target)
    with pytest.raises(CredentialError, match="credential_store_acl_too_broad"):
        store.read("openai")
    assert not list(root.glob(".*.tmp"))


# Validates: Requirements 14.2, 14.4, 14.5
def test_other_windows_user_cannot_decrypt_when_controlled_runner_is_configured(
    tmp_path: Path,
) -> None:
    """受控 runner 必须以不同 Windows 身份运行，并保留 probe 的 stdout 与退出码。"""

    runner_value = os.environ.get(_OTHER_USER_RUNNER_ENV)
    if not runner_value:
        pytest.skip(f"{_OTHER_USER_RUNNER_ENV} is not configured")
    runner = Path(runner_value)
    assert runner.is_file(), f"{_OTHER_USER_RUNNER_ENV} must be an absolute runner path"

    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(root)
    secret = f"dpapi-other-user-{uuid.uuid4().hex}"
    store.write("openai", secret)

    public_directory = _public_probe_directory()
    try:
        blob_path = public_directory / "credential.dpapi"
        probe_path = public_directory / "probe.py"
        blob_path.write_bytes((root / "openai.dpapi").read_bytes())
        _write_other_user_probe(probe_path)
        _grant_users(blob_path, "R")
        _grant_users(probe_path, "R")

        result = subprocess.run(
            [str(runner), str(sys.executable), str(probe_path), str(blob_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        shutil.rmtree(public_directory, ignore_errors=True)

    assert "DPAPI_BLOB_UNREADABLE" not in result.stdout
    assert "DPAPI_DECRYPTED" not in result.stdout
    assert result.returncode == 3, result.stdout + result.stderr
    assert "DPAPI_DECRYPT_REJECTED" in result.stdout
