# Leo PPT Generator 文档中心

本目录组织 Leo PPT Generator 的全部技术文档、方案与交付记录。

## 目录结构

| 子目录 | 内容 |
| --- | --- |
| `guides/` | 用户与使用文档(安装 / 兼容 / 故障 / 限制 / 测试) |
| `skills/` | 技能与端到端工作流定义 |
| `reviews/` | 评审、优化与验证报告 |
| `plans/` | 技术方案与实施计划 |
| `audits/` | 上游能力审计与证据 |

## guides/ — 用户与使用

- [user-guide.md](guides/user-guide.md) — 完整用户教程(安装 Skill / 升级 / 卸载)
- [compatibility.md](guides/compatibility.md) — 版本兼容性声明
- [troubleshooting.md](guides/troubleshooting.md) — 故障处理与唯一恢复动作
- [limitations.md](guides/limitations.md) — 已知限制与边界
- [testing.md](guides/testing.md) — 测试方案与证据分层

## skills/ — 技能与工作流

- [skill-workflow.md](skills/skill-workflow.md) — 端到端逻辑流程(用户路径 / Agent 编排 / 确定性 runtime)

## reviews/ — 评审与验证报告

- [three-round-skill-product-review-2026-08-21.md](reviews/three-round-skill-product-review-2026-08-21.md) — 三轮 Skill 产品审查报告
- [optimization-rounds-2026-08-21.md](reviews/optimization-rounds-2026-08-21.md) — 20 轮多角色优化记录
- [u0-report.md](reviews/u0-report.md) — U0 可内嵌性与发行边界报告
- [verification-report-2026-08-21.md](reviews/verification-report-2026-08-21.md) — 直接验证报告
- [verification-report-2026-08-22.md](reviews/verification-report-2026-08-22.md) — 发布候选验证报告

## plans/ — 技术方案

- [2026-08-20-002-feature-ppt-orchestration-skill-plan.md](plans/2026-08-20-002-feature-ppt-orchestration-skill-plan.md) — PPT 编排技能方案
- [2026-08-20-003-feature-top-level-ppt-workflow-skill-plan.md](plans/2026-08-20-003-feature-top-level-ppt-workflow-skill-plan.md) — 顶层 PPT 工作流技能方案
- [2026-08-21-004-feature-release-hardening-and-review-closure-plan.md](plans/2026-08-21-004-feature-release-hardening-and-review-closure-plan.md) — 发布加固与评审闭环方案
- [2026-08-21-005-upstream-capability-integration-review-plan.md](plans/2026-08-21-005-upstream-capability-integration-review-plan.md) — 上游能力集成评审方案
- [2026-08-22-006-feature-frictionless-onboarding-and-distribution-plan.md](plans/2026-08-22-006-feature-frictionless-onboarding-and-distribution-plan.md) — 无摩擦上手与分发方案

## audits/ — 上游能力审计

- [upstream-feature-integration-audit-2026-08-21.md](audits/upstream-feature-integration-audit-2026-08-21.md) — 两个上游全功能集成审计
- [upstream-capability-integration-review-2026-08-21.md](audits/upstream-capability-integration-review-2026-08-21.md) — 上游能力集成评审
- `upstream-integration/` — 集成证据(文件清单 / 验证摘要 / 快照)

---

> 快速入口:新用户从 [用户教程](guides/user-guide.md) 开始;集成方看 [兼容性](guides/compatibility.md) 与 [审计](audits/upstream-feature-integration-audit-2026-08-21.md)。
