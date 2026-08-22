#!/usr/bin/env python3
"""安装、验证和选择 leo-ppt-generator 的不可变 Python runtime。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

IDENTITY_SCHEMA_VERSION = 1
TERMINAL_RUN_STATUSES = {"completed", "cancelled"}
BOOTSTRAP_PROTOCOL = "leo-ppt-bootstrap/v1"


class RuntimeManagerError(RuntimeError):
    reason_code = "runtime_manager_error"


class RuntimeInstallError(RuntimeManagerError):
    reason_code = "runtime_install_failed"


class RuntimeInUseError(RuntimeManagerError):
    reason_code = "runtime_in_use"


class RuntimeIncompatibleError(RuntimeManagerError):
    reason_code = "runtime_incompatible"


class OperationConflictError(RuntimeManagerError):
    reason_code = "operation_conflict"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> str:
    if not root.exists():
        return sha256_bytes(b"missing")
    digest = hashlib.sha256()
    ignored = {"__pycache__", ".pytest_cache", ".venv", "build", "dist"}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if any(part in ignored or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fsync_directory(path: Path) -> None:
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


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class InstallLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.handle is None:
            return
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def platform_lock_name() -> str:
    machine = platform.machine().lower().replace(" ", "-") or "unknown"
    system = sys.platform.lower().replace(" ", "-")
    return f"py{sys.version_info.major}{sys.version_info.minor}-{system}-{machine}.txt"


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


def venv_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "venv/Scripts/python.exe"
    return runtime_dir / "venv/bin/python"


def venv_cli(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "venv/Scripts/leo-ppt.exe"
    return runtime_dir / "venv/bin/leo-ppt"


class RuntimeManager:
    def __init__(self, bundle_root: Path, home: Path | None = None) -> None:
        self.bundle_root = Path(bundle_root).resolve()
        self.runtime_source = self.bundle_root / "runtime"
        self.upstreams_path = self.bundle_root / "upstreams.yaml"
        self.patches_path = self.bundle_root / "patches"
        self.home = (Path(home) if home is not None else default_home()).resolve()
        self.runtimes_dir = self.home / "runtimes"
        self.quarantine_dir = self.home / "quarantine"
        self.operations_dir = self.home / "operations"
        self.current_path = self.home / "current"
        self.lock_path = self.home / "install.lock"

    @property
    def constraint_path(self) -> Path:
        return self.runtime_source / "constraints" / platform_lock_name()

    def identity_payload(self) -> dict[str, Any]:
        if not (self.runtime_source / "pyproject.toml").is_file():
            raise RuntimeIncompatibleError(
                f"缺少 runtime/pyproject.toml：{self.runtime_source}"
            )
        if not self.constraint_path.is_file():
            raise RuntimeIncompatibleError(
                f"当前 Python/平台缺少发布 lock：{self.constraint_path.name}"
            )
        upstreams = self.upstreams_path
        patches = self.patches_path
        if not upstreams.is_file():
            raise RuntimeIncompatibleError(f"缺少上游身份清单：{upstreams}")
        return {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "runtime_source_hash": hash_tree(self.runtime_source),
            "upstreams_hash": sha256_file(upstreams),
            "patches_hash": hash_tree(patches),
            "dependency_lock_hash": sha256_file(self.constraint_path),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": sys.platform,
            "machine": platform.machine().lower(),
        }

    def identity(self) -> str:
        payload = self.identity_payload()
        return sha256_bytes(canonical_json(payload).encode("utf-8"))[:32]

    def _runtime_dir(self, identity: str) -> Path:
        if not identity or any(character not in "0123456789abcdef" for character in identity):
            raise RuntimeIncompatibleError(f"非法 runtime identity：{identity!r}")
        return self.runtimes_dir / identity

    def _healthy(self, identity: str) -> bool:
        runtime_dir = self._runtime_dir(identity)
        receipt = runtime_dir / "runtime.json"
        cli = venv_cli(runtime_dir)
        python = venv_python(runtime_dir)
        if not receipt.is_file() or not cli.is_file() or not python.is_file():
            return False
        try:
            data = read_json(receipt)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if data.get("runtime_identity") != identity:
            return False
        try:
            result = subprocess.run(
                [str(cli), "--version"],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _quarantine(self, path: Path, reason: str, operation_id: str) -> Path:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        target = self.quarantine_dir / f"{path.name}.{stamp}.{operation_id}.{reason}"
        counter = 0
        while target.exists():
            counter += 1
            target = target.with_name(f"{target.name}.{counter}")
        os.replace(path, target)
        fsync_directory(self.quarantine_dir)
        fsync_directory(path.parent)
        return target

    def _cleanup_half_installs(self, identity: str, operation_id: str) -> list[str]:
        quarantined = []
        if not self.runtimes_dir.exists():
            return quarantined
        for path in sorted(self.runtimes_dir.glob(f".{identity}.*.installing")):
            quarantined.append(
                str(self._quarantine(path, "half-install", operation_id))
            )
        return quarantined

    def _install(self, identity: str, operation_id: str) -> dict[str, Any]:
        runtime_dir = self._runtime_dir(identity)
        if runtime_dir.exists():
            self._quarantine(runtime_dir, "invalid-runtime", operation_id)
        runtime_dir.mkdir(parents=True)
        fsync_directory(runtime_dir.parent)
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(runtime_dir / "venv")],
                text=True,
                capture_output=True,
                timeout=180,
                check=True,
            )
            python = venv_python(runtime_dir)
            with tempfile.TemporaryDirectory(
                prefix=".runtime-source-", dir=runtime_dir
            ) as install_root:
                install_source = Path(install_root) / "runtime"
                shutil.copytree(
                    self.runtime_source,
                    install_source,
                    ignore=shutil.ignore_patterns(
                        ".venv",
                        "__pycache__",
                        "build",
                        "dist",
                        "*.egg-info",
                        "*.pyc",
                        "*.pyo",
                    ),
                )
                install = subprocess.run(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "--no-input",
                        "--constraint",
                        str(self.constraint_path),
                        str(install_source),
                    ],
                    text=True,
                    capture_output=True,
                    timeout=900,
                    check=False,
                )
            if install.returncode != 0:
                raise RuntimeInstallError(
                    "runtime 依赖安装失败："
                    + (install.stderr.strip() or install.stdout.strip())[-4000:]
                )
            cli = venv_cli(runtime_dir)
            smoke = subprocess.run(
                [str(cli), "--version"],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            if smoke.returncode != 0:
                raise RuntimeInstallError(
                    "runtime smoke 失败："
                    + (smoke.stderr.strip() or smoke.stdout.strip())[-2000:]
                )
            receipt = {
                "schema_version": 1,
                "runtime_identity": identity,
                "identity_payload": self.identity_payload(),
                "operation_id": operation_id,
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "cli_version": smoke.stdout.strip(),
                "dependency_install_requires_network_or_cache": True,
            }
            atomic_write_json(runtime_dir / "runtime.json", receipt)
            if not self._healthy(identity):
                raise RuntimeInstallError("runtime 写入 receipt 后健康检查失败")
            return receipt
        except Exception as error:
            if runtime_dir.exists():
                self._quarantine(runtime_dir, "install-failed", operation_id)
            if isinstance(error, RuntimeManagerError):
                raise
            if isinstance(error, subprocess.TimeoutExpired):
                raise RuntimeInstallError(f"runtime 安装超时：{error}") from error
            if isinstance(error, subprocess.CalledProcessError):
                detail = error.stderr or error.stdout or str(error)
                raise RuntimeInstallError(f"runtime 环境创建失败：{detail}") from error
            raise RuntimeInstallError(str(error)) from error

    def _switch_current(self, identity: str, operation_id: str) -> dict[str, Any]:
        if not self._healthy(identity):
            raise RuntimeIncompatibleError(f"不能切换到未验证 runtime：{identity}")
        value = {
            "schema_version": 1,
            "runtime_identity": identity,
            "runtime_dir": str(self._runtime_dir(identity)),
            "cli": str(venv_cli(self._runtime_dir(identity))),
            "operation_id": operation_id,
            "switched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        atomic_write_json(self.current_path, value)
        return value

    def _operation_path(self, operation_id: str) -> Path:
        safe = "".join(character for character in operation_id if character.isalnum() or character in "-_")
        if not safe or safe != operation_id:
            raise OperationConflictError(f"非法 operation id：{operation_id!r}")
        return self.operations_dir / f"{safe}.json"

    def ensure(self, operation_id: str | None = None) -> dict[str, Any]:
        operation_id = operation_id or uuid.uuid4().hex
        identity = self.identity()
        fingerprint = sha256_bytes(
            canonical_json({"action": "ensure", "identity": identity}).encode("utf-8")
        )
        with InstallLock(self.lock_path):
            operation_path = self._operation_path(operation_id)
            if operation_path.exists():
                try:
                    existing = read_json(operation_path)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    raise OperationConflictError(
                        f"operation receipt 损坏或不可读：{operation_path}"
                    ) from error
                if existing.get("request_fingerprint") != fingerprint:
                    raise OperationConflictError(
                        f"operation id 已绑定其他请求：{operation_id}"
                    )
                if existing.get("status") == "completed":
                    return existing["result"]
            self.runtimes_dir.mkdir(parents=True, exist_ok=True)
            quarantined = self._cleanup_half_installs(identity, operation_id)
            if self._healthy(identity):
                outcome = "reused"
            else:
                self._install(identity, operation_id)
                outcome = "installed"
            current = self._switch_current(identity, operation_id)
            result = {
                "schema_version": 1,
                "operation_id": operation_id,
                "outcome": outcome,
                "runtime_identity": identity,
                "runtime_dir": current["runtime_dir"],
                "cli": current["cli"],
                "quarantined": quarantined,
            }
            atomic_write_json(
                operation_path,
                {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_fingerprint": fingerprint,
                    "status": "completed",
                    "result": result,
                },
            )
            return result

    def current(self) -> dict[str, Any]:
        if not self.current_path.is_file():
            raise RuntimeIncompatibleError("尚无 current runtime；先运行 ensure")
        value = read_json(self.current_path)
        identity = value.get("runtime_identity")
        if not isinstance(identity, str) or not self._healthy(identity):
            raise RuntimeIncompatibleError("current runtime 不完整或验证失败")
        return value

    def print_cli(self) -> str:
        return str(venv_cli(self._runtime_dir(self.current()["runtime_identity"])))

    def bootstrap(
        self,
        *,
        python_source: str,
        platform_name: str,
        architecture: str,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        if python_source not in {
            "system",
            "uv-existing",
            "uv-bootstrap",
            "private-python",
        }:
            raise RuntimeIncompatibleError("bootstrap python source 非法")
        if platform_name not in {"macos", "windows", "linux"}:
            raise RuntimeIncompatibleError("bootstrap platform 非法")
        if not architecture or len(architecture) > 64:
            raise RuntimeIncompatibleError("bootstrap architecture 非法")
        ensured = self.ensure(operation_id)
        return {
            "protocol": BOOTSTRAP_PROTOCOL,
            "schema_version": 1,
            "platform": platform_name,
            "architecture": architecture,
            "python_source": python_source,
            "runtime_outcome": ensured["outcome"],
            "runtime_identity": ensured["runtime_identity"],
            "cli_reference": ensured["cli"],
            "stage": "complete",
            "status": "ready",
            "reason_code": "bootstrap_ready",
            "primary_action": None,
            "details": {
                "operation_id": ensured["operation_id"],
                "quarantined": ensured["quarantined"],
            },
        }

    def doctor(self, route: str | None = None) -> dict[str, Any]:
        current = self.current()
        command = [self.print_cli(), "doctor", "--json"]
        if route:
            command.extend(["--route", route])
        try:
            result = subprocess.run(
                command, text=True, capture_output=True, timeout=60, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            cli_report = {
                "status": "blocked",
                "reason_code": "cli_doctor_unavailable",
                "message": str(exc),
            }
            exit_code = None
        else:
            exit_code = result.returncode
            try:
                cli_report = json.loads(result.stdout)
            except json.JSONDecodeError:
                cli_report = {
                    "status": "blocked",
                    "reason_code": "invalid_cli_doctor_output",
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                }
            if not isinstance(cli_report, dict):
                cli_report = {
                    "status": "blocked",
                    "reason_code": "invalid_cli_doctor_output",
                }
        passed = exit_code == 0 and cli_report.get("status") == "ready"
        return {
            "schema_version": 1,
            "status": "ready" if passed else "blocked",
            "reason_code": "ready" if passed else cli_report.get("reason_code", "cli_doctor_failed"),
            "runtime_identity": current["runtime_identity"],
            "runtime_status": "healthy",
            "cli_exit_code": exit_code,
            "cli_report": cli_report,
        }

    def rollback(self, identity: str, operation_id: str | None = None) -> dict[str, Any]:
        operation_id = operation_id or uuid.uuid4().hex
        with InstallLock(self.lock_path):
            current = self._switch_current(identity, operation_id)
            return {
                "schema_version": 1,
                "operation_id": operation_id,
                "outcome": "rolled_back",
                **current,
            }

    def active_run_refs(self, identity: str, runs_root: Path) -> list[str]:
        references = []
        if not runs_root.exists():
            return references
        for run_file in sorted(runs_root.rglob("run.json")):
            try:
                run = read_json(run_file)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise RuntimeInUseError(
                    f"无法确认损坏或不可读 run 是否引用 runtime：{run_file}"
                ) from error
            if (
                run.get("runtime_identity") == identity
                and run.get("status") not in TERMINAL_RUN_STATUSES
            ):
                references.append(str(run_file))
        return references

    def remove(self, identity: str, runs_root: Path) -> dict[str, Any]:
        with InstallLock(self.lock_path):
            references = self.active_run_refs(identity, Path(runs_root))
            if references:
                raise RuntimeInUseError(
                    f"runtime 被未完成 run 引用：{', '.join(references)}"
                )
            if self.current_path.exists():
                try:
                    current = read_json(self.current_path)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    raise RuntimeInUseError(
                        f"无法确认损坏或不可读 current 是否引用 runtime：{self.current_path}"
                    ) from error
                if current.get("runtime_identity") == identity:
                    raise RuntimeInUseError("不能删除 current runtime；先 rollback")
            runtime_dir = self._runtime_dir(identity)
            if not runtime_dir.exists():
                return {"schema_version": 1, "outcome": "not_found", "runtime_identity": identity}
            quarantine = self._quarantine(
                runtime_dir, "removed", uuid.uuid4().hex
            )
            return {
                "schema_version": 1,
                "outcome": "quarantined",
                "runtime_identity": identity,
                "quarantine": str(quarantine),
            }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    ensure = subcommands.add_parser("ensure")
    ensure.add_argument("--operation-id")
    bootstrap = subcommands.add_parser("bootstrap")
    bootstrap.add_argument("--python-source", required=True)
    bootstrap.add_argument("--bootstrap-platform", required=True)
    bootstrap.add_argument("--bootstrap-architecture", required=True)
    bootstrap.add_argument("--operation-id")
    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--route")
    subcommands.add_parser("print-cli")
    rollback = subcommands.add_parser("rollback")
    rollback.add_argument("--identity", required=True)
    rollback.add_argument("--operation-id")
    remove = subcommands.add_parser("remove")
    remove.add_argument("--identity", required=True)
    remove.add_argument("--runs-root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bundle_root = Path(__file__).resolve().parents[1]
    manager = RuntimeManager(bundle_root)
    try:
        if args.command == "ensure":
            result: Any = manager.ensure(args.operation_id)
        elif args.command == "bootstrap":
            result = manager.bootstrap(
                python_source=args.python_source,
                platform_name=args.bootstrap_platform,
                architecture=args.bootstrap_architecture,
                operation_id=args.operation_id,
            )
        elif args.command == "doctor":
            result = manager.doctor(args.route)
        elif args.command == "print-cli":
            print(manager.print_cli())
            return 0
        elif args.command == "rollback":
            result = manager.rollback(args.identity, args.operation_id)
        else:
            result = manager.remove(args.identity, Path(args.runs_root))
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2 if result.get("status") == "blocked" else 0
    except RuntimeManagerError as error:
        if args.command == "bootstrap":
            print(
                json.dumps(
                    {
                        "protocol": BOOTSTRAP_PROTOCOL,
                        "schema_version": 1,
                        "platform": args.bootstrap_platform,
                        "architecture": args.bootstrap_architecture,
                        "python_source": args.python_source,
                        "runtime_outcome": "not_ready",
                        "runtime_identity": None,
                        "cli_reference": None,
                        "stage": "runtime_ensure",
                        "status": "blocked",
                        "reason_code": error.reason_code,
                        "primary_action": {
                            "id": "retry_runtime_ensure",
                            "command": "重新运行 bundle bootstrap launcher",
                            "verification": "runtime ensure 通过并返回 ready 后继续。",
                        },
                        "details": {"error_type": type(error).__name__},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "blocked",
                    "reason_code": error.reason_code,
                    "message": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
