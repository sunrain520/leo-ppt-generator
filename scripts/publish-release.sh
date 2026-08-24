#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
REMOTE="origin"
TAG=""
PUBLISH=0
SKIP_TESTS=0

usage() {
  cat <<'EOF'
用法：
  bash scripts/publish-release.sh
  bash scripts/publish-release.sh --publish
  bash scripts/publish-release.sh --publish --tag v0.1.0

默认只执行发布前检查和预览；传入 --publish 才会自动创建 tag、推送远端并验证公开 URL。

选项：
  --publish         自动创建 annotated tag 并推送到远端
  --tag <tag>       覆盖自动生成的 tag；必须与 runtime 版本一致
  --remote <name>   Git remote，默认 origin
  --skip-tests      跳过发布合同测试（不推荐）
  -h, --help        显示帮助
EOF
}

fail() {
  printf '发布失败：%s\n' "$*"
  exit 1
}

while (($# > 0)); do
  case "$1" in
    --publish)
      PUBLISH=1
      shift
      ;;
    --tag)
      (($# >= 2)) || fail "--tag 缺少值"
      TAG="$2"
      shift 2
      ;;
    --remote)
      (($# >= 2)) || fail "--remote 缺少值"
      REMOTE="$2"
      shift 2
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
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

cd "$ROOT"
git rev-parse --show-toplevel >/dev/null || fail "当前目录不是 Git 仓库"
REMOTE_URL="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
[[ -n "$REMOTE_URL" ]] || fail "Git remote 不存在：$REMOTE"

if [[ -n "$(git status --porcelain=v1)" ]]; then
  fail "工作树不干净；请先提交或清理改动后再发布"
fi

VERSION="$(python3 - <<'PY'
from pathlib import Path
import tomllib

document = tomllib.loads(
    Path("skills/leo-ppt-generator/runtime/pyproject.toml").read_text(encoding="utf-8")
)
print(document["project"]["version"])
PY
)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || fail "runtime 版本无效：$VERSION"
[[ -n "$TAG" ]] || TAG="v$VERSION"
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || fail "tag 格式无效：$TAG"
[[ "$TAG" == "v$VERSION" ]] || fail "tag $TAG 与 runtime 版本 v$VERSION 不一致"

HEAD_SHA="$(git rev-parse HEAD)"
git rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null && fail "本地 tag 已存在：$TAG"
if git ls-remote --exit-code --quiet "$REMOTE" "refs/tags/$TAG" >/dev/null 2>&1; then
  fail "远端 tag 已存在：$REMOTE/$TAG；脚本禁止覆盖已有 tag"
fi

STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/leo-release.XXXXXX")"
cleanup() { rm -rf -- "$STAGE_ROOT"; }
trap cleanup EXIT

printf 'release[preflight]: remote=%s tag=%s head=%s\n' "$REMOTE_URL" "$TAG" "$HEAD_SHA"
printf 'release[build]: 构建并验证 standalone/plugin 包…\n'
python3 scripts/build_release.py --output "$STAGE_ROOT/dist" >"$STAGE_ROOT/build.json"
python3 scripts/validate_release.py "$STAGE_ROOT/dist/release-manifest.json" >"$STAGE_ROOT/validate.json"

if [[ "$SKIP_TESTS" == "0" ]]; then
  command -v pytest >/dev/null 2>&1 || fail "缺少 pytest；如确需跳过，显式传入 --skip-tests"
  printf 'release[test]: 运行发布合同测试…\n'
  PYTHONDONTWRITEBYTECODE=1 pytest -q \
    tests/release/test_plugin_package.py \
    tests/release/test_release_docs.py \
    tests/release/test_installed_routes.py
else
  printf 'release[test]: 已跳过（--skip-tests）\n'
fi

if [[ "$PUBLISH" == "0" ]]; then
  printf 'release[preview]: 预检通过；未创建 tag、未推送。\n'
  printf 'release[preview]: 执行 bash scripts/publish-release.sh --publish 以一键发布 %s。\n' "$TAG"
  exit 0
fi

printf 'release[tag]: 创建 annotated tag %s…\n' "$TAG"
git tag -a "$TAG" -m "Release $TAG" "$HEAD_SHA"
if ! git push "$REMOTE" "refs/tags/$TAG"; then
  git tag -d "$TAG" >/dev/null 2>&1 || true
  fail "tag 推送失败；已删除本地新建 tag，未执行强制覆盖"
fi

REMOTE_TAGS="$(git ls-remote "$REMOTE" "refs/tags/$TAG" "refs/tags/$TAG^{}")"
printf '%s\n' "$REMOTE_TAGS" | grep -Eq "[[:space:]]refs/tags/$TAG\^\{\}$" || \
  fail "远端 tag 已推送但未确认 peeled commit：$REMOTE/$TAG"

REPO_SLUG="$(printf '%s' "$REMOTE_URL" | sed -E 's#^https?://github\.com/##; s#^git@github\.com:##; s#\.git$##')"
if [[ "$REPO_SLUG" =~ ^[^/]+/[^/]+$ ]]; then
  printf 'release[verify]: 验证 GitHub raw/codeload 公开 URL…\n'
  RAW_BASE="https://raw.githubusercontent.com/$REPO_SLUG/$TAG"
  curl -fsSL --max-time 30 -o /dev/null "$RAW_BASE/install.sh"
  curl -fsSL --max-time 30 -o /dev/null "$RAW_BASE/install.ps1"
  curl -fsSL --max-time 30 -o /dev/null "$RAW_BASE/skills/leo-ppt-generator/SKILL.md"
  curl -fsSL --max-time 60 -o /dev/null "https://codeload.github.com/$REPO_SLUG/tar.gz/$TAG"
else
  printf 'release[verify]: remote 非 GitHub，跳过匿名 URL 检查：%s\n' "$REMOTE_URL"
fi

printf 'release[complete]: %s/%s 已发布。\n' "$REMOTE" "$TAG"
printf 'release[update]: 用户可运行 leo-ppt update --yes --version %s\n' "$TAG"
