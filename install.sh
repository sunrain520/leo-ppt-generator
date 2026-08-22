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
if [[ "$platform" != "Darwin" || "$architecture" != "arm64" ]]; then
  fail "当前版本仅支持 macOS arm64；检测到 ${platform}/${architecture}"
fi
printf 'install[platform_check]: macOS arm64 已确认\n'

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
for discovery_root in "$codex_root" "$agents_root"; do
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
install_lock="$target_parent/.$SKILL_NAME.install.lock"
lock_acquired=0
cleanup() {
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

stage_root="$(mktemp -d "$target_parent/.leo-ppt-installer.XXXXXX")"

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

printf 'install[runtime_ensure]: 正在初始化受管 runtime…\n'
ensure_log="$stage_root/runtime-ensure.log"
if ! "$candidate/scripts/leo-bootstrap.sh" bootstrap >"$ensure_log"; then
  cat "$ensure_log" >&2
  fail "runtime 初始化失败；现有 Skill 未被替换"
fi
if [[ "$(plutil -extract protocol raw -o - "$ensure_log" 2>/dev/null || true)" != "leo-ppt-bootstrap/v1" || \
      "$(plutil -extract status raw -o - "$ensure_log" 2>/dev/null || true)" != "ready" || \
      -z "$(plutil -extract runtime_identity raw -o - "$ensure_log" 2>/dev/null || true)" || \
      -z "$(plutil -extract cli_reference raw -o - "$ensure_log" 2>/dev/null || true)" ]]; then
  cat "$ensure_log" >&2
  fail "runtime 初始化返回无效 receipt；现有 Skill 未被替换"
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
    fail "route 返回无效或未就绪 receipt：${route}；现有 Skill 未被替换"
  fi
  printf 'route %s：本地机制就绪\n' "$route"
done

backup=""
if [[ -e "$target" ]]; then
  backup_root="$target_parent/.$SKILL_NAME-backups"
  mkdir -p "$backup_root"
  backup="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  [[ ! -e "$backup" ]] || fail "备份目录已存在：$backup"
  mv "$target" "$backup"
fi

if ! mv "$candidate" "$target"; then
  if [[ -n "$backup" && -d "$backup" && ! -e "$target" ]]; then
    mv "$backup" "$target"
  fi
  fail "激活新 Skill 失败；已尝试恢复旧版本"
fi
printf 'install[activate]: 已原子激活验证后的 Skill\n'

printf '\n安装成功：%s\n' "$target"
if [[ -n "$backup" ]]; then
  printf '旧版本备份：%s\n' "$backup"
fi
printf '请重新启动 Codex，或开启下一轮对话后使用 leo-ppt-generator。\n'
