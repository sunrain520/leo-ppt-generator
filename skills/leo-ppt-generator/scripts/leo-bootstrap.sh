#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
skill_dir="$(cd "$script_dir/.." && pwd -P)"
manifest="$skill_dir/runtime/bootstrap-lock.json"
manager="$script_dir/runtime_manager.py"
home="${LEO_PPT_HOME:-$HOME/Library/Application Support/leo-ppt-generator}"
stage=""
lock_dir=""

stage_event() {
  if [[ "${LEO_PPT_BOOTSTRAP_QUIET:-0}" != "1" ]]; then
    printf 'bootstrap[%s]: %s\n' "$1" "$2" >&2
  fi
}

fail_bootstrap() {
  local reason="$1" action_id="$2" command="$3" verification="$4" current_stage="$5"
  printf '{"architecture":"arm64","cli_reference":null,"details":{},"platform":"macos","primary_action":{"command":"%s","id":"%s","verification":"%s"},"protocol":"leo-ppt-bootstrap/v1","python_source":"unknown","reason_code":"%s","runtime_identity":null,"runtime_outcome":"not_ready","schema_version":1,"stage":"%s","status":"blocked"}\n' \
    "$command" "$action_id" "$verification" "$reason" "$current_stage"
  exit 2
}

cleanup() {
  if [[ -n "${stage:-}" && -d "$stage" ]]; then
    case "$stage" in
      "$home"/.bootstrap-stage.*) rm -rf -- "$stage" ;;
    esac
  fi
  if [[ -n "${lock_dir:-}" && -d "$lock_dir" && -f "$lock_dir/pid" ]] && \
    [[ "$(cat "$lock_dir/pid" 2>/dev/null || true)" == "$$" ]]; then
    rm -rf -- "$lock_dir"
  fi
}
trap cleanup EXIT INT TERM

[[ -f "$manifest" && -f "$manager" ]] || \
  fail_bootstrap "bootstrap_bundle_incomplete" "reinstall_skill" "重新安装 leo-ppt-generator" "bundle 包含 manifest 和 runtime manager 后重试。" "platform_check"

platform="$(uname -s 2>/dev/null || true)"
architecture="$(uname -m 2>/dev/null || true)"
[[ "$platform" == "Darwin" && "$architecture" == "arm64" ]] || \
  fail_bootstrap "bootstrap_platform_unsupported" "use_supported_platform" "在 macOS arm64 或 Windows x64 上安装" "平台匹配后重新运行 bootstrap。" "platform_check"
stage_event "platform_check" "macOS arm64 已确认"

python_bin=""
python_source=""
for candidate in python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
    "$candidate" -c 'import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) and struct.calcsize("P")==8 else 1)' >/dev/null 2>&1; then
    python_bin="$(command -v "$candidate")"
    python_source="system"
    break
  fi
done

if [[ -z "$python_bin" ]]; then
  stage_event "python_resolve" "未找到兼容系统 Python，准备私有 Python"
  mkdir -p "$home" 2>/dev/null || \
    fail_bootstrap "bootstrap_home_unwritable" "choose_writable_home" "设置 LEO_PPT_HOME 为可写目录后重试" "目录可写后重新运行 bootstrap。" "python_resolve"
  lock_dir="$home/bootstrap.lock"
  acquired=0
  for _attempt in $(seq 1 120); do
    if mkdir "$lock_dir" 2>/dev/null; then
      printf '%s\n' "$$" >"$lock_dir/pid"
      acquired=1
      break
    fi
    owner="$(cat "$lock_dir/pid" 2>/dev/null || true)"
    if [[ -n "$owner" ]] && ! kill -0 "$owner" 2>/dev/null; then
      rm -rf -- "$lock_dir"
      continue
    fi
    sleep 0.25
  done
  [[ "$acquired" == "1" ]] || \
    fail_bootstrap "bootstrap_lock_timeout" "retry_bootstrap" "重新运行 leo-bootstrap.sh" "活动 bootstrap 完成后重试。" "python_resolve"

  private_python="$(find "$home/python" -type f -path '*/bin/python3.12' -print -quit 2>/dev/null || true)"
  if [[ -n "$private_python" ]] && "$private_python" -c 'import sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then
    python_bin="$private_python"
    python_source="private-python"
  fi

  if [[ -z "$python_bin" ]]; then
    uv_bin="$(command -v uv 2>/dev/null || true)"
    if [[ -n "$uv_bin" ]] && "$uv_bin" --version 2>/dev/null | grep -Eq '^uv [0-9]+\.[0-9]+\.[0-9]+'; then
      python_source="uv-existing"
    else
    command -v plutil >/dev/null 2>&1 || \
      fail_bootstrap "bootstrap_manifest_parser_missing" "install_system_python" "安装 Python 3.12 后重试" "兼容 Python 可用后重新运行 bootstrap。" "python_resolve"
    uv_version="$(plutil -extract uv_version raw -o - "$manifest" 2>/dev/null || true)"
    url="$(plutil -extract artifacts.macos-arm64.url raw -o - "$manifest" 2>/dev/null || true)"
    expected_sha="$(plutil -extract artifacts.macos-arm64.sha256 raw -o - "$manifest" 2>/dev/null || true)"
    max_bytes="$(plutil -extract artifacts.macos-arm64.max_bytes raw -o - "$manifest" 2>/dev/null || true)"
    executable="$(plutil -extract artifacts.macos-arm64.executable raw -o - "$manifest" 2>/dev/null || true)"
    [[ "$uv_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$expected_sha" =~ ^[0-9a-f]{64}$ && "$max_bytes" =~ ^[0-9]+$ ]] || \
      fail_bootstrap "bootstrap_manifest_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "manifest 通过结构检查后重试。" "python_resolve"
    expected_prefix="https://github.com/astral-sh/uv/releases/download/$uv_version/"
    [[ "$url" == "$expected_prefix"* && "$executable" == "uv-aarch64-apple-darwin/uv" ]] || \
      fail_bootstrap "bootstrap_origin_forbidden" "reinstall_skill" "重新安装 leo-ppt-generator" "manifest origin 恢复为官方固定 HTTPS 地址后重试。" "python_resolve"
    command -v curl >/dev/null 2>&1 && command -v shasum >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 || \
      fail_bootstrap "bootstrap_download_tools_missing" "install_system_python" "安装 Python 3.12 后重试" "兼容 Python 可用后重新运行 bootstrap。" "python_resolve"
    stage="$home/.bootstrap-stage.$$"
    mkdir -m 700 "$stage" 2>/dev/null || \
      fail_bootstrap "bootstrap_home_unwritable" "choose_writable_home" "设置 LEO_PPT_HOME 为可写目录后重试" "目录可写后重新运行 bootstrap。" "python_resolve"
    archive="$stage/uv.tar.gz"
    stage_event "python_resolve" "下载固定 uv $uv_version 工件"
    curl -fsSL --proto '=https' --tlsv1.2 --max-time 120 "$url" -o "$archive" || \
      fail_bootstrap "bootstrap_download_failed" "check_network_and_retry" "检查网络或代理后重新运行 leo-bootstrap.sh" "工件可完整下载后重试。" "python_resolve"
    actual_bytes="$(wc -c <"$archive" | tr -d ' ')"
    [[ "$actual_bytes" =~ ^[0-9]+$ && "$actual_bytes" -gt 0 && "$actual_bytes" -le "$max_bytes" ]] || \
      fail_bootstrap "bootstrap_artifact_size_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "工件大小符合 manifest 后重试。" "python_resolve"
    actual_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
    [[ "$actual_sha" == "$expected_sha" ]] || \
      fail_bootstrap "bootstrap_artifact_hash_mismatch" "stop_and_reinstall" "停止执行并重新安装 leo-ppt-generator" "SHA-256 与 manifest 一致后重试。" "python_resolve"
    tar -tzf "$archive" | grep -Eq '^uv-aarch64-apple-darwin/uv$' || \
      fail_bootstrap "bootstrap_archive_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "归档结构匹配 manifest 后重试。" "python_resolve"
    tar -xzf "$archive" -C "$stage" || \
      fail_bootstrap "bootstrap_extract_failed" "retry_bootstrap" "重新运行 leo-bootstrap.sh" "解压成功后重试。" "python_resolve"
    uv_bin="$stage/$executable"
    chmod 700 "$uv_bin"
      python_source="uv-bootstrap"
    fi

    python_version="$(plutil -extract python_version raw -o - "$manifest" 2>/dev/null || true)"
    [[ "$python_version" =~ ^3\.12\.[0-9]+$ ]] || \
      fail_bootstrap "bootstrap_manifest_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "manifest 包含固定 Python 3.12 patch 后重试。" "python_resolve"
    python_root="$home/python"
    cache_root="$home/bootstrap-cache"
    stage_event "python_resolve" "安装私有 Python $python_version"
    UV_PYTHON_INSTALL_DIR="$python_root" UV_CACHE_DIR="$cache_root" \
      "$uv_bin" python install "$python_version" --install-dir "$python_root" --no-bin --no-config >/dev/null || \
      fail_bootstrap "bootstrap_python_install_failed" "retry_bootstrap" "重新运行 leo-bootstrap.sh" "私有 Python 安装完成后重试。" "python_resolve"
    python_bin="$(UV_PYTHON_INSTALL_DIR="$python_root" UV_CACHE_DIR="$cache_root" \
      "$uv_bin" python find "$python_version" --managed-python --no-project --no-config 2>/dev/null || true)"
    [[ -x "$python_bin" ]] && "$python_bin" -c 'import sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1 || \
      fail_bootstrap "bootstrap_python_invalid" "retry_bootstrap" "重新运行 leo-bootstrap.sh" "私有 Python 通过版本检查后重试。" "python_resolve"
    stage_event "python_resolve" "私有 Python 已就绪"
  else
    stage_event "python_resolve" "复用 Leo 私有 Python 3.12"
  fi
else
  stage_event "python_resolve" "复用兼容系统 Python 3.12"
fi

arguments=("$@")
if [[ "${arguments[0]:-bootstrap}" == "bootstrap" ]]; then
  if ((${#arguments[@]} == 0)); then arguments=(bootstrap); fi
  arguments+=(--python-source "$python_source" --bootstrap-platform macos --bootstrap-architecture arm64)
fi
stage_event "runtime_ensure" "调用受管 runtime manager"
"$python_bin" "$manager" "${arguments[@]}"
