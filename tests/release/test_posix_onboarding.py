from __future__ import annotations

import os
import pty
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.sh"
POSIX_LAUNCHER = ROOT / "skills/leo-ppt-generator/scripts/leo-ppt"


def _make_source(tmp_path: Path) -> Path:
    source = tmp_path / "source" / "leo-ppt-generator"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: leo-ppt-generator\n---\n", encoding="utf-8")
    (source / "VERSION").write_text("test", encoding="utf-8")
    (scripts / "runtime_manager.py").write_text(
        """from __future__ import annotations
import json
import os
import sys
from pathlib import Path

log = Path(os.environ["LEO_INSTALLER_TEST_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")

if sys.argv[1:] == ["bootstrap"]:
    print(json.dumps({
        "protocol": "leo-ppt-bootstrap/v1",
        "status": "ready",
        "runtime_identity": "fixture",
        "cli_reference": str(Path(__file__).with_name("fixture-cli.sh")),
    }))
    raise SystemExit(0)

if sys.argv[1:] == ["print-cli"]:
    print(Path(__file__).with_name("fixture-cli.sh"))
    raise SystemExit(0)

if len(sys.argv) == 4 and sys.argv[1:3] == ["doctor", "--route"]:
    print(json.dumps({"status": "ready", "reason_code": "ready"}))
    raise SystemExit(0)

if sys.argv[1:] == ["onboard", "--route", "generate"]:
    status = os.environ.get("LEO_ONBOARD_STATUS", "configured_unverified")
    readiness = os.environ.get("LEO_ONBOARD_READINESS", "usable_unverified")
    eligibility = os.environ.get("LEO_ONBOARD_ELIGIBILITY", "allowed")
    configuration = os.environ.get("LEO_ONBOARD_CONFIGURATION", "locally_configured")
    verification = os.environ.get("LEO_ONBOARD_VERIFICATION", "not_run")
    print(json.dumps({
        "status": status,
        "configuration_state": configuration,
        "verification": {"status": verification},
        "execution_eligibility": eligibility,
        "installation_readiness": readiness,
        "reason_code": os.environ.get("LEO_ONBOARD_REASON", "provider_verification_not_run"),
        "cli_reference": str(Path(__file__).with_name("fixture-cli.sh")),
    }))
    raise SystemExit(0)

raise SystemExit(97)
""",
        encoding="utf-8",
    )
    (scripts / "leo-bootstrap.sh").write_text(
        '#!/bin/sh\nexec python3 "$(dirname "$0")/runtime_manager.py" "$@"\n',
        encoding="utf-8",
    )
    (scripts / "leo-bootstrap.sh").chmod(0o755)
    shutil.copy2(POSIX_LAUNCHER, scripts / "leo-ppt")
    (scripts / "leo-ppt").chmod(0o755)
    (scripts / "fixture-cli.sh").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >>"$LEO_INSTALLER_TEST_LOG"\n'
        'if [ "$1" = "config" ]; then exit "${LEO_CONFIG_EXIT:-0}"; fi\n',
        encoding="utf-8",
    )
    (scripts / "fixture-cli.sh").chmod(0o755)
    runtime = source / "runtime"
    runtime.mkdir()
    (runtime / "bootstrap-lock.json").write_text("{}\n", encoding="utf-8")
    return source


def _environment(tmp_path: Path, log: Path, **overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path / "home"),
            "CODEX_HOME": str(tmp_path / "home/.codex"),
            "LEO_INSTALLER_TEST_LOG": str(log),
            **overrides,
        }
    )
    return environment


def _command(source: Path, target: Path) -> list[str]:
    return [
        "bash",
        str(INSTALLER),
        "--source",
        str(source),
        "--target",
        str(target),
    ]


def test_posix_onboarding_reports_local_state_without_waiting_for_non_tty(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "calls.log"

    result = subprocess.run(
        _command(source, target),
        cwd=ROOT,
        env=_environment(
            tmp_path,
            log,
            LEO_ONBOARD_STATUS="not_configured",
            LEO_ONBOARD_READINESS="installed_not_ready",
            LEO_ONBOARD_ELIGIBILITY="blocked",
            LEO_ONBOARD_CONFIGURATION="not_configured",
            LEO_ONBOARD_VERIFICATION="not_run",
            LEO_ONBOARD_REASON="credential_input_channel_unavailable",
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

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
    assert "安装状态：已安装" in result.stdout
    assert "配置状态：not_configured" in result.stdout
    assert "真实验证状态：未验证（尚未生成过图片）" in result.stdout
    assert "执行资格：blocked" in result.stdout
    assert "安装可用性：installed_not_ready" in result.stdout
    assert "未检测到交互终端；不会等待配置输入或发起可能计费的验证。" in result.stdout
    assert " config" in result.stdout


def test_posix_onboarding_keeps_activated_skill_after_tty_configuration_failure(
    tmp_path: Path,
):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "calls.log"
    master, slave = pty.openpty()
    process = subprocess.Popen(
        _command(source, target),
        cwd=ROOT,
        env=_environment(
            tmp_path,
            log,
            LEO_ONBOARD_STATUS="not_configured",
            LEO_ONBOARD_READINESS="installed_not_ready",
            LEO_ONBOARD_ELIGIBILITY="blocked",
            LEO_ONBOARD_CONFIGURATION="not_configured",
            LEO_ONBOARD_VERIFICATION="not_run",
            LEO_ONBOARD_REASON="credential_input_channel_unavailable",
            LEO_CONFIG_EXIT="23",
        ),
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    try:
        os.write(master, b"y\n")
        stdout, stderr = process.communicate(timeout=5)
    finally:
        os.close(master)

    assert process.returncode == 0, stderr
    assert (target / "SKILL.md").is_file()
    assert log.read_text(encoding="utf-8").splitlines() == [
        "bootstrap",
        "doctor --route generate",
        "doctor --route direct-editable",
        "doctor --route upgrade-full",
        "doctor --route upgrade-selected",
        "onboard --route generate",
        "config",
        "onboard --route generate",
    ]
    assert "正在启动配置向导；任何可能计费的验证仍需在向导中单独确认。" in stdout
    assert "配置向导未完成；Skill 仍保持已安装状态。" in stderr
    assert "安装状态：已安装" in stdout
    assert "安装可用性：installed_not_ready" in stdout


def test_posix_onboarding_activates_before_ready_and_usable_reports(tmp_path: Path):
    scenarios = (
        ("ready", "ready", "allowed", "locally_configured", "passed"),
        (
            "configured_unverified",
            "usable_unverified",
            "allowed",
            "locally_configured",
            "not_run",
        ),
    )

    # install.sh 的 verification_label 把状态值映射为用户可见中文标签。
    verification_label = {
        "passed": "已通过真实验证",
        "failed": "真实验证失败",
        "stale": "已过期（配置/模型/凭据已变化，需重新验证）",
        "not_run": "未验证（尚未生成过图片）",
    }

    for status, readiness, eligibility, configuration, verification in scenarios:
        source = _make_source(tmp_path / f"source {status} 'quoted'")
        target = tmp_path / f"install {status} 'quoted'" / "leo-ppt-generator"
        log = tmp_path / f"{status}.log"

        result = subprocess.run(
            _command(source, target),
            cwd=ROOT,
            env=_environment(
                tmp_path,
                log,
                LEO_ONBOARD_STATUS=status,
                LEO_ONBOARD_READINESS=readiness,
                LEO_ONBOARD_ELIGIBILITY=eligibility,
                LEO_ONBOARD_CONFIGURATION=configuration,
                LEO_ONBOARD_VERIFICATION=verification,
                LEO_PPT_BIN_DIR=str(tmp_path / f"bin-{status}"),
            ),
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

        assert result.returncode == 0, result.stderr
        assert (target / "SKILL.md").is_file()
        assert result.stdout.index("install[activate]") < result.stdout.index("install[onboarding]")
        assert f"配置状态：{configuration}" in result.stdout
        assert f"真实验证状态：{verification_label[verification]}" in result.stdout
        assert f"执行资格：{eligibility}" in result.stdout
        assert f"安装可用性：{readiness}" in result.stdout
        assert log.read_text(encoding="utf-8").splitlines()[-1] == "onboard --route generate"


def test_posix_onboarding_does_not_wait_for_configuration_without_tty(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "calls.log"

    result = subprocess.run(
        _command(source, target),
        cwd=ROOT,
        env=_environment(
            tmp_path,
            log,
            LEO_ONBOARD_STATUS="not_configured",
            LEO_ONBOARD_READINESS="installed_not_ready",
            LEO_ONBOARD_ELIGIBILITY="blocked",
            LEO_ONBOARD_CONFIGURATION="not_configured",
            LEO_ONBOARD_VERIFICATION="not_run",
            LEO_ONBOARD_REASON="credential_input_channel_unavailable",
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert (target / "SKILL.md").is_file()
    assert "未检测到交互终端；不会等待配置输入或发起可能计费的验证。" in result.stdout
    assert "config" not in log.read_text(encoding="utf-8").splitlines()


def test_posix_onboarding_tty_defer_preserves_activated_skill(tmp_path: Path):
    source = _make_source(tmp_path)
    target = tmp_path / "install-root" / "leo-ppt-generator"
    log = tmp_path / "calls.log"
    master, slave = pty.openpty()
    process = subprocess.Popen(
        _command(source, target),
        cwd=ROOT,
        env=_environment(
            tmp_path,
            log,
            LEO_ONBOARD_STATUS="not_configured",
            LEO_ONBOARD_READINESS="installed_not_ready",
            LEO_ONBOARD_ELIGIBILITY="blocked",
            LEO_ONBOARD_CONFIGURATION="not_configured",
            LEO_ONBOARD_VERIFICATION="not_run",
            LEO_ONBOARD_REASON="credential_input_channel_unavailable",
        ),
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    try:
        os.write(master, b"n\n")
        stdout, stderr = process.communicate(timeout=5)
    finally:
        os.close(master)

    assert process.returncode == 0, stderr
    assert (target / "SKILL.md").is_file()
    assert "已推迟配置；Skill 仍保持已安装状态。" in stdout
    assert "config" not in log.read_text(encoding="utf-8").splitlines()


def test_posix_upgrade_preserves_leo_ppt_home_with_special_paths(tmp_path: Path):
    source = _make_source(tmp_path / "source 'quoted' path")
    target = tmp_path / "install 'quoted' path" / "leo-ppt-generator"
    log = tmp_path / "calls.log"
    leo_ppt_home = tmp_path / "配置 'quoted' home"
    leo_ppt_home.mkdir()
    config_file = leo_ppt_home / "config.yaml"
    config_file.write_text("preserve: this-config\n", encoding="utf-8")
    environment = _environment(tmp_path, log, LEO_PPT_HOME=str(leo_ppt_home))

    installed = subprocess.run(
        _command(source, target),
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    upgraded = subprocess.run(
        [*_command(source, target), "--upgrade"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert installed.returncode == 0, installed.stderr
    assert upgraded.returncode == 0, upgraded.stderr
    assert (target / "SKILL.md").is_file()
    assert config_file.read_text(encoding="utf-8") == "preserve: this-config\n"
