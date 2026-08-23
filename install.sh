#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="sunrain520/leo-ppt-generator"
DOWNLOAD_BASE="https://codeload.github.com/sunrain520/leo-ppt-generator/tar.gz"
DEFAULT_REF="main"
SKILL_NAME="leo-ppt-generator"

usage() {
  cat <<'EOF'
安装 Leo PPT Generator Skill。

用法：
  bash install.sh [选项]

选项：
  --agents                 安装到 ~/.agents/skills，而不是 Codex 用户目录
  --ref <commit-or-tag>    下载指定 commit 或 tag，默认 main
  --upgrade                验证新版本后替换现有 Skill，并保留旧版本备份
  --source <目录>          从本地 Skill 目录安装（开发与离线验收用）
  --target <目录>          指定完整安装目录（高级用法）
  --bin-dir <目录>         安装稳定 leo-ppt 命令，默认 ~/.local/bin
  -h, --help               显示帮助

默认目标：${CODEX_HOME:-$HOME/.codex}/skills/leo-ppt-generator
EOF
}

fail() {
  printf '安装失败：%s\n' "$*" >&2
  exit 1
}

agents_mode=0
upgrade=0
ref="$DEFAULT_REF"
source_dir=""
target=""
bin_dir="${LEO_PPT_BIN_DIR:-}"

while (($# > 0)); do
  case "$1" in
    --agents)
      agents_mode=1
      shift
      ;;
    --upgrade)
      upgrade=1
      shift
      ;;
    --ref)
      (($# >= 2)) || fail "--ref 缺少值"
      ref="$2"
      shift 2
      ;;
    --source)
      (($# >= 2)) || fail "--source 缺少值"
      source_dir="$2"
      shift 2
      ;;
    --target)
      (($# >= 2)) || fail "--target 缺少值"
      target="$2"
      shift 2
      ;;
    --bin-dir)
      (($# >= 2)) || fail "--bin-dir 缺少值"
      bin_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知选项：$1"
      ;;
  esac
done

if [[ -n "$target" && "$agents_mode" == "1" ]]; then
  fail "--agents 与 --target 不能同时使用"
fi
if [[ ! "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ || "$ref" == *..* ]]; then
  fail "--ref 只能是安全的 Git commit 或 tag 名称"
fi

platform="$(uname -s)"
architecture="$(uname -m)"
if [[ "$platform" != "Darwin" || ( "$architecture" != "arm64" && "$architecture" != "x86_64" ) ]]; then
  fail "当前版本仅支持 macOS arm64/x86_64 或 Windows x64；检测到 ${platform}/${architecture}"
fi
printf 'install[platform_check]: macOS %s 已确认\n' "$architecture"

if [[ -z "$target" ]]; then
  if [[ "$agents_mode" == "1" ]]; then
    target="$HOME/.agents/skills/$SKILL_NAME"
  else
    target="${CODEX_HOME:-$HOME/.codex}/skills/$SKILL_NAME"
  fi
fi
[[ "$(basename "$target")" == "$SKILL_NAME" ]] || \
  fail "安装目录末级名称必须是 $SKILL_NAME"

target_parent="$(dirname "$target")"
mkdir -p "$target_parent"
target_parent="$(cd "$target_parent" && pwd -P)"
target="$target_parent/$SKILL_NAME"

codex_root="${CODEX_HOME:-$HOME/.codex}/skills"
agents_root="$HOME/.agents/skills"
discovery_roots=("$codex_root" "$agents_root")
if [[ -n "${LEO_PPT_EXTRA_DISCOVERY_ROOTS:-}" ]]; then
  IFS=':' read -r -a extra_roots <<< "$LEO_PPT_EXTRA_DISCOVERY_ROOTS"
  for extra_root in "${extra_roots[@]}"; do
    [[ -n "$extra_root" ]] || continue
    discovery_roots+=("$extra_root")
  done
fi
for discovery_root in "${discovery_roots[@]}"; do
  discovered="$discovery_root/$SKILL_NAME"
  if [[ "$discovered" != "$target" && -f "$discovered/SKILL.md" ]]; then
    fail "检测到另一个活动 Skill：${discovered}；请只保留目标 ${target} 后重试"
  fi
  for discovered_backup in "$discovery_root"/$SKILL_NAME.backup-*/SKILL.md; do
    [[ -e "$discovered_backup" ]] || continue
    fail "检测到可被发现的旧备份：$(dirname "$discovered_backup")；请移入非发现目录后重试"
  done
done

stage_root=""
launcher_path=""
launcher_target="$target/scripts/leo-ppt"
launcher_stage=""
launcher_created=0
launcher_committed=0
runtime_switched=0
install_lock="$target_parent/.$SKILL_NAME.install.lock"
lock_acquired=0
cleanup() {
  # 若 bootstrap 已把受管 runtime 的 current 切到新 identity，但 bundle 最终未激活，
  # 则必须把 current 回滚到上一健康 runtime，避免出现“旧 bundle + 新 runtime”的分裂态。
  if [[ "${runtime_switched:-0}" == "1" && "${launcher_committed:-0}" != "1" && \
        -n "${candidate:-}" && -x "${candidate}/scripts/leo-bootstrap.sh" ]]; then
    LEO_PPT_INSTALL_TARGET="${target:-}" "${candidate}/scripts/leo-bootstrap.sh" rollback >/dev/null 2>&1 || true
  fi
  if [[ -n "${launcher_stage:-}" && -L "$launcher_stage" ]]; then
    rm -f -- "$launcher_stage"
  fi
  if [[ "${launcher_created:-0}" == "1" && "${launcher_committed:-0}" != "1" && \
        -L "${launcher_path:-}" && "$(readlink "$launcher_path" 2>/dev/null || true)" == "$launcher_target" ]]; then
    rm -f -- "$launcher_path"
  fi
  if [[ -n "${stage_root:-}" && -d "$stage_root" ]]; then
    case "$stage_root" in
      "$target_parent"/.leo-ppt-installer.*) rm -rf -- "$stage_root" ;;
      *) printf '警告：拒绝清理非安装器临时目录：%s\n' "$stage_root" >&2 ;;
    esac
  fi
  if [[ "${lock_acquired:-0}" == "1" && -d "$install_lock" ]]; then
    case "$install_lock" in
      "$target_parent"/.$SKILL_NAME.install.lock)
        rmdir -- "$install_lock" 2>/dev/null || \
          printf '警告：安装锁未能自动移除：%s\n' "$install_lock" >&2
        ;;
      *) printf '警告：拒绝清理非安装器锁目录：%s\n' "$install_lock" >&2 ;;
    esac
  fi
}
trap cleanup EXIT

if ! mkdir "$install_lock" 2>/dev/null; then
  fail "另一个安装或升级正在操作该目标；若确认没有活动进程，请移除陈旧锁：$install_lock"
fi
lock_acquired=1

if [[ -e "$target" && "$upgrade" != "1" ]]; then
  fail "同名目录已存在：${target}；请先审阅，或明确使用 --upgrade"
fi
if [[ -e "$target" && ! -d "$target" ]]; then
  fail "目标已存在但不是目录：$target"
fi

if [[ -z "$bin_dir" ]]; then
  bin_dir="$HOME/.local/bin"
fi
mkdir -p "$bin_dir" || fail "无法创建用户命令目录：$bin_dir"
bin_dir="$(cd "$bin_dir" && pwd -P)"
launcher_path="$bin_dir/leo-ppt"
launcher_on_path=0
case ":${PATH:-}:" in
  *":$bin_dir:"*) launcher_on_path=1 ;;
esac
launcher_needs_install=1
if [[ -L "$launcher_path" ]]; then
  if [[ "$(readlink "$launcher_path")" == "$launcher_target" ]]; then
    launcher_needs_install=0
  else
    fail "leo-ppt 命令已指向其他位置：${launcher_path}；拒绝覆盖"
  fi
elif [[ -e "$launcher_path" ]]; then
  fail "leo-ppt 命令已存在且不属于当前安装：${launcher_path}；拒绝覆盖"
fi

stage_root="$(mktemp -d "$target_parent/.leo-ppt-installer.XXXXXX")"
if [[ "$launcher_needs_install" == "1" ]]; then
  launcher_stage="$bin_dir/.leo-ppt.$$.installing"
  [[ ! -e "$launcher_stage" && ! -L "$launcher_stage" ]] || \
    fail "launcher 临时路径已存在：$launcher_stage"
  ln -s "$launcher_target" "$launcher_stage" || fail "无法准备 leo-ppt launcher"
fi

if [[ -n "$source_dir" ]]; then
  [[ -d "$source_dir" ]] || fail "本地来源目录不存在：$source_dir"
  source_dir="$(cd "$source_dir" && pwd -P)"
else
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)"
  if [[ -n "$script_dir" && -f "$script_dir/skills/$SKILL_NAME/SKILL.md" ]]; then
    source_dir="$script_dir/skills/$SKILL_NAME"
  else
    command -v curl >/dev/null 2>&1 || fail "缺少 curl，无法下载发布包"
    command -v tar >/dev/null 2>&1 || fail "缺少 tar，无法解压发布包"
    archive="$stage_root/source.tar.gz"
    extract_root="$stage_root/source"
    mkdir -p "$extract_root"
    download_url="$DOWNLOAD_BASE/$ref"
    printf '正在下载 %s@%s…\n' "$REPOSITORY" "$ref"
    curl -fsSL --proto '=https' --tlsv1.2 "$download_url" -o "$archive" || \
      fail "下载失败：$download_url"
    tar -xzf "$archive" -C "$extract_root" || fail "发布包解压失败"
    source_dir="$(find "$extract_root" -type d -path "*/skills/$SKILL_NAME" -print -quit)"
    [[ -n "$source_dir" ]] || fail "发布包中缺少 skills/$SKILL_NAME"
  fi
fi

[[ -f "$source_dir/SKILL.md" ]] || fail "来源缺少 SKILL.md：$source_dir"
[[ -f "$source_dir/scripts/runtime_manager.py" ]] || \
  fail "来源缺少 scripts/runtime_manager.py：$source_dir"
[[ -f "$source_dir/scripts/leo-bootstrap.sh" ]] || \
  fail "来源缺少 scripts/leo-bootstrap.sh：$source_dir"
[[ -f "$source_dir/scripts/leo-ppt" ]] || \
  fail "来源缺少 scripts/leo-ppt：$source_dir"
[[ -f "$source_dir/runtime/bootstrap-lock.json" ]] || \
  fail "来源缺少 runtime/bootstrap-lock.json：$source_dir"

candidate="$stage_root/$SKILL_NAME"
command -v tar >/dev/null 2>&1 || fail "缺少 tar，无法准备安装包"
mkdir -p "$candidate"
tar -C "$source_dir" \
  --exclude='.venv' --exclude='*/.venv' \
  --exclude='__pycache__' --exclude='*/__pycache__' \
  --exclude='build' --exclude='*/build' \
  --exclude='dist' --exclude='*/dist' \
  --exclude='*.egg-info' --exclude='*.pyc' --exclude='*.pyo' \
  -cf - . | tar -C "$candidate" -xf - || fail "准备安装包失败"

unsafe_path="$(find "$candidate" \( -type l -o -type d \( \
  -name third_party -o -name __pycache__ -o -name build -o -name '*.egg-info' \
  -o -name dist \
  \) -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -print -quit)"
[[ -z "$unsafe_path" ]] || fail "安装包包含不允许的目录、生成物或符号链接：$unsafe_path"
chmod 755 "$candidate/scripts/leo-bootstrap.sh" || fail "无法设置 bootstrap launcher 执行权限"
chmod 755 "$candidate/scripts/leo-ppt" || fail "无法设置 leo-ppt launcher 执行权限"

# 在 bootstrap 之前就确定旧 bundle 的备份路径，随 _switch_current 记录进 current 元数据，
# 使 rollback 能把 bundle 与 runtime 一起回退到上一个一致版本（而非只回 venv）。
backup=""
if [[ -e "$target" ]]; then
  backup_root="$target_parent/.$SKILL_NAME-backups"
  mkdir -p "$backup_root"
  backup="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
install_channel="standalone"
if [[ "$agents_mode" == "1" ]]; then
  install_channel="agent-skill"
fi

printf 'install[runtime_ensure]: 正在初始化受管 runtime…\n'
# stdout 保留纯 JSON receipt 供 plutil 解析；stderr（stage 进度事件与失败诊断）
# 保持实时打到终端，避免冷安装下载私有 runtime 时进度不可见。
ensure_log="$stage_root/runtime-ensure.log"
if ! LEO_PPT_INSTALL_TARGET="$target" LEO_PPT_PREVIOUS_BUNDLE_BACKUP="$backup" \
  LEO_PPT_INSTALL_CHANNEL="$install_channel" \
  "$candidate/scripts/leo-bootstrap.sh" bootstrap >"$ensure_log"; then
  cat "$ensure_log" >&2
  fail "runtime 初始化失败；现有 Skill 未被替换"
fi
runtime_switched=1
if [[ "$(plutil -extract protocol raw -o - "$ensure_log" 2>/dev/null || true)" != "leo-ppt-bootstrap/v1" || \
      "$(plutil -extract status raw -o - "$ensure_log" 2>/dev/null || true)" != "ready" || \
      -z "$(plutil -extract runtime_identity raw -o - "$ensure_log" 2>/dev/null || true)" || \
      -z "$(plutil -extract cli_reference raw -o - "$ensure_log" 2>/dev/null || true)" ]]; then
  cat "$ensure_log" >&2
  reason="$(plutil -extract reason_code raw -o - "$ensure_log" 2>/dev/null || true)"
  fail "runtime 初始化返回无效 receipt（reason_code=${reason:-未知}）；现有 Skill 未被替换"
fi
printf 'runtime：就绪\n'

for route in generate direct-editable upgrade-full upgrade-selected; do
  printf 'install[route_doctor]: 正在验证 route：%s…\n' "$route"
  doctor_log="$stage_root/doctor-$route.log"
  if ! "$candidate/scripts/leo-bootstrap.sh" doctor --route "$route" \
    >"$doctor_log"; then
    cat "$doctor_log" >&2
    fail "route 验证失败：${route}；现有 Skill 未被替换"
  fi
  if [[ "$(plutil -extract status raw -o - "$doctor_log" 2>/dev/null || true)" != "ready" || \
        "$(plutil -extract reason_code raw -o - "$doctor_log" 2>/dev/null || true)" != "ready" ]]; then
    cat "$doctor_log" >&2
    reason="$(plutil -extract reason_code raw -o - "$doctor_log" 2>/dev/null || true)"
    fail "route 返回无效或未就绪 receipt：${route}（reason_code=${reason:-未知}）；现有 Skill 未被替换"
  fi
  printf 'route %s：本地机制就绪\n' "$route"
done

if [[ "$launcher_needs_install" == "1" ]]; then
  if ! mv "$launcher_stage" "$launcher_path"; then
    fail "无法激活 leo-ppt launcher：$launcher_path"
  fi
  launcher_stage=""
  launcher_created=1
fi
if [[ -e "$target" ]]; then
  [[ -n "$backup" ]] || fail "内部错误：未预留旧 bundle 备份目录"
  [[ ! -e "$backup" ]] || fail "备份目录已存在：$backup"
  mv "$target" "$backup"
fi

if ! mv "$candidate" "$target"; then
  if [[ -n "$backup" && -d "$backup" && ! -e "$target" ]]; then
    mv "$backup" "$target"
  fi
  fail "激活新 Skill 失败；已尝试恢复旧版本"
fi
launcher_committed=1
printf 'install[activate]: 已原子激活验证后的 Skill\n'
printf 'install[launcher]: 已安装稳定命令：%s\n' "$launcher_path"

shell_quote() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\"\'\"\'}"
}

onboarding_log="$stage_root/post-activation-onboarding.json"
onboarding_status="blocked"
configuration_state="not_checked"
verification_status="not_checked"
execution_eligibility="blocked"
installation_readiness="installed_not_ready"
onboarding_reason="config_check_unavailable"
cli_reference=""

onboarding_value() {
  local key="$1"
  local fallback="$2"
  local value
  value="$(plutil -extract "$key" raw -o - "$onboarding_log" 2>/dev/null || true)"
  printf '%s' "${value:-$fallback}"
}

run_post_activation_onboarding() {
  printf 'install[onboarding]: 正在检查图片服务配置…\n'
  if ! "$target/scripts/leo-bootstrap.sh" onboard --route generate >"$onboarding_log"; then
    printf '安装后配置检查未完整执行；Skill 仍保持已激活状态。\n' >&2
  fi

  onboarding_status="$(onboarding_value status blocked)"
  configuration_state="$(onboarding_value configuration_state not_checked)"
  verification_status="$(onboarding_value verification.status not_checked)"
  execution_eligibility="$(onboarding_value execution_eligibility blocked)"
  installation_readiness="$(onboarding_value installation_readiness installed_not_ready)"
  onboarding_reason="$(onboarding_value reason_code config_check_unavailable)"
  cli_reference="$(onboarding_value cli_reference '')"
  if [[ "$cli_reference" != /* ]]; then
    cli_reference=""
  fi
}

print_onboarding_report() {
  printf '安装状态：已安装\n'
  printf '配置状态：%s\n' "$configuration_state"
  printf '真实验证状态：%s\n' "$verification_status"
  printf '执行资格：%s\n' "$execution_eligibility"
  printf '安装可用性：%s\n' "$installation_readiness"
  printf '原因：%s\n' "$onboarding_reason"

  case "$installation_readiness" in
    ready)
      printf '图片服务已就绪，可以开始生成 PPT。\n'
      ;;
    usable_unverified)
      printf '配置完成，可以开始使用；首次生成图片时验证服务。\n'
      ;;
    *)
      printf 'Skill 已安装，但当前图片服务尚未就绪。\n'
      ;;
  esac
}

print_configuration_command() {
  printf '稍后可运行：'
  if [[ "$launcher_on_path" == "1" ]]; then
    printf 'leo-ppt config\n'
  elif [[ -n "$launcher_path" ]]; then
    shell_quote "$launcher_path"
    printf ' config\n'
  elif [[ -n "$cli_reference" ]]; then
    shell_quote "$cli_reference"
    printf ' config\n'
  else
    shell_quote "$target/scripts/leo-bootstrap.sh"
    printf ' bootstrap\n'
  fi
}

printf '\n安装成功：%s\n' "$target"
if [[ -n "$backup" ]]; then
  printf '旧版本备份：%s\n' "$backup"
fi

# Install_Transaction 已在原子 mv 时提交。下面的检查、配置、取消或推迟
# 均只影响安装可用性，绝不能回滚已激活的 Skill。
run_post_activation_onboarding
print_onboarding_report

if [[ "$execution_eligibility" != "allowed" ]]; then
  if [[ -z "$cli_reference" ]]; then
    print_configuration_command
  elif [[ ! -t 0 ]]; then
    printf '未检测到交互终端；不会等待配置输入或发起可能计费的验证。\n'
    print_configuration_command
  else
    response=""
    printf '现在启动配置向导吗？ [y/N] '
    IFS= read -r response || response=""
    case "$response" in
      y|Y|yes|YES|Yes)
        printf '正在启动配置向导；任何可能计费的验证仍需在向导中单独确认。\n'
        if ! "$cli_reference" config; then
          printf '配置向导未完成；Skill 仍保持已安装状态。\n' >&2
        fi
        run_post_activation_onboarding
        print_onboarding_report
        if [[ "$execution_eligibility" != "allowed" ]]; then
          print_configuration_command
        fi
        ;;
      *)
        printf '已推迟配置；Skill 仍保持已安装状态。\n'
        print_configuration_command
        ;;
    esac
  fi
fi

if [[ "$launcher_on_path" == "1" ]]; then
  printf '配置命令：leo-ppt config\n'
else
  printf '提示：%s 尚不在 PATH；加入 shell 配置后即可使用短命令：\n' "$bin_dir"
  printf "  export PATH='%s':\$PATH\n" "$bin_dir"
fi
printf '请重新启动 Codex，或开启下一轮对话后使用 leo-ppt-generator。\n'
