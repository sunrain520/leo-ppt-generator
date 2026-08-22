from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGER_PATH = REPO_ROOT / "skills/leo-ppt-generator/scripts/runtime_manager.py"


def load_manager():
    spec = importlib.util.spec_from_file_location("leo_runtime_manager", MANAGER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(MANAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bundle(
    root: Path,
    version: str = "0.0.1",
    broken: bool = False,
    doctor_blocked: bool = False,
) -> Path:
    bundle = root / f"bundle-{version}"
    runtime = bundle / "runtime"
    package = runtime / "src/fixture_runtime"
    constraints = runtime / "constraints"
    package.mkdir(parents=True)
    constraints.mkdir(parents=True)
    pyproject = (
        "[build-system]\n"
        'requires = ["setuptools>=77", "wheel"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        'name = "fixture-runtime"\n'
        f'version = "{version}"\n'
        'requires-python = ">=3.10"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        'leo-ppt = "fixture_runtime.cli:main"\n\n'
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    if broken:
        pyproject = "[project\ninvalid = true\n"
    (runtime / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (package / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (package / "cli.py").write_text(
        "import json, sys\n"
        "def main():\n"
        "    if '--version' in sys.argv:\n"
        f"        print('{version}'); return 0\n"
        f"    payload = {{'status': {'blocked' if doctor_blocked else 'ready'!r}, "
        f"'reason_code': {'config_invalid' if doctor_blocked else 'ready'!r}}}\n"
        "    print(json.dumps(payload)); return 2 if payload['status'] == 'blocked' else 0\n"
        "if __name__ == '__main__': raise SystemExit(main())\n",
        encoding="utf-8",
    )
    lock_name = load_manager().platform_lock_name()
    (constraints / lock_name).write_text("# empty fixture lock\n", encoding="utf-8")
    (bundle / "upstreams.yaml").write_text(
        "schema_version: 1\nupstreams: {}\n", encoding="utf-8"
    )
    (bundle / "patches").mkdir()
    return bundle


def ensure_worker(manager_path: str, bundle: str, home: str, queue) -> None:
    spec = importlib.util.spec_from_file_location("leo_runtime_manager_child", manager_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.RuntimeManager(Path(bundle), Path(home)).ensure()
    queue.put(result)


class RuntimeManagerTest(unittest.TestCase):
    def test_installed_bundle_ensure_works_from_unrelated_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            scripts = bundle / "scripts"
            scripts.mkdir()
            manager_path = scripts / "runtime_manager.py"
            shutil.copy2(MANAGER_PATH, manager_path)
            unrelated_cwd = root / "unrelated-cwd"
            unrelated_cwd.mkdir()
            env = {
                **os.environ,
                "LEO_PPT_HOME": str(root / "managed-home"),
            }
            completed = subprocess.run(
                [sys.executable, str(manager_path), "ensure"],
                cwd=unrelated_cwd,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("installed", payload["outcome"])

    def test_doctor_wrapper_propagates_blocked_cli_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root, doctor_blocked=True)
            scripts = bundle / "scripts"
            scripts.mkdir()
            manager_path = scripts / "runtime_manager.py"
            shutil.copy2(MANAGER_PATH, manager_path)
            env = {**os.environ, "LEO_PPT_HOME": str(root / "managed-home")}
            installed = subprocess.run(
                [sys.executable, str(manager_path), "ensure"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )
            self.assertEqual(0, installed.returncode, installed.stderr)

            doctor = subprocess.run(
                [sys.executable, str(manager_path), "doctor", "--route", "generate"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            self.assertEqual(2, doctor.returncode)
            payload = json.loads(doctor.stdout)
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("config_invalid", payload["reason_code"])

    def test_doctor_rejects_invalid_output_and_normalizes_timeout(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root), root / "home")
            manager.ensure()

            with mock.patch.object(
                module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="not-json", stderr="bad"),
            ):
                invalid = manager.doctor("generate")
            self.assertEqual("blocked", invalid["status"])
            self.assertEqual("invalid_cli_doctor_output", invalid["reason_code"])

            with (
                mock.patch.object(
                    manager,
                    "current",
                    return_value={"runtime_identity": manager.identity()},
                ),
                mock.patch.object(manager, "print_cli", return_value="/absolute/leo-ppt"),
                mock.patch.object(
                    module.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(["leo-ppt", "doctor"], 60),
                ),
            ):
                timed_out = manager.doctor("generate")
            self.assertEqual("blocked", timed_out["status"])
            self.assertEqual("cli_doctor_unavailable", timed_out["reason_code"])

    def test_identity_is_stable_and_lock_bound(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            manager = module.RuntimeManager(bundle, root / "home")
            first = manager.identity()
            second = manager.identity()
            self.assertEqual(first, second)
            lock = bundle / "runtime/constraints" / module.platform_lock_name()
            lock.write_text("# changed\n", encoding="utf-8")
            self.assertNotEqual(first, manager.identity())

    def test_bootstrap_wraps_ensure_without_taking_runtime_identity_ownership(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root), root / "home")

            result = manager.bootstrap(
                python_source="system",
                platform_name="macos",
                architecture="arm64",
            )

            self.assertEqual("leo-ppt-bootstrap/v1", result["protocol"])
            self.assertEqual("ready", result["status"])
            self.assertEqual("system", result["python_source"])
            self.assertEqual(manager.current()["runtime_identity"], result["runtime_identity"])
            self.assertEqual(manager.print_cli(), result["cli_reference"])
            self.assertIsNone(result["primary_action"])

    def test_install_target_metadata_survives_pre_activation_staging(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged_bundle = make_bundle(root / "stage")
            target = root / "installed/leo-ppt-generator"
            manager = module.RuntimeManager(staged_bundle, root / "home")
            with mock.patch.dict(
                module.os.environ,
                {"LEO_PPT_INSTALL_TARGET": str(target)},
            ):
                manager.ensure()
            current = module.read_json(manager.current_path)
            self.assertEqual(str(target.resolve()), current["bundle_root"])
            self.assertEqual(
                str((target / "scripts/runtime_manager.py").resolve()),
                current["runtime_manager"],
            )

    def test_bootstrap_cli_failure_keeps_bootstrap_result_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root, broken=True)
            scripts = bundle / "scripts"
            scripts.mkdir()
            manager_path = scripts / "runtime_manager.py"
            shutil.copy2(MANAGER_PATH, manager_path)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(manager_path),
                    "bootstrap",
                    "--python-source",
                    "system",
                    "--bootstrap-platform",
                    "macos",
                    "--bootstrap-architecture",
                    "arm64",
                ],
                env={**os.environ, "LEO_PPT_HOME": str(root / "home")},
                text=True,
                capture_output=True,
                check=False,
                timeout=90,
            )

            self.assertEqual(2, completed.returncode)
            payload = json.loads(completed.stderr)
            self.assertEqual("leo-ppt-bootstrap/v1", payload["protocol"])
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("not_ready", payload["runtime_outcome"])
            self.assertEqual("runtime_ensure", payload["stage"])
            self.assertEqual("retry_runtime_ensure", payload["primary_action"]["id"])

    def test_ensure_does_not_mutate_runtime_source_or_change_identity(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            manager = module.RuntimeManager(bundle, root / "home")
            identity_before = manager.identity()

            installed = manager.ensure()

            self.assertEqual(identity_before, installed["runtime_identity"])
            self.assertEqual(identity_before, manager.identity())
            self.assertFalse((bundle / "runtime/build").exists())
            self.assertEqual([], list((bundle / "runtime").rglob("*.egg-info")))
            self.assertEqual("reused", manager.ensure()["outcome"])

    def test_windows_x64_uses_the_published_windows_lock_name(self) -> None:
        module = load_manager()
        with (
            mock.patch.object(module.sys, "platform", "win32"),
            mock.patch.object(module.platform, "machine", return_value="AMD64"),
        ):
            self.assertEqual("py312-win32-amd64.txt", module.platform_lock_name())

    def test_concurrent_ensure_has_one_installer_and_one_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            home = root / "home"
            context = multiprocessing.get_context("spawn")
            queue = context.Queue()
            processes = [
                context.Process(
                    target=ensure_worker,
                    args=(str(MANAGER_PATH), str(bundle), str(home), queue),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(90)
                self.assertEqual(0, process.exitcode)
            results = [queue.get(timeout=5), queue.get(timeout=5)]
            self.assertEqual({"installed", "reused"}, {item["outcome"] for item in results})
            self.assertEqual(1, len(list((home / "runtimes").glob("*/runtime.json"))))

    def test_failed_upgrade_preserves_previous_current(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            good = module.RuntimeManager(make_bundle(root, "0.0.1"), home).ensure()
            current_before = module.read_json(home / "current")
            with self.assertRaises(module.RuntimeInstallError):
                module.RuntimeManager(make_bundle(root, "0.0.2", broken=True), home).ensure()
            self.assertEqual(current_before, module.read_json(home / "current"))
            self.assertEqual(good["runtime_identity"], current_before["runtime_identity"])

    def test_missing_platform_lock_and_corrupt_operation_fail_with_stable_errors(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            manager = module.RuntimeManager(bundle, root / "home")
            manager.constraint_path.unlink()
            with self.assertRaises(module.RuntimeIncompatibleError):
                manager.ensure()

            bundle = make_bundle(root / "second")
            manager = module.RuntimeManager(bundle, root / "second-home")
            operation_id = "fixed-operation"
            operation_path = manager._operation_path(operation_id)
            operation_path.parent.mkdir(parents=True)
            operation_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(module.OperationConflictError):
                manager.ensure(operation_id)

    def test_half_install_is_quarantined_before_reuse(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            manager = module.RuntimeManager(bundle, root / "home")
            identity = manager.identity()
            half = manager.runtimes_dir / f".{identity}.old.installing"
            half.mkdir(parents=True)
            (half / "partial").write_text("x", encoding="utf-8")
            result = manager.ensure()
            self.assertEqual("installed", result["outcome"])
            self.assertFalse(half.exists())
            self.assertTrue(any(manager.quarantine_dir.iterdir()))

    @unittest.skipIf(os.name == "nt", "POSIX 执行权限恢复场景")
    def test_unexecutable_runtime_cli_is_quarantined_and_reinstalled(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root), root / "home")
            installed = manager.ensure()
            cli = Path(installed["cli"])
            cli.chmod(cli.stat().st_mode & ~0o111)

            repaired = manager.ensure()

            self.assertEqual("installed", repaired["outcome"])
            self.assertTrue(os.access(repaired["cli"], os.X_OK))
            self.assertTrue(any(manager.quarantine_dir.iterdir()))

    def test_rollback_and_active_run_removal_guard(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            first = module.RuntimeManager(make_bundle(root, "0.0.1"), home).ensure()
            second = module.RuntimeManager(make_bundle(root, "0.0.2"), home).ensure()
            manager = module.RuntimeManager(root / "bundle-0.0.2", home)
            rolled = manager.rollback(first["runtime_identity"])
            self.assertEqual(first["runtime_identity"], rolled["runtime_identity"])
            self.assertNotEqual(second["runtime_identity"], rolled["runtime_identity"])

            runs = root / "runs/run-active"
            runs.mkdir(parents=True)
            (runs / "run.json").write_text(
                json.dumps(
                    {
                        "runtime_identity": first["runtime_identity"],
                        "status": "waiting_for_worker",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(module.RuntimeInUseError):
                manager.remove(first["runtime_identity"], root / "runs")

    def test_remove_fails_closed_when_run_or_current_metadata_is_corrupt(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            installed = module.RuntimeManager(make_bundle(root), home).ensure()
            manager = module.RuntimeManager(root / "bundle-0.0.1", home)
            corrupt_run = root / "runs/run-corrupt/run.json"
            corrupt_run.parent.mkdir(parents=True)
            corrupt_run.write_text("{not-json", encoding="utf-8")

            with self.assertRaisesRegex(module.RuntimeInUseError, "无法确认.*run"):
                manager.remove(installed["runtime_identity"], root / "runs")

            corrupt_run.unlink()
            manager.current_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(module.RuntimeInUseError, "无法确认.*current"):
                manager.remove(installed["runtime_identity"], root / "runs")

            self.assertTrue(Path(installed["runtime_dir"]).is_dir())

    def test_release_check_compares_remote_and_local_versions(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root, "0.0.1"), root / "home")
            remote = b'[project]\nname = "fixture-runtime"\nversion = "0.0.2"\n'
            with mock.patch.object(module, "_download_raw", return_value=remote):
                result = manager.release_check("v0.0.2")
            self.assertEqual("leo-ppt-update/v1", result["protocol"])
            self.assertEqual("0.0.1", result["current_version"])
            self.assertEqual("0.0.2", result["target_version"])
            self.assertTrue(result["update_available"])

    def test_update_dry_run_never_executes_installer(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root, "0.0.1"), root / "home")
            preview = {
                "protocol": "leo-ppt-update/v1",
                "schema_version": 1,
                "status": "update_available",
                "reason_code": "release_update_available",
                "update_available": True,
            }
            with (
                mock.patch.object(manager, "release_check", return_value=preview),
                mock.patch.object(module.subprocess, "run") as runner,
            ):
                result = manager.update("v0.0.2", dry_run=True)
            runner.assert_not_called()
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["updated"])

    def test_update_runs_installer_non_interactively(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root, "0.0.1"), root / "home")
            preview = {
                "protocol": "leo-ppt-update/v1",
                "schema_version": 1,
                "status": "update_available",
                "reason_code": "release_update_available",
                "update_available": True,
            }
            completed = SimpleNamespace(returncode=0, stdout="updated", stderr="")
            with (
                mock.patch.object(manager, "release_check", return_value=preview),
                mock.patch.object(module, "_download_raw", return_value=b"#!/bin/sh\n"),
                mock.patch.object(module.subprocess, "run", return_value=completed) as runner,
            ):
                result = manager.update("v0.0.2")
            self.assertTrue(result["updated"])
            self.assertIs(runner.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_rollback_without_identity_uses_previous_healthy_runtime(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            first = module.RuntimeManager(make_bundle(root, "0.0.1"), home).ensure()
            manager = module.RuntimeManager(make_bundle(root, "0.0.2"), home)
            manager.ensure()
            rolled = manager.rollback()
            self.assertEqual(first["runtime_identity"], rolled["runtime_identity"])
            self.assertEqual("runtime_rolled_back", rolled["reason_code"])


if __name__ == "__main__":
    unittest.main()

    def test_onboard_returns_installation_readiness_from_config_status(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = make_bundle(root)
            manager = module.RuntimeManager(bundle, root / "home")
            manager.ensure()

            # fixture CLI 无 config 子命令：返回 config_check_unavailable 或
            # cli_path_unresolved，但绝不破坏安装真值。
            result = manager.onboard()
            self.assertIn(
                result["reason_code"],
                {"config_check_unavailable", "config_protocol_invalid",
                 "cli_path_unresolved", "ready", "not_configured"},
            )
            self.assertIn(
                result["installation_readiness"],
                {"installed_not_ready", "usable_unverified", "ready",
                 "configured_unverified"},
            )
            # onboard 不改变 runtime identity。
            self.assertEqual(
                manager.current()["runtime_identity"],
                result.get("cli_reference") and manager.current()["runtime_identity"]
            )

    def test_onboard_without_runtime_returns_cli_path_unresolved(self) -> None:
        module = load_manager()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = module.RuntimeManager(make_bundle(root), root / "home")
            result = manager.onboard()
            self.assertEqual("blocked", result["status"])
            self.assertEqual("cli_path_unresolved", result["reason_code"])
            self.assertEqual("installed_not_ready", result["installation_readiness"])
            self.assertIsNone(result["cli_reference"])
