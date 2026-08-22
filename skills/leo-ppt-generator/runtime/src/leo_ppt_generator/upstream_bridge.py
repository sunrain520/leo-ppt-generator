"""通过唯一 ``leo-ppt`` CLI 暴露固定上游的确定性能力。"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .application.routes import RouteContractError, classify_input
from .backend_execution import BackendExecutionContext, build_execution_context

VENDOR_ROOT = Path(__file__).resolve().parent / "_vendor"
CODEX_TOOLS = {
    "assemble": "assemble_ppt.py",
    "image": "image_gen.py",
    "prepare": "prepare_slide_prompts.py",
    "record-blocker": "record_slide_blocker.py",
    "record-dispatch": "record_slide_dispatch.py",
    "record-result": "record_slide_result.py",
    "remove-chroma-key": "remove_chroma_key.py",
    "status": "slide_job_status.py",
}


class UpstreamBridgeError(ValueError):
    """固定上游 bridge 的稳定错误。"""


_EDITABLE_PREPARE_VALUE_OPTIONS = {
    "--out-root",
    "--job-dir",
    "--dpi",
    "--max-concurrent-pages",
    "--image-backend",
}


def _preflight_editable_prepare(arguments: list[str]) -> list[str]:
    forwarded: list[str] = []
    inputs: list[str] = []
    trusted = False
    skip_value = False
    for argument in arguments:
        if skip_value:
            forwarded.append(argument)
            skip_value = False
            continue
        if argument == "--office-trusted":
            trusted = True
            continue
        forwarded.append(argument)
        if argument in _EDITABLE_PREPARE_VALUE_OPTIONS:
            skip_value = True
        elif not argument.startswith("-"):
            inputs.append(argument)
    for source in inputs:
        try:
            classify_input(source, office_trusted=trusted)
        except RouteContractError as exc:
            raise UpstreamBridgeError(str(exc)) from exc
    return forwarded


def _payload(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _current_cli_prefix(capability: str) -> str:
    raw = os.environ.get("LEO_PPT_CLI_PROG")
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if resolved.is_file() and os.access(resolved, os.X_OK):
                return f"{shlex.quote(str(resolved))} upstream {capability} --"
    return f"leo-ppt upstream {capability} --"


def _rewrite_editable_cli(value: Any) -> Any:
    """让上游帮助文本只引用当前唯一 CLI。"""

    replacement = _current_cli_prefix("editable-ppt")
    if isinstance(value, str):
        return re.sub(r"(?<![\w./-])editppt(?=\s)", replacement, value)
    if isinstance(value, list):
        return [_rewrite_editable_cli(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_editable_cli(item) for key, item in value.items()}
    return value


def _rewrite_codex_cli(value: Any) -> Any:
    replacement = f'{_current_cli_prefix("codex-ppt")} image'
    if isinstance(value, str):
        return value.replace("scripts/image_gen.py", replacement)
    if isinstance(value, list):
        return [_rewrite_codex_cli(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_codex_cli(item) for key, item in value.items()}
    return value


def _argument_value(arguments: list[str], option: str) -> str | None:
    try:
        index = arguments.index(option)
    except ValueError:
        return None
    return arguments[index + 1] if index + 1 < len(arguments) else None


def _rewrite_editable_json_tree(root: str | Path) -> None:
    """把 vendor 产物中的命令提示适配到当前唯一 CLI。"""

    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*.json")):
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        rewritten = _rewrite_editable_cli(original)
        if rewritten == original:
            continue
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(rewritten, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        return {
            "returncode": process.returncode,
            "stdout": _payload(stdout or exc.stdout or ""),
            "stderr": "upstream_subprocess_timeout",
            "timed_out": True,
        }
    return {
        "returncode": process.returncode,
        "stdout": _payload(stdout),
        "stderr": stderr.strip() or None,
        "timed_out": False,
    }


def _isolated_env(
    root: str,
    execution: BackendExecutionContext | None = None,
) -> dict[str, str]:
    """只向 vendor 子进程传递已声明的系统/provider 字段。"""
    allowed = {
        "PATH",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "OPENAI_BASE_URL",
        "CODEX_PPT_IMAGE_MODEL",
        "IMAGE_TO_EDITABLE_PPT_IMAGE_MODEL",
        "PADDLE_OCR_TOKEN",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "CODEX_AUTH_FILE": str(Path(root) / "no-codex-auth.json"),
            "CODEX_PPT_HOME": str(Path(root) / "no-codex-ppt-config"),
            "EDITPPT_CONFIG_HOME": str(Path(root) / "no-editppt-config"),
            "IMAGE_TO_EDITABLE_PPT_CLI_PROG": _current_cli_prefix("editable-ppt"),
        }
    )
    if execution is not None:
        env.update(execution.environment)
    else:
        # Legacy direct bridge calls remain fixture/host-only. They must not
        # accidentally inherit ambient provider credentials.
        env.pop("OPENAI_API_KEY", None)
        env.pop("ATLASCLOUD_API_KEY", None)
    return env


def _adapted_configuration_help(command: str) -> str:
    if command == "setup":
        return (
            "setup 已由受管 runtime 替代。请从当前 Skill 安装目录运行 "
            "scripts/runtime_manager.py ensure 或 doctor --route <route>。"
        )
    return (
        "config 已由每个 run 的 backend-contract-v1 替代。凭据只能使用 "
        "env:/host:/keychain: 引用，不接受或保存原始 key/token。"
    )


def run_upstream(
    capability: str,
    arguments: list[str],
    *,
    backend_contract: str | Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """执行固定上游入口，不依赖旧 Skill、旧 CLI 或 PATH。"""

    forwarded = list(arguments)
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    if capability == "codex-ppt":
        if not forwarded:
            raise UpstreamBridgeError("upstream_tool_required")
        tool = forwarded.pop(0)
        try:
            script_name = CODEX_TOOLS[tool]
        except KeyError as exc:
            raise UpstreamBridgeError("unknown_upstream_tool") from exc
        script = VENDOR_ROOT / "codex_ppt" / script_name
        with tempfile.TemporaryDirectory(prefix="leo-ppt-upstream-") as isolated:
            execution = (
                build_execution_context(backend_contract, isolated)
                if backend_contract is not None
                else None
            )
            result = _run(
                [sys.executable, str(script), *forwarded],
                env=_isolated_env(isolated, execution),
                timeout_seconds=execution.timeout_seconds if execution else timeout_seconds,
            )
        if execution is not None:
            result["execution_receipt"] = dict(execution.receipt)
        result["stdout"] = _rewrite_codex_cli(result["stdout"])
        result["stderr"] = _rewrite_codex_cli(result["stderr"])
        result.update({"upstream": capability, "tool": tool})
        return result
    if capability == "editable-ppt":
        if forwarded[:1] in (["setup"], ["config"]):
            command = forwarded[0]
            if forwarded[1:] in ([], ["--help"], ["-h"]):
                return {
                    "returncode": 0,
                    "stdout": _adapted_configuration_help(command),
                    "stderr": None,
                    "upstream": capability,
                    "tool": command,
                    "disposition": "adapted",
                }
            raise UpstreamBridgeError(
                "upstream_setup_replaced_by_runtime_manager"
                if command == "setup"
                else "raw_credential_configuration_forbidden"
            )
        if forwarded[:1] == ["prepare"]:
            forwarded = ["prepare", *_preflight_editable_prepare(forwarded[1:])]
        script = VENDOR_ROOT / "editable_ppt" / "editppt" / "cli.py"
        with tempfile.TemporaryDirectory(prefix="leo-ppt-upstream-") as isolated:
            execution = (
                build_execution_context(backend_contract, isolated)
                if backend_contract is not None
                else None
            )
            result = _run(
                [sys.executable, str(script), *forwarded],
                env=_isolated_env(isolated, execution),
                timeout_seconds=execution.timeout_seconds if execution else timeout_seconds,
            )
        if execution is not None:
            result["execution_receipt"] = dict(execution.receipt)
        if result["returncode"] == 0 and forwarded[:1] == ["prepare"]:
            job_dir = _argument_value(forwarded, "--job-dir")
            if job_dir:
                _rewrite_editable_json_tree(job_dir)
        result["stdout"] = _rewrite_editable_cli(result["stdout"])
        result["stderr"] = _rewrite_editable_cli(result["stderr"])
        result.update({"upstream": capability, "tool": forwarded[0] if forwarded else "help"})
        return result
    raise UpstreamBridgeError("unknown_upstream")
