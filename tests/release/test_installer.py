from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.sh"
WINDOWS_INSTALLER = ROOT / "install.ps1"
POSIX_LAUNCHER = ROOT / "skills/leo-ppt-generator/scripts/leo-ppt"


def test_powershell_onboarding_defaults_to_safe_defer_and_rechecks():
    source = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert "现在进入配置向导？[y/N]" in source
    assert "$Choice -notmatch '^(?i:y|yes)$'" in source
    assert "Invoke-PostActivationOnboarding -StageRoot $StageRoot -SkipPrompt" in source


def _backup_directories(target: Path) -> list[Path]:
    root = target.parent / ".leo-ppt-generator-backups"
    return sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []


def test_public_installers_expose_platform_neutral_help():
    bash = subprocess.run(
        ["bash", str(INSTALLER), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert bash.returncode == 0, bash.stderr
    assert "bash install.sh [选项]" in bash.stdout
    assert "--upgrade" in bash.stdout

    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 不可用")
    powershell = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(WINDOWS_INSTALLER), "-Help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert powershell.returncode == 0, powershell.stderr
    assert "pwsh -File install.ps1 [选项]" in powershell.stdout
    assert "-Upgrade" in powershell.stdout
    assert "${HOME}\\.codex\\skills\\leo-ppt-generator" in powershell.stdout
    assert "仅用于 Windows" not in powershell.stderr


def _make_source(tmp_path: Path, *, version: str = "new", fail_route: str = "") -> Path:
    source = tmp_path / "source" / "leo-ppt-generator"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    (source / "SKILL.md").write_text(f"---\nname: leo-ppt-generator\n---\n{version}\n", encoding="utf-8")
    (source / "VERSION").write_text(version, encoding="utf-8")
    (scripts / "runtime_manager.py").write_text(
        """from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

log = Path(os.environ["LEO_INSTALLER_TEST_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:] == ["ensure"]:
    time.sleep(float(os.environ.get("LEO_INSTALLER_PAUSE_ENSURE", "0")))
    if os.environ.get("LEO_INSTALLER_FAIL_ENSURE") == "1":
        raise SystemExit(19)
    if os.environ.get("LEO_INSTALLER_FALSE_GREEN_ENSURE") == "1":
        print('{"status":"passed"}')
        raise SystemExit(0)
    print('{"outcome":"installed","runtime_identity":"fixture","cli":"fixture-cli"}')
    raise SystemExit(0)
if sys.argv[1:] == ["bootstrap"]:
    time.sleep(float(os.environ.get("LEO_INSTALLER_PAUSE_ENSURE", "0")))
    if os.environ.get("LEO_INSTALLER_FAIL_ENSURE") == "1":
        raise SystemExit(19)
    if os.environ.get("LEO_INSTALLER_FALSE_GREEN_ENSURE") == "1":
        print('{"status":"passed"}')
        raise SystemExit(0)
    print('{"protocol":"leo-ppt-bootstrap/v1","status":"ready","runtime_identity":"fixture","cli_reference":"fixture-cli"}')
    raise SystemExit(0)
if sys.argv[1:] == ["print-cli"]:
    print(os.environ["LEO_INSTALLER_CURRENT_CLI"])
    raise SystemExit(0)
if sys.argv[1:] == ["onboard", "--route", "generate"]:
    if os.environ.get("LEO_INSTALLER_ONBOARD_FAIL") == "1":
        raise SystemExit(29)
    status = os.environ.get("LEO_INSTALLER_ONBOARD_STATUS", "configured_unverified")
    eligibility = {
        "ready": "allowed",
        "configured_unverified": "allowed",
        "degraded": "retryable",
    }.get(status, "blocked")
    readiness = {
        "ready": "ready",
        "configured_unverified": "usable_unverified",
    }.get(status, "installed_not_ready")
    print(json.dumps({
        "schema_version": 1,
        "status": status,
        "reason_code": "fixture_onboarding_" + status,
        "installation_readiness": readiness,
        "execution_eligibility": eligibility,
        "cli_reference": os.environ.get("LEO_INSTALLER_ONBOARD_CLI", "/fixture/leo-ppt"),
    }))
    raise SystemExit(0)
if len(sys.argv) >= 4 and sys.argv[1:3] == ["doctor", "--route"]:
    if sys.argv[3] == os.environ.get("LEO_INSTALLER_FAIL_ROUTE"):
        raise SystemExit(23)
    if sys.argv[3] == os.environ.get("LEO_INSTALLER_FALSE_GREEN_ROUTE"):
        print('{"status":"blocked","reason_code":"fixture_false_green"}')
        raise SystemExit(0)
    print('{"status":"ready","reason_code":"ready"}')
    raise SystemExit(0)
""",
        encoding="utf-8",
    )
    (scripts / "leo-bootstrap.sh").write_text(
        '#!/bin/sh\n'
        'if [ "${LEO_PPT_BOOTSTRAP_QUIET:-0}" != "1" ]; then echo "bootstrap[fixture]" >&2; fi\n'
        'exec python3 "$(dirname "$0")/runtime_manager.py" "$@"\n',
        encoding="utf-8",
    )
    (scripts / "leo-bootstrap.sh").chmod(0o755)
    shutil.copy2(POSIX_LAUNCHER, scripts / "leo-ppt")
    (scripts / "leo-ppt").chmod(0o755)
    (scripts / "leo-bootstrap.ps1").write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ManagerArguments)\n"
        "& python3 (Join-Path $PSScriptRoot 'runtime_manager.py') @ManagerArguments\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8",
    )
    runtime = source / "runtime"
    runtime.mkdir()
    (runtime / "bootstrap-lock.json").write_text("{}\n", encoding="utf-8")
    return source


def _run_installer(
    tmp_path: Path,
    source: Path,
    *extra_args: str,
    fail_route: str = "",
    extra_env: dict[str, str] | None = None,
    target: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    target = target or tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "installer-calls.log"
    environment = os.environ.copy()
    environment["LEO_INSTALLER_TEST_LOG"] = str(log)
    environment["LEO_INSTALLER_FAIL_ROUTE"] = fail_route
    environment["HOME"] = str(tmp_path / "user-home")
    environment["CODEX_HOME"] = str(tmp_path / "user-home/.codex")
    environment.update(extra_env or {})
    result = subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--source",
            str(source),
            "--target",
            str(target),
            *extra_args,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, target, log


def test_local_install_stages_bundle_and_verifies_all_routes(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, log = _run_installer(tmp_path, source)

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert (target / "VERSION").read_text(encoding="utf-8") == "new"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "bootstrap",
        "doctor --route generate",
        "doctor --route direct-editable",
        "doctor --route upgrade-full",
        "doctor --route upgrade-selected",
        "onboard --route generate",
    ]
    assert "重新启动 Codex" in result.stdout
    for stage in ("platform_check", "runtime_ensure", "route_doctor", "activate"):
        assert f"install[{stage}]" in result.stdout


def test_macos_installs_stable_launcher_that_follows_current_cli(tmp_path: Path):
    source = _make_source(tmp_path / "first-source", version="first")
    upgraded_source = _make_source(tmp_path / "second-source", version="second")
    home = tmp_path / "user-home"
    calls = tmp_path / "launcher-calls.log"

    def fixture_cli(name: str) -> Path:
        path = tmp_path / f"runtime-{name}" / "leo-ppt"
        path.parent.mkdir()
        path.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "{name}:$*" >>"$LEO_LAUNCHER_TEST_LOG"\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    first_cli = fixture_cli("first")
    second_cli = fixture_cli("second")
    result, target, _ = _run_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_CURRENT_CLI": str(first_cli)},
    )

    launcher = home / ".local/bin/leo-ppt"
    assert result.returncode == 0, result.stderr
    assert launcher.is_symlink()
    assert launcher.resolve() == (target / "scripts/leo-ppt").resolve()

    environment = os.environ.copy()
    environment.update(
        {
            "LEO_INSTALLER_CURRENT_CLI": str(first_cli),
            "LEO_INSTALLER_TEST_LOG": str(tmp_path / "runtime-manager-calls.log"),
            "LEO_LAUNCHER_TEST_LOG": str(calls),
            "PATH": f"{launcher.parent}:{os.environ['PATH']}",
        }
    )
    first = subprocess.run(
        ["leo-ppt", "config", "--help"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    upgraded, _, _ = _run_installer(
        tmp_path,
        upgraded_source,
        "--upgrade",
        extra_env={"LEO_INSTALLER_CURRENT_CLI": str(second_cli)},
        target=target,
    )
    environment["LEO_INSTALLER_CURRENT_CLI"] = str(second_cli)
    second = subprocess.run(
        ["leo-ppt", "config", "status", "--json"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    assert first.stderr == ""
    assert upgraded.returncode == 0, upgraded.stderr
    assert launcher.is_symlink()
    assert launcher.resolve() == (target / "scripts/leo-ppt").resolve()
    assert (target / "VERSION").read_text(encoding="utf-8") == "second"
    assert second.returncode == 0, second.stderr
    assert second.stderr == ""
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "first:config --help",
        "second:config status --json",
    ]


def test_macos_installer_does_not_overwrite_foreign_leo_ppt_command(tmp_path: Path):
    source = _make_source(tmp_path)
    launcher = tmp_path / "user-home/.local/bin/leo-ppt"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("third-party-command\n", encoding="utf-8")

    result, target, _ = _run_installer(tmp_path, source)

    assert result.returncode != 0
    assert "leo-ppt" in result.stderr
    assert "覆盖" in result.stderr
    assert launcher.read_text(encoding="utf-8") == "third-party-command\n"
    assert not target.exists()


def test_existing_target_is_not_overwritten_without_upgrade(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, log = _run_installer(tmp_path, source)

    assert result.returncode != 0
    assert (target / "VERSION").read_text(encoding="utf-8") == "old"
    assert not log.exists()
    assert "--upgrade" in result.stderr


def test_concurrent_macos_installers_allow_exactly_one_activation(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "installer-calls.log"
    environment = os.environ.copy()
    environment["LEO_INSTALLER_TEST_LOG"] = str(log)
    environment["LEO_INSTALLER_FAIL_ROUTE"] = ""
    environment["HOME"] = str(tmp_path / "user-home")
    environment["CODEX_HOME"] = str(tmp_path / "user-home/.codex")
    environment["LEO_INSTALLER_PAUSE_ENSURE"] = "0.5"
    command = [
        "bash",
        str(INSTALLER),
        "--source",
        str(source),
        "--target",
        str(target),
    ]

    first = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.1)
    second = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    results = [first.communicate(timeout=20), second.communicate(timeout=20)]
    returncodes = [first.returncode, second.returncode]

    assert sorted(code == 0 for code in returncodes) == [False, True], results
    assert (target / "SKILL.md").is_file()
    assert not (target / "leo-ppt-generator").exists()


def test_upgrade_preserves_backup_and_activates_verified_candidate(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, _ = _run_installer(tmp_path, source, "--upgrade")

    assert result.returncode == 0, result.stderr
    assert (target / "VERSION").read_text(encoding="utf-8") == "new"
    backups = _backup_directories(target)
    assert len(backups) == 1
    assert (backups[0] / "VERSION").read_text(encoding="utf-8") == "old"


def test_failed_upgrade_keeps_existing_skill_untouched(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, _ = _run_installer(
        tmp_path,
        source,
        "--upgrade",
        fail_route="direct-editable",
    )

    assert result.returncode != 0
    assert (target / "VERSION").read_text(encoding="utf-8") == "old"
    assert not _backup_directories(target)


def test_failed_upgrade_rolls_back_runtime_current(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, log = _run_installer(
        tmp_path,
        source,
        "--upgrade",
        fail_route="direct-editable",
    )

    assert result.returncode != 0
    assert (target / "VERSION").read_text(encoding="utf-8") == "old"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert "rollback" in calls


def test_macos_false_green_doctor_output_blocks_activation(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FALSE_GREEN_ROUTE": "upgrade-full"},
    )

    assert result.returncode != 0
    assert not target.exists()
    assert "fixture_false_green" in result.stderr


def test_macos_ensure_failure_leaves_no_target_stage_or_lock(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FAIL_ENSURE": "1"},
    )

    assert result.returncode != 0
    assert not target.exists()
    assert not list(target.parent.glob(".leo-ppt-installer.*"))
    assert not (target.parent / ".leo-ppt-generator.install.lock").exists()


def test_macos_invalid_success_receipt_does_not_activate(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FALSE_GREEN_ENSURE": "1"},
    )

    assert result.returncode != 0
    assert "无效 receipt" in result.stderr
    assert not target.exists()


def test_bundle_with_forbidden_generated_or_vendor_directories_is_rejected(tmp_path: Path):
    source = _make_source(tmp_path)
    (source / "third_party").mkdir()

    result, target, _ = _run_installer(tmp_path, source)

    assert result.returncode != 0
    assert not target.exists()
    assert "不允许的目录" in result.stderr


def test_local_install_excludes_development_environments_and_python_caches(tmp_path: Path):
    source = _make_source(tmp_path)
    (source / "runtime" / ".venv" / "bin").mkdir(parents=True)
    (source / "runtime" / ".venv" / "bin" / "python").symlink_to("python3.12")
    (source / "runtime" / "build").mkdir()
    (source / "runtime" / "dist").mkdir()
    (source / "runtime" / "src" / "fixture.egg-info").mkdir(parents=True)
    cache = source / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "runtime_manager.cpython-312.pyc").write_bytes(b"generated")

    result, target, _ = _run_installer(tmp_path, source)

    assert result.returncode == 0, result.stderr
    assert not (target / "runtime" / ".venv").exists()
    assert not (target / "runtime" / "build").exists()
    assert not (target / "runtime" / "dist").exists()
    assert not (target / "runtime" / "src" / "fixture.egg-info").exists()
    assert not (target / "scripts" / "__pycache__").exists()


def test_macos_install_handles_spaces_and_unicode_in_source_and_target(tmp_path: Path):
    source = _make_source(tmp_path / "来源 包")
    target = tmp_path / "目标 包" / "leo-ppt-generator"

    result, installed, _ = _run_installer(tmp_path, source, target=target)

    assert result.returncode == 0, result.stderr
    assert installed == target
    assert (installed / "SKILL.md").is_file()


def test_macos_rejects_unexpected_symlink_and_missing_runtime_manager(tmp_path: Path):
    linked_source = _make_source(tmp_path / "linked")
    (linked_source / "unsafe-link").symlink_to(linked_source / "VERSION")
    linked_result, linked_target, _ = _run_installer(tmp_path / "linked-run", linked_source)

    missing_source = _make_source(tmp_path / "missing")
    (missing_source / "scripts/runtime_manager.py").unlink()
    missing_result, missing_target, _ = _run_installer(tmp_path / "missing-run", missing_source)

    assert linked_result.returncode != 0
    assert "符号链接" in linked_result.stderr
    assert not linked_target.exists()
    assert missing_result.returncode != 0
    assert "runtime_manager.py" in missing_result.stderr
    assert not missing_target.exists()


def test_macos_stale_install_lock_fails_closed_without_touching_target(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.parent.mkdir(parents=True)
    lock = target.parent / ".leo-ppt-generator.install.lock"
    lock.mkdir()

    result, _, log = _run_installer(tmp_path, source)

    assert result.returncode != 0
    assert "陈旧锁" in result.stderr
    assert not target.exists()
    assert lock.is_dir()
    assert not log.exists()


def test_macos_activation_failure_restores_old_skill(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    fake_mv = tool_dir / "mv"
    fake_mv.write_text(
        """#!/bin/sh
case "$1" in
  */.leo-ppt-installer.*/leo-ppt-generator)
    if [ "$2" = "$LEO_TEST_ACTIVATION_TARGET" ]; then exit 91; fi
    ;;
esac
exec /bin/mv "$@"
""",
        encoding="utf-8",
    )
    fake_mv.chmod(0o755)

    result, _, _ = _run_installer(
        tmp_path,
        source,
        "--upgrade",
        extra_env={
            "PATH": f"{tool_dir}:{os.environ['PATH']}",
            "LEO_TEST_ACTIVATION_TARGET": str(target),
        },
    )

    assert result.returncode != 0
    assert "恢复旧版本" in result.stderr
    assert (target / "VERSION").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "user-home/.local/bin/leo-ppt").exists()
    assert not _backup_directories(target)


def test_macos_remote_archive_path_installs_and_corrupt_archive_fails_closed(tmp_path: Path):
    source = _make_source(tmp_path / "bundle")
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(
            source,
            arcname="leo-ppt-generator-test/skills/leo-ppt-generator",
        )
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    installer = standalone / "install.sh"
    shutil.copy2(INSTALLER, installer)
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    fake_curl = tool_dir / "curl"
    fake_curl.write_text(
        """#!/bin/sh
output=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then output="$2"; shift 2; continue; fi
  shift
done
cp "$LEO_FAKE_ARCHIVE" "$output"
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{tool_dir}:{os.environ['PATH']}",
            "LEO_FAKE_ARCHIVE": str(archive),
            "LEO_INSTALLER_TEST_LOG": str(tmp_path / "remote-calls.log"),
            "LEO_INSTALLER_FAIL_ROUTE": "",
            "HOME": str(tmp_path / "remote-user"),
            "CODEX_HOME": str(tmp_path / "remote-user/.codex"),
        }
    )
    target = tmp_path / "remote-target" / "leo-ppt-generator"

    installed = subprocess.run(
        ["bash", str(installer), "--ref", "test-ref", "--target", str(target)],
        cwd=standalone,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    corrupt = tmp_path / "corrupt.tar.gz"
    corrupt.write_text("not-an-archive", encoding="utf-8")
    corrupt_target = tmp_path / "corrupt-target" / "leo-ppt-generator"
    environment["LEO_FAKE_ARCHIVE"] = str(corrupt)
    rejected = subprocess.run(
        ["bash", str(installer), "--target", str(corrupt_target)],
        cwd=standalone,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert installed.returncode == 0, installed.stderr
    assert (target / "SKILL.md").is_file()
    assert rejected.returncode != 0
    assert not corrupt_target.exists()
    assert not list(corrupt_target.parent.glob(".leo-ppt-installer.*"))
    assert not (corrupt_target.parent / ".leo-ppt-generator.install.lock").exists()


def test_macos_rejects_wrong_platform_and_unsafe_ref_before_install(tmp_path: Path):
    source = _make_source(tmp_path)
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    fake_uname = tool_dir / "uname"
    fake_uname.write_text(
        '#!/bin/sh\nif [ "$1" = "-s" ]; then echo Linux; else echo x86_64; fi\n',
        encoding="utf-8",
    )
    fake_uname.chmod(0o755)
    wrong_platform, target, _ = _run_installer(
        tmp_path / "platform",
        source,
        extra_env={"PATH": f"{tool_dir}:{os.environ['PATH']}"},
    )
    unsafe_ref, unsafe_target, _ = _run_installer(
        tmp_path / "ref",
        source,
        "--ref",
        "../main",
    )

    assert wrong_platform.returncode != 0
    assert "仅支持 macOS arm64/x86_64 或 Windows x64" in wrong_platform.stderr
    assert not target.exists()
    assert unsafe_ref.returncode != 0
    assert "安全的 Git commit" in unsafe_ref.stderr
    assert not unsafe_target.exists()


def test_agents_option_installs_into_home_agent_discovery_directory(tmp_path: Path):
    source = _make_source(tmp_path)
    home = tmp_path / "home"
    log = tmp_path / "installer-calls.log"
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["CODEX_HOME"] = str(home / ".codex")
    environment["LEO_INSTALLER_TEST_LOG"] = str(log)
    environment["LEO_INSTALLER_FAIL_ROUTE"] = ""

    result = subprocess.run(
        ["bash", str(INSTALLER), "--source", str(source), "--agents"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    target = home / ".agents" / "skills" / "leo-ppt-generator"
    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert str(target) in result.stdout


def test_default_discovery_directory_installs_without_preinstalled_python_contract(
    tmp_path: Path,
):
    source = _make_source(tmp_path)
    scripts = source / "scripts"
    (scripts / "leo-bootstrap.sh").write_text(
        """#!/bin/sh
printf '%s\n' "$*" >>"$LEO_INSTALLER_TEST_LOG"
if [ "$1" = "bootstrap" ]; then
  echo '{"protocol":"leo-ppt-bootstrap/v1","status":"ready","runtime_identity":"fixture","cli_reference":"fixture-cli"}'
else
  echo '{"status":"ready","reason_code":"ready"}'
fi
""",
        encoding="utf-8",
    )
    (scripts / "leo-bootstrap.sh").chmod(0o755)
    home = tmp_path / "clean-user"
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "PATH": "/usr/bin:/bin",
            "LEO_INSTALLER_TEST_LOG": str(tmp_path / "no-python.log"),
            "LEO_INSTALLER_FAIL_ROUTE": "",
        }
    )

    result = subprocess.run(
        ["bash", str(INSTALLER), "--source", str(source)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    target = home / ".codex/skills/leo-ppt-generator"
    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()


@pytest.mark.parametrize("duplicate_kind", ["legacy", "dual", "visible-backup"])
def test_macos_duplicate_discovery_paths_fail_with_one_migration_action(
    tmp_path: Path, duplicate_kind: str
):
    source = _make_source(tmp_path)
    home = tmp_path / "user-home"
    codex = home / ".codex/skills/leo-ppt-generator"
    legacy = home / ".agents/skills/leo-ppt-generator"
    if duplicate_kind in {"legacy", "dual"}:
        legacy.mkdir(parents=True)
        (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
    if duplicate_kind == "dual":
        codex.mkdir(parents=True)
        (codex / "SKILL.md").write_text("current", encoding="utf-8")
    if duplicate_kind == "visible-backup":
        backup = home / ".agents/skills/leo-ppt-generator.backup-old"
        backup.mkdir(parents=True)
        (backup / "SKILL.md").write_text("backup", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "LEO_INSTALLER_TEST_LOG": str(tmp_path / "duplicate.log"),
            "LEO_INSTALLER_FAIL_ROUTE": "",
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--source",
            str(source),
            "--target",
            str(tmp_path / "custom/leo-ppt-generator"),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "检测到" in result.stderr
    assert "后重试" in result.stderr
    assert not (tmp_path / "custom/leo-ppt-generator").exists()


def _run_windows_installer(
    tmp_path: Path,
    source: Path,
    *extra_args: str,
    fail_route: str = "",
    extra_env: dict[str, str] | None = None,
    target: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Windows installer behavior test")
    target = target or tmp_path / "windows-install-root" / "leo-ppt-generator"
    log = tmp_path / "windows-installer-calls.log"
    environment = os.environ.copy()
    environment["OS"] = "Windows_NT"
    environment["PROCESSOR_ARCHITECTURE"] = "AMD64"
    environment.pop("PROCESSOR_ARCHITEW6432", None)
    environment["LEO_INSTALLER_TEST_LOG"] = str(log)
    environment["LEO_INSTALLER_FAIL_ROUTE"] = fail_route
    environment["USERPROFILE"] = str(tmp_path / "windows-user")
    environment["CODEX_HOME"] = str(tmp_path / "windows-user/.codex")
    environment.update(extra_env or {})
    result = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(WINDOWS_INSTALLER),
            "-Source",
            str(source),
            "-Target",
            str(target),
            *extra_args,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, target, log


def test_windows_installer_stages_bundle_and_verifies_all_routes(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, log = _run_windows_installer(tmp_path, source)

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert log.read_text(encoding="utf-8").splitlines() == [
        "bootstrap",
        "doctor --route generate",
        "doctor --route direct-editable",
        "doctor --route upgrade-full",
        "doctor --route upgrade-selected",
        "onboard --route generate",
    ]
    assert "配置完成，可以开始使用；首次生成图片时验证服务。" in result.stdout
    assert "onboarding[readiness]: usable_unverified" in result.stdout
    assert "重新启动 Codex" in result.stdout
    for stage in ("platform_check", "runtime_ensure", "route_doctor", "activate", "onboarding"):
        assert f"install[{stage}]" in result.stdout


def test_powershell_excludes_development_and_build_artifacts(tmp_path: Path):
    source = _make_source(tmp_path)
    (source / "runtime" / ".venv" / "Scripts").mkdir(parents=True)
    (source / "runtime" / "build").mkdir()
    (source / "runtime" / "dist").mkdir()
    (source / "runtime" / "src" / "fixture.egg-info").mkdir(parents=True)
    cache = source / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "runtime_manager.cpython-312.pyc").write_bytes(b"generated")

    result, target, _ = _run_windows_installer(tmp_path, source)

    assert result.returncode == 0, result.stderr
    assert not (target / "runtime" / ".venv").exists()
    assert not (target / "runtime" / "build").exists()
    assert not (target / "runtime" / "dist").exists()
    assert not (target / "runtime" / "src" / "fixture.egg-info").exists()
    assert not (target / "scripts" / "__pycache__").exists()


def test_concurrent_powershell_installers_allow_exactly_one_activation(tmp_path: Path):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Windows installer behavior test")
    source = _make_source(tmp_path)
    target = tmp_path / "windows-install-root" / "leo-ppt-generator"
    log = tmp_path / "windows-installer-calls.log"
    environment = os.environ.copy()
    environment.update(
        {
            "OS": "Windows_NT",
            "PROCESSOR_ARCHITECTURE": "AMD64",
            "LEO_INSTALLER_TEST_LOG": str(log),
            "LEO_INSTALLER_FAIL_ROUTE": "",
            "LEO_INSTALLER_PAUSE_ENSURE": "0.7",
            "USERPROFILE": str(tmp_path / "windows-user"),
            "CODEX_HOME": str(tmp_path / "windows-user/.codex"),
        }
    )
    environment.pop("PROCESSOR_ARCHITEW6432", None)
    command = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-File",
        str(WINDOWS_INSTALLER),
        "-Source",
        str(source),
        "-Target",
        str(target),
    ]

    first = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.2)
    second = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    results = [first.communicate(timeout=30), second.communicate(timeout=30)]
    returncodes = [first.returncode, second.returncode]

    assert sorted(code == 0 for code in returncodes) == [False, True], results
    assert (target / "SKILL.md").is_file()
    assert not (target / "leo-ppt-generator").exists()


def test_failed_windows_upgrade_keeps_existing_skill_untouched(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "windows-install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, _ = _run_windows_installer(
        tmp_path,
        source,
        "-Upgrade",
        fail_route="upgrade-full",
    )

    assert result.returncode != 0
    assert (target / "VERSION").read_text(encoding="utf-8") == "old"
    assert not _backup_directories(target)


def test_successful_powershell_upgrade_preserves_backup(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "windows-install-root" / "leo-ppt-generator"
    target.mkdir(parents=True)
    (target / "VERSION").write_text("old", encoding="utf-8")

    result, _, _ = _run_windows_installer(tmp_path, source, "-Upgrade")

    assert result.returncode == 0, result.stderr
    assert (target / "VERSION").read_text(encoding="utf-8") == "new"
    backups = _backup_directories(target)
    assert len(backups) == 1
    assert (backups[0] / "VERSION").read_text(encoding="utf-8") == "old"


def test_powershell_handles_unicode_paths_and_rejects_unexpected_symlink(tmp_path: Path):
    source = _make_source(tmp_path / "来源 包")
    target = tmp_path / "目标 包" / "leo-ppt-generator"
    success, installed, _ = _run_windows_installer(tmp_path, source, target=target)

    linked_source = _make_source(tmp_path / "linked")
    (linked_source / "unsafe-link").symlink_to(linked_source / "VERSION")
    rejected, rejected_target, _ = _run_windows_installer(
        tmp_path / "linked-run",
        linked_source,
    )

    assert success.returncode == 0, success.stderr
    assert (installed / "SKILL.md").is_file()
    assert rejected.returncode != 0
    assert "符号链接" in rejected.stderr
    assert not rejected_target.exists()


def test_powershell_duplicate_skill_blocks_before_candidate_activation(tmp_path: Path):
    source = _make_source(tmp_path)
    user = tmp_path / "windows-user"
    duplicate = user / ".agents/skills/leo-ppt-generator"
    duplicate.mkdir(parents=True)
    (duplicate / "SKILL.md").write_text("duplicate", encoding="utf-8")

    result, target, log = _run_windows_installer(tmp_path, source)

    assert result.returncode != 0
    assert "检测到另一个活动 Skill" in result.stderr
    assert "后重试" in result.stderr
    assert not target.exists()
    assert not log.exists()


def test_powershell_installer_delegates_python_resolution_to_bundle_launcher(
    tmp_path: Path,
):
    source = _make_source(tmp_path)
    (source / "scripts/leo-bootstrap.ps1").write_text(
        """param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ManagerArguments)
Add-Content -LiteralPath $env:LEO_INSTALLER_TEST_LOG -Value ($ManagerArguments -join ' ')
if ($ManagerArguments[0] -eq 'bootstrap') {
  '{"protocol":"leo-ppt-bootstrap/v1","status":"ready","runtime_identity":"fixture","cli_reference":"fixture-cli"}'
} else {
  '{"status":"ready","reason_code":"ready"}'
}
""",
        encoding="utf-8",
    )

    result, target, _ = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"PATH": ""},
    )

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()


def test_powershell_remote_zip_path_installs_from_deterministic_local_server(tmp_path: Path):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Windows installer behavior test")
    source = _make_source(tmp_path / "bundle")
    server_root = tmp_path / "server"
    server_root.mkdir()
    archive = server_root / "main"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                relative = path.relative_to(source).as_posix()
                bundle.write(
                    path,
                    f"leo-ppt-generator-test/skills/leo-ppt-generator/{relative}",
                )

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args, **kwargs: QuietHandler(*args, directory=str(server_root), **kwargs),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        installer = tmp_path / "install.ps1"
        body = WINDOWS_INSTALLER.read_text(encoding="utf-8").replace(
            "https://codeload.github.com/sunrain520/leo-ppt-generator/zip",
            f"http://127.0.0.1:{server.server_port}",
        )
        installer.write_text(body, encoding="utf-8")
        target = tmp_path / "remote-windows-target" / "leo-ppt-generator"
        environment = os.environ.copy()
        environment.update(
            {
                "OS": "Windows_NT",
                "PROCESSOR_ARCHITECTURE": "AMD64",
                "LEO_INSTALLER_TEST_LOG": str(tmp_path / "remote-windows-calls.log"),
                "LEO_INSTALLER_FAIL_ROUTE": "",
                "USERPROFILE": str(tmp_path / "remote-windows-user"),
                "CODEX_HOME": str(tmp_path / "remote-windows-user/.codex"),
            }
        )
        environment.pop("PROCESSOR_ARCHITEW6432", None)

        result = subprocess.run(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(installer),
                "-Ref",
                "main",
                "-Target",
                str(target),
            ],
            cwd=tmp_path,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()


def test_powershell_rejects_wrong_architecture_and_unsafe_ref(tmp_path: Path):
    source = _make_source(tmp_path)
    wrong_arch, target, _ = _run_windows_installer(
        tmp_path / "architecture",
        source,
        extra_env={"PROCESSOR_ARCHITECTURE": "ARM64"},
    )
    unsafe_ref, unsafe_target, _ = _run_windows_installer(
        tmp_path / "ref",
        source,
        "-Ref",
        "../main",
    )

    assert wrong_arch.returncode != 0
    assert "仅支持 Windows x64" in wrong_arch.stderr
    assert not target.exists()
    assert unsafe_ref.returncode != 0
    assert "安全的 Git commit" in unsafe_ref.stderr
    assert not unsafe_target.exists()


def test_powershell_false_green_doctor_output_blocks_activation(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FALSE_GREEN_ROUTE": "direct-editable"},
    )

    assert result.returncode != 0
    assert not target.exists()
    assert "fixture_false_green" in result.stderr


def test_powershell_ensure_failure_leaves_no_target_or_stage(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FAIL_ENSURE": "1"},
    )

    assert result.returncode != 0
    assert not target.exists()
    assert not list(target.parent.glob(".leo-ppt-installer.*"))


def test_powershell_invalid_success_receipt_does_not_activate(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, _ = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_FALSE_GREEN_ENSURE": "1"},
    )

    assert result.returncode != 0
    assert "无效 receipt" in result.stderr
    assert not target.exists()


def test_windows_and_macos_constraints_pin_the_same_dependency_set():
    constraints = ROOT / "skills/leo-ppt-generator/runtime/constraints"

    def pins(path: Path) -> list[str]:
        return [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]

    assert pins(constraints / "py312-win32-amd64.txt") == pins(
        constraints / "py312-darwin-arm64.txt"
    )


@pytest.mark.parametrize("status, eligibility", [("not_configured", "blocked"), ("degraded", "retryable")])
def test_powershell_onboarding_defers_noninteractive_config_without_rollback(
    tmp_path: Path, status: str, eligibility: str
):
    source = _make_source(tmp_path / "来源 空格 '单引号'")
    cli_path = tmp_path / "CLI 路径 '单引号'" / "leo-ppt"

    result, target, log = _run_windows_installer(
        tmp_path,
        source,
        extra_env={
            "LEO_INSTALLER_ONBOARD_STATUS": status,
            "LEO_INSTALLER_ONBOARD_CLI": str(cli_path),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert log.read_text(encoding="utf-8").splitlines()[-1] == "onboard --route generate"
    assert f"onboarding[eligibility]: {eligibility}" in result.stdout
    assert "当前不是交互终端；Skill 已安装，但图片服务尚未就绪。" in result.stdout
    escaped_cli_path = str(cli_path).replace("'", "''")
    assert f"& '{escaped_cli_path}' config" in result.stdout


def test_powershell_onboarding_failure_preserves_activated_skill(tmp_path: Path):
    source = _make_source(tmp_path)

    result, target, log = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_ONBOARD_FAIL": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert log.read_text(encoding="utf-8").splitlines()[-1] == "onboard --route generate"
    assert "onboarding[readiness]: installed_not_ready（reason_code=config_check_unavailable）" in result.stdout


@pytest.mark.parametrize(
    ("status", "readiness", "verification"),
    (
        ("ready", "ready", "真实验证已通过"),
        ("configured_unverified", "usable_unverified", "尚未完成当前图片能力的真实验证"),
    ),
)
def test_powershell_onboarding_activates_before_usable_statuses(
    tmp_path: Path, status: str, readiness: str, verification: str
):
    source = _make_source(tmp_path / f"source {status} 'quoted'")
    target = tmp_path / f"install {status} 'quoted'" / "leo-ppt-generator"

    result, installed, log = _run_windows_installer(
        tmp_path,
        source,
        extra_env={"LEO_INSTALLER_ONBOARD_STATUS": status},
        target=target,
    )

    assert result.returncode == 0, result.stderr
    assert installed == target
    assert (installed / "SKILL.md").is_file()
    assert result.stdout.index("install[activate]") < result.stdout.index("install[onboarding]")
    assert "onboarding[configuration]: 本地配置完成" in result.stdout
    assert f"onboarding[verification]: {verification}" in result.stdout
    assert "onboarding[eligibility]: allowed" in result.stdout
    assert f"onboarding[readiness]: {readiness}" in result.stdout
    assert log.read_text(encoding="utf-8").splitlines()[-1] == "onboard --route generate"


def test_powershell_upgrade_preserves_leo_ppt_home_with_special_paths(tmp_path: Path):
    source = _make_source(tmp_path / "source 'quoted' path")
    target = tmp_path / "install 'quoted' path" / "leo-ppt-generator"
    leo_ppt_home = tmp_path / "配置 'quoted' home"
    leo_ppt_home.mkdir()
    config_file = leo_ppt_home / "config.yaml"
    config_file.write_text("preserve: this-config\n", encoding="utf-8")
    environment = {"LEO_PPT_HOME": str(leo_ppt_home)}

    installed, installed_target, _ = _run_windows_installer(
        tmp_path,
        source,
        extra_env=environment,
        target=target,
    )
    upgraded, upgraded_target, _ = _run_windows_installer(
        tmp_path,
        source,
        "-Upgrade",
        extra_env=environment,
        target=target,
    )

    assert installed.returncode == 0, installed.stderr
    assert upgraded.returncode == 0, upgraded.stderr
    assert installed_target == upgraded_target == target
    assert (target / "SKILL.md").is_file()
    assert config_file.read_text(encoding="utf-8") == "preserve: this-config\n"
