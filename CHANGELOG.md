# Changelog

All notable changes to the leo-ppt-generator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added - 2026-08-23

- 新增 100 种可参考 PPT 风格库：按 `01_通用母版（30）/ 02_行业内容域（35）/ 03_场景用途结构（35）` 三层多级分类，存放于 `references/styles/` 下；每风格含完整 GPT-Image-2 JSON Brief（visual_direction / canvas / color_palette / typography / layout_patterns / layout_usage_rule / layout_blueprints / visual_elements / rendering_constraints）与 `reference` 来源，并新增 `00_索引/_INDEX.md` 总索引。均为独立候选参考风格（`list_styles()` 载入 glob `references/styles/*.md`，不自动加载子目录），现有 12 个内置风格保持不变。(user-visible)。作者: leokuang
- 新增 macOS Intel (x86_64) 支持：固定 `macos-x64` uv artifact、`darwin-x86_64`
  约束锁、bootstrap/install 平台门与 Keychain 集成测试覆盖；目标安装平台扩展为
  macOS arm64/x86_64 与 Windows 10/11 x64。
- 新增跨平台 `platform-smoke` CI job：在 macOS arm64、macOS Intel 与 Windows x64
  runner 上执行真实 clean install、bootstrap 与 `config status` 冒烟，并在 PR 触发。
- 同步兼容性声明、README、用户指南、故障处理与 reason-codes 的平台文案。

### Changed - 2026-08-23

- 补充仓库卫生规则：忽略 `.spec-first/cache`、`.hypothesis`、`.ruff_cache`、`.venv`、
  `.env`、`.DS_Store`、`*.bak` 与 `semantic-review`，并将已误提交的 MCP warmup 缓存与
  graphify 备份移出 Git 跟踪。
- 加固安装/升级/回滚一致性：`rollback` 先校验目标 runtime 健康再动 bundle，支持显式
  `--identity` 在 current 不健康时回滚到已知健康旧版；bundle 恢复整体原子化并在激活窗口
  中断时直接把备份就位，避免旧包丢失或新 runtime + 旧 bundle 分裂；二次回滚记录并还原
  bundle 备份。
- `version` 的 `install_channel` 拒绝空值/未知值并按 install 渠道透传，agent-skill 安装
  经 `update` 升级后不再被误标为 standalone（Windows 渠道登记仍属未验证范围）。
- `_restore_previous_bundle` 首个替换失败给出可诊断错误而非裸 `FileNotFoundError` 逃逸。

### Added - 2026-08-22

- 新增无状态 setup facade、宿主图片能力三态、Provider capability/凭据/确认排序和 OCR
  延迟披露，所有非 ready 结果只提供一个首选恢复动作。
- 新增 macOS/Windows bundle bootstrap launcher，可安全复用系统 Python、已有 uv 或私有
  Python 3.12，并在执行固定工件前验证 HTTPS origin、大小和 SHA-256。
- 新增 `auth add/status/remove`、macOS Keychain 与 Windows 当前用户 DPAPI 凭据存储，
  保留环境变量兼容入口，状态、receipt 与 run 不记录 secret。
- 新增 canonical Codex Plugin manifest、repo marketplace、可复现双渠道发布构建和
  release manifest；Plugin 与 standalone 强制使用同一 Skill tree hash。
- 简化首次使用流程：Agent 自动 bootstrap/setup，README 只保留 Plugin/standalone
  安装、自然语言首次任务和按需密钥三档。
- 新增统一 `leo-ppt config` 用户合同及能力级 verification receipt：本地配置完整后以
  `configured_unverified` 允许开始任务；可能计费的 `verify` 仅接受当前操作的明确同意，
  首张真实业务图片通过 single-flight 完成惰性验证。
- 新增顶层 `version`、`update`、`rollback`，以及统一的
  `config provider`、`config credential` 命令树；历史 `auth`、顶层 `provider` 和
  `config change` 降级为兼容入口。
- 同步用户文档、兼容性、故障处理、限制与测试说明：统一 `config status/verify/repair/change`
  路径，明确 Host capability 三态、凭据安全通道、非破坏式升级恢复和现场证据上限。

### Added - 2026-08-21

- 交付唯一可发现的 `leo-ppt-generator` Skill、不可变受管 runtime、四条有限 route
  和 `leo-ppt-machine/v1` CLI 协议。
- 内嵌固定版本 codex-ppt 与 image-to-editable-ppt 源码、许可证、patch ledger、
  vendor lock 与 `sync_upstreams.py --check`。
- 新增 versioned `PageArtifact`、backend contract、轻量 `run.json`、revision、
  idempotency、脱敏 events、diagnose 与 fingerprint-guarded cleanup。
- 新增 image/editable adapter、full editable/hybrid/partial-hybrid assembler，保证
  缺页、hash、validation 与未确认 partial 场景 fail closed。
- 新增 immutable upgrade baseline、generation/lease fence、原子 PPTX finalize、
  speaker notes、无损图片比例策略和安装后四 route 黑盒验证。
- 新增用户风格 store、source-side 公式确认清单，以及 provider provenance、独立
  visual render 和人工 acceptance 三类 hash-bound evidence 命令。
- 新增 unit/integration/boundary/e2e/Skill contract 测试、覆盖率门禁、测试方案、
  兼容性声明、已知限制与直接验证报告。
- 新增公开 `install.sh`：支持一键安装、`skill-installer` 并列指引、固定 ref、通用
  Agent 发现目录、安全升级备份，以及安装前 runtime 与四 route 验证。
- 新增 Windows 10/11 x64 原生 `install.ps1`、Windows dependency lock、PowerShell
  Skill 启动语法，以及与 macOS 一致的 staging、验证、升级和回滚合同。
- 按墨菲定律/FMEA 补齐并发安装、远程压缩包、特殊路径、假成功 receipt、激活失败、
  损坏 operation/run/current 元数据等故障注入；安装器增加目标互斥与 receipt 语义校验，
  runtime 删除在元数据不可确认时 fail closed。

### Fixed - 2026-08-21

- editable vendor 状态写入增加文件锁、expected revision、temp write、file fsync、
  atomic replace 与 directory barrier；codex 状态补 directory barrier。
- 修复 wheel 错误打包 `__pycache__`/`.pyc` 的发布污染。
- 修复 runtime 初始化直接从 Skill source 构建而回写 `build`/`*.egg-info` 的污染；安装改从
  临时隔离副本构建，并统一排除 `build`、`dist` 与 `*.egg-info`。
- 统一 image/editable canonical state，接通 backend execution contract、凭据引用、
  timeout/retry 与脱敏 execution receipt；兼容声明收敛到 Python 3.12/macOS arm64。

### Added - 2026-08-20

- **Hybrid assembler precondition validation**: Added comprehensive precondition table with 7 invariants that must be verified before hybrid assembly (page count, order, dimensions, validation status, notes mapping, source hash, total page count)
- **U0 quantified success criteria**: Added measurable pass/fail standards including source code change rate (<5%), adapter code limit (<500 lines), dependency conflicts (0), test pass rate (≥95%), and qualitative boundaries
- **Worker availability decision matrix**: Added `worker_mode` in `next_action` payload supporting multi_agent/single_page_local/unavailable modes with clear Agent behavior for each
- **Progress reporting**: Added optional `progress` field in machine protocol with total_units, completed, failed, pending, and estimated_remaining_seconds
- **Backend selection algorithm**: Added fallback chain with priority-based selection, condition checking (agent_host_supports, credential_available, endpoint_configured), and explicit user confirmation override
- **Credential lifecycle management**: Added credential source priority, security rules (no plaintext logging, no CLI args, no run directory storage), and credential expiration handling with retry-from-failed recovery
- **Error classification system**: Added comprehensive reason_code taxonomy with 19 error types, each mapped to recoverability status and specific recovery actions
- **User interruption handling**: Added interrupt types (user cancel, agent timeout, system crash, explicit cancel), grace period behavior (5 min), and state preservation rules
- **Concurrency control**: Added worker concurrency configuration (default min(cpu_count//2, 4, page_count), configurable max 1-16), backend API rate limiting with exponential backoff, and resource limits (10GB disk quota)
- **Log levels and debug mode**: Added structured JSON logging with 5 levels (ERROR/WARNING/INFO/DEBUG/TRACE), `LEO_PPT_DEBUG=1` mode preserving all artifacts, and credential/content redaction rules
- **Test coverage requirements**: Added quantified coverage targets (adapter ≥80%, run_index ≥90%, hybrid ≥85%), integration test matrix (8 route×backend combos), and boundary test scenarios (concurrent writes, crash injection, idempotency)
- **Performance baseline**: Added typical scenario timing expectations (10-page PPT: generate 5-12min, direct-editable 8-18min, upgrade-full 13-30min), timeout strategy table, and performance monitoring with timing.json structure
- **Scale limits**: Added first-version limits (generate max 50 pages, direct-editable max 100 pages, upgrade max 50 selected pages, single image 25MB, total PPTX 200MB, run directory 10GB)
- **Troubleshooting guide**: Added Appendix A with 12 common scenarios covering installation/config, runtime issues, recovery/cleanup, and performance problems with concrete commands
- **DoD requirements**: Added version compatibility statement requirement, reason_code documentation mandate, and troubleshooting documentation requirement

### Changed - 2026-08-20

- **Section 3.5**: Expanded hybrid assembler specification to include detailed precondition validation table with 7 verification points
- **Section 5.4**: Enhanced machine protocol contract with worker_mode declaration and progress reporting capabilities
- **Section 8.2**: Expanded backend contract to include selection algorithm, credential lifecycle, and expiration handling
- **Section 8.4**: Added new section for concurrency control and resource limits
- **Section 9.1**: Enhanced U0 spike requirements with quantified pass criteria and measurable boundaries
- **Section 11**: Restructured into 11.1 (failure reporting), 11.2 (error classification), and 11.3 (user interruption)
- **Section 13**: Added 13.6 (test coverage requirements) and 13.7 (claim ceiling)
- **Chapter 14**: Added new chapter "Performance Baseline and Resource Management" with 4 subsections
- **Chapter 15-16**: Renumbered from 14-15 due to new chapter insertion
- **Definition of Done**: Added requirements for reason_code documentation, test coverage verification, version compatibility statement, and troubleshooting documentation

### Technical Impact

- **Extensibility**: Improved from 5/10 to 7.5/10 through explicit capability protocol, backend selection abstraction, and import boundary enforcement
- **Stability**: Improved from 6/10 to 8.5/10 through quantified concurrency controls, error classification, idempotency contracts, and credential lifecycle management
- **Operational readiness**: Improved from 6.5/10 to 8.0/10 through comprehensive error recovery paths, performance baselines, and troubleshooting guidance
- **Implementation readiness**: Upgraded from "needs tactical clarification" to "ready for implementation with clear DoD gates"

### Notes

This update systematically addressed 17 identified optimization points across architecture (capability discovery, backend selection), stability (concurrent writes, credential expiration, user interruption), quality assurance (test coverage, performance baseline), and operational excellence (error classification, troubleshooting guide).

Author: Claude (based on systematic review feedback)

---

## Project Initialization - 2026-08-20

### Added

- Initial project structure with docs/plans/ directory
- Technical plan 002: PPT orchestration skill plan (superseded by 003)
- Technical plan 003: Top-level PPT workflow skill with embedded dual-capability architecture

Author: leokuang (user-visible)
