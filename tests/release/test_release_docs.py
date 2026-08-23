from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "skills/leo-ppt-generator"
FORBIDDEN_README_TERMS = (
    "codex-ppt license",
    "image-to-editable-ppt license",
    "审计",
    "上游全功能集成审计",
    "直接验证报告",
    "U0 可内嵌性报告",
)


def test_project_uses_mit_and_preserves_both_upstream_licenses():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License\n")
    assert "Permission is hereby granted, free of charge" in license_text
    assert "Copyright (c) 2026 leokuang" in license_text
    assert (ROOT / "skills/leo-ppt-generator/LICENSE").read_text(encoding="utf-8") == license_text
    for name in ("LICENSE.codex-ppt", "LICENSE.image-to-editable-ppt"):
        assert (ROOT / "skills/leo-ppt-generator" / name).is_file()


def test_readme_and_user_guide_cover_install_config_routes_recovery_and_validation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    for anchor in (
        "codex plugin marketplace add",
        "codex plugin add leo-ppt-generator@leo-ppt-generator",
        "skill-installer",
        "https://github.com/sunrain520/leo-ppt-generator/tree/main/skills/leo-ppt-generator",
        "curl -fsSL",
        "install.sh | bash",
        "install.ps1",
        "irm https://raw.githubusercontent.com",
        "Windows 10/11 x64",
        "$leo-ppt-generator",
        "OpenAI",
        "AtlasCloud",
        "PaddleOCR",
        "Keychain",
        "DPAPI",
        "docs/guides/user-guide.md",
        "docs/guides/troubleshooting.md",
        "MIT License",
    ):
        assert anchor in readme
    for anchor in (
        "skill-installer",
        "https://github.com/sunrain520/leo-ppt-generator/tree/main/skills/leo-ppt-generator",
        "curl -fsSL",
        "install.sh | bash",
        "install.ps1",
        "irm https://raw.githubusercontent.com",
        "Windows 10/11 x64",
        "$CODEX_HOME/skills/leo-ppt-generator",
        "$HOME/.agents/skills/leo-ppt-generator",
        "codex plugin marketplace add",
        "leo-bootstrap.sh",
        "leo-bootstrap.ps1",
        "config provider configure --provider openai",
        "generate",
        "direct-editable",
        "upgrade-full",
        "upgrade-selected",
        "backend-contract",
        "run status",
        "run diagnose",
        "run retry",
        "run cleanup",
        "validation-summary.json",
        "failure-report.json",
        "## 8. 升级 Skill",
        "## 9. 卸载 Skill",
        "## 10. 隐私与数据边界",
    ):
        assert anchor in guide


def test_install_docs_distinguish_both_discovery_mechanisms_and_restart_condition():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    for document in (readme, guide):
        assert "codex plugin marketplace add" in document
        assert "skill-installer" in document
        assert "install.sh | bash" in document
        assert "自动" in document
        assert "下一轮" in document or "重新启动" in document
    assert "不要同时安装重复副本" in readme
    assert "$CODEX_HOME/skills/leo-ppt-generator" in guide
    assert "$HOME/.agents/skills/leo-ppt-generator" in guide
    assert "同名目录" in guide
    assert "--upgrade" in guide


def test_public_installer_exists_and_documents_version_pinning():
    installer = ROOT / "install.sh"
    assert installer.is_file()
    body = installer.read_text(encoding="utf-8")
    assert body.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in body
    assert "codeload.github.com/sunrain520/leo-ppt-generator" in body
    assert "--ref" in body

    windows_installer = ROOT / "install.ps1"
    assert windows_installer.is_file()
    windows_body = windows_installer.read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in windows_body
    assert "codeload.github.com/sunrain520/leo-ppt-generator" in windows_body
    assert "[string]$Ref" in windows_body

    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    assert "--ref <commit-or-tag>" in guide
    assert "-Ref <commit-or-tag>" in guide
    assert "固定版本" in guide
    assert "发布 tag" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_user_guide_covers_non_destructive_upgrade_uninstall_and_privacy():
    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    for anchor in (
        "先移出发现目录",
        "runtime_manager.py\" remove",
        "active run",
        "不自动删除",
        "credential_ref",
        "task-local",
        "not-run",
    ):
        assert anchor in guide


def test_documented_config_and_backend_examples_match_v1_contracts():
    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    config_block = guide.split("```yaml\n", 1)[1].split("```", 1)[0]
    config = yaml.safe_load(config_block)
    assert config["schema_version"] == 1
    assert config["max_concurrent_workers"] == 5

    backend_block = guide.split("```json\n", 1)[1].split("```", 1)[0]
    backend = json.loads(backend_block)
    assert backend["schema_version"] == 1
    assert backend["credential_ref"] == "env:OPENAI_API_KEY"
    assert backend["capabilities"]["execution_owner"] == "runtime"


def test_bundle_has_one_discoverable_skill_and_no_third_party_directory():
    assert [path.relative_to(ROOT).as_posix() for path in ROOT.glob("skills/**/SKILL.md")] == [
        "skills/leo-ppt-generator/SKILL.md"
    ]
    assert not (BUNDLE / "third_party").exists()
    assert not (BUNDLE / "README.md").exists()


def test_bundle_markdown_links_and_prompt_skill_refs_resolve():
    markdown_links = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    skill_refs = re.compile(r"\{\{SKILL_ROOT\}\}/([^\s`]+)")
    for document in sorted(BUNDLE.rglob("*.md")):
        body = document.read_text(encoding="utf-8")
        for target in markdown_links.findall(body):
            clean = target.split("#", 1)[0]
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            assert (document.parent / clean).resolve().exists(), (document, target)
        for target in skill_refs.findall(body):
            assert (BUNDLE / target).exists(), (document, target)


def test_public_document_local_links_resolve_and_platform_examples_are_paired():
    markdown_links = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        body = document.read_text(encoding="utf-8")
        for target in markdown_links.findall(body):
            clean = target.split("#", 1)[0]
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            assert (document.parent / clean).resolve().exists(), (document, target)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8")
    for document in (readme, guide):
        assert "macOS" in document
        assert "Windows" in document
        assert "install.sh" in document
        assert "install.ps1" in document


def test_skill_uses_bundle_root_and_has_no_repository_only_runtime_refs():
    body = (BUNDLE / "SKILL.md").read_text(encoding="utf-8")
    first_use = (BUNDLE / "references/first-use.md").read_text(encoding="utf-8")
    assert "scripts/leo-bootstrap.sh" in first_use
    assert "scripts\\leo-bootstrap.ps1" in first_use
    assert "cli_reference" in first_use
    assert "setup --route <route>" in first_use
    assert "SKILL_DIR=" not in body
    assert "print-cli" not in body
    assert "docs/" not in body


def test_worker_prompts_only_use_current_cli_surfaces():
    slide = (BUNDLE / "prompts/slide-worker.md").read_text(encoding="utf-8")
    assert "scripts/image_gen.py" not in slide
    assert '"<absolute leo-ppt CLI path>" upstream codex-ppt -- image generate' in slide
    assert '"<absolute leo-ppt CLI path>" upstream codex-ppt -- image edit' in slide
    assert "`leo-ppt upstream" not in slide

    page = (BUNDLE / "prompts/page-worker.md").read_text(encoding="utf-8")
    assert "{{SKILL_ROOT}}/references/cli-helper.md" in page
    helper = (BUNDLE / "references/cli-helper.md").read_text(encoding="utf-8")
    assert '"$LEO_PPT" upstream editable-ppt -- prepare' in helper
    assert "LEO_PPT=" in helper
    assert "pipx install" not in helper


def test_readme_excludes_internal_delivery_terms():
    body = (ROOT / "README.md").read_text(encoding="utf-8")
    lowered = body.lower()
    for term in FORBIDDEN_README_TERMS:
        assert term.lower() not in lowered
    for internal in ("runtime_manager.py", "print-cli", "config.yaml", "backend create"):
        assert internal not in body


def test_repo_marketplace_exposes_the_root_plugin_without_a_second_skill_tree():
    marketplace = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    assert marketplace["name"] == "leo-ppt-generator"
    assert len(marketplace["plugins"]) == 1
    plugin = marketplace["plugins"][0]
    assert plugin["name"] == "leo-ppt-generator"
    assert plugin["source"] == {
        "source": "url",
        "url": "https://github.com/sunrain520/leo-ppt-generator.git",
        "ref": "feat/leo-ppt-generator-release",
    }
    assert plugin["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_documented_public_commands_exist_in_current_cli_help():
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "skills/leo-ppt-generator/runtime/src"),
    }
    for arguments, anchors in (
        (("version", "--help"), ("--json",)),
        (
            ("update", "--help"),
            ("--check", "--dry-run", "--version", "--yes", "--json"),
        ),
        (("rollback", "--help"), ("--identity", "--json")),
        (("auth", "add", "--help"), ("--provider", "--overwrite")),
        (("setup", "--help"), ("--host-imagegen", "--ocr-requirement")),
        (
            ("config", "--help"),
            ("status", "verify", "repair", "provider", "credential", "reset"),
        ),
        (
            ("config", "status", "--help"),
            ("--route", "--json"),
        ),
        (
            ("config", "provider", "--help"),
            ("list", "configure", "select", "remove"),
        ),
        (
            ("config", "credential", "--help"),
            ("status", "set", "remove"),
        ),
        (
            ("config", "credential", "set", "--help"),
            ("--provider", "--overwrite", "--key-stdin"),
        ),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "leo_ppt_generator", *arguments],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert all(anchor in result.stdout for anchor in anchors)


def test_six_reader_roles_can_find_their_single_task_path():
    documents = {
        "readme": (ROOT / "README.md").read_text(encoding="utf-8"),
        "guide": (ROOT / "docs/guides/user-guide.md").read_text(encoding="utf-8"),
        "troubleshooting": (ROOT / "docs/guides/troubleshooting.md").read_text(encoding="utf-8"),
        "testing": (ROOT / "docs/guides/testing.md").read_text(encoding="utf-8"),
    }
    role_tasks = {
        "首次用户": ("readme", ("方式 A：Codex Plugin", "第一次生成 PPT")),
        "Windows 用户": ("guide", ("Windows 10/11 x64", "leo-bootstrap.ps1")),
        "安全审查者": ("guide", ("DPAPI", "不接受聊天、命令参数或 pipe")),
        "支持运营": ("troubleshooting", ("primary_action", "唯一首选动作")),
        "发布工程师": ("testing", ("双渠道发布", "tree hash")),
        "PPT 编辑者": ("readme", ("对象级可编辑", "重新确认样张")),
    }
    for _role, (document, anchors) in role_tasks.items():
        assert all(anchor in documents[document] for anchor in anchors)


def test_testing_plan_covers_murphy_failure_domains_and_false_green_boundaries():
    body = (ROOT / "docs/guides/testing.md").read_text(encoding="utf-8")
    for anchor in (
        "## 墨菲定律故障驱动模型",
        "### 发布故障矩阵",
        "并发",
        "陈旧锁",
        "runtime receipt",
        "route receipt",
        "operation",
        "损坏 run/current",
        "反假绿",
        "Windows 真机待跑",
        "P0/P1 故障域",
    ):
        assert anchor in body
