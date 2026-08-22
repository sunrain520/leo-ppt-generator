---
artifact_contract: spec-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
status: active
date: 2026-08-20
title: PPT Orchestration Skill - Focused MVP Plan
topic: ppt-orchestration-skill
type: feat
---

# PPT Orchestration Skill - Focused MVP Plan

## Goal Capsule

- **目标：** 做一个统一的 PPT 生成 Skill，编排 `codex-ppt` 与 `image-to-editable-ppt` 两套已存在能力。
- **集成方式：** 将两套 Skill 的必要源码纳入当前仓库，由当前项目直接安装和调用；主流程不依赖用户另外安装两个旧 Skill 或旧 CLI。
- **Runtime：** 共享一个 Python package、一个依赖环境、一个配置入口和一个 CLI；不建设新的通用工作流平台。
- **默认体验：** 先生成高质量图片式 PPT；用户需要时再把整套或指定页面升级为可编辑 PPT；已有视觉稿也可直接转可编辑 PPT。
- **复用原则：** 保留上游已经工作的算法、prompt、验证和页面 worker 合同，只在入口、配置、路径和跨阶段衔接处做必要改造。
- **MVP 成功标准：** 用户只需发现并使用 `leo-ppt-generator`，即可完成图片生成、直接转可编辑、图片版升级可编辑三条路径，并得到可验证的 PPTX。

## 1. 问题与边界

### 1.1 当前问题

两个上游 Skill 已分别解决：

1. `codex-ppt`：从文章、报告、笔记或大纲生成整页图片式 PPT。
2. `image-to-editable-ppt`：从图片、PDF 或图片型 PPT/PPTX 重建对象级可编辑 PPT。

当前缺少的是统一产品入口和自然的阶段衔接，不是第三套 PPT 算法，也不是新的任务调度平台。

### 1.2 MVP 范围

MVP 只做以下能力：

- 一个可发现的 `leo-ppt-generator` Skill。
- 一个可安装的 `leo-ppt-generator` Python package。
- 一个 `leo-ppt` CLI。
- 统一依赖、配置读取、图片后端选择和输出目录。
- 三条用户路径：
  - 内容 → 图片式 PPT。
  - 图片/PDF/PPTX → 可编辑 PPT。
  - 图片式 PPT → 整套或指定页面可编辑升级。
- 复用两套上游的关键源码、prompt、references、测试和许可证信息。
- 保留上游已有的大纲确认、样张确认、页面重建、manifest 驱动和结构验证语义。

### 1.3 明确不做

MVP 不做：

- Web、桌面端或多人协作。
- 通用 scheduler、daemon、租约、heartbeat、attempt quarantine 或分布式任务协议。
- SQLite 任务数据库、事件溯源、JSON projection 或 completion attestation。
- 自建公开网页抓取器；文章正文由 Agent 使用现有读取能力获得，runtime 只接收本地文件或已规范化文本。
- 自建 credential store、旧配置迁移系统或多级 secret resolver。
- 自建 Office 沙箱、SSRF 网关、网络策略引擎或跨平台隔离框架。
- SSIM 自动视觉回归、密码学证明或逐页审计台账。
- 承诺所有复杂视觉元素都能成为 PowerPoint 原生对象。

这些能力只有在真实使用暴露明确问题后，才进入后续版本。

## 2. 产品流程

### 2.1 路由 A：生成图片式 PPT

1. Skill 获取主题、文章正文、报告、笔记或详细内容稿。
2. 复用 `codex-ppt` 的内容理解、大纲、风格、图片后端和样张确认流程。
3. 用户确认样张后，复用其 slide worker、图片生成、状态记录、QA 和 PPTX 组装能力。
4. 输出图片式 PPTX、逐页图片、最终大纲和演讲稿（如需要）。
5. Skill 询问用户是否需要升级为可编辑版本。

### 2.2 路由 B：直接转可编辑 PPT

1. Skill 收到图片、PDF 或已有 PPT/PPTX，并确认用户要直接重建可编辑版本。
2. 复用 `image-to-editable-ppt` 的输入规范化、OCR hints、page worker、manifest、record、validation 和 finalize 流程。
3. 输出对象级可编辑 PPTX 及验证结果。

### 2.3 路由 C：图片版升级为可编辑 PPT

1. 使用路由 A 的最终逐页图片作为路由 B 的输入。
2. 用户选择整套或指定页面。
3. 只处理所选页面；未选择页面的交付语义必须明确：
   - 整套升级：输出全可编辑 deck。
   - 指定页面升级：输出混合 deck，并明确哪些页已升级。
4. 复用 editable runtime 的页面验证和最终组装能力。

### 2.4 失败行为

- 失败时报告具体阶段、页面和可用产物。
- 图片版已经成功时，可编辑升级失败不得抹掉图片版交付。
- 不完整页面不得被静默组装为成功 deck。
- 重试沿用上游 runtime 的既有机制；MVP 不另建一套重试状态机。

## 3. 架构

```text
User
  │
  ▼
skills/leo-ppt-generator/SKILL.md
  │  负责意图识别、确认点、路由和用户沟通
  ▼
leo-ppt CLI / leo_ppt_generator package
  ├── image_deck adapter
  │     └── imported codex-ppt source
  ├── editable adapter
  │     └── imported image-to-editable-ppt source
  ├── shared config and image backend facade
  └── shared run directory
```

### 3.1 Skill 与 runtime 的职责

Skill 负责：

- 判断用户要生成、直接转可编辑，还是升级可编辑。
- 获取最少必要信息。
- 执行上游已有的大纲、风格、样张和升级确认。
- 在 Agent 宿主提供并行能力时，按上游 worker 合同派发 slide/page worker。
- 调用统一 CLI，并把结果和限制报告给用户。

Runtime 负责：

- 输入文件规范化。
- 调用图片式 PPT 与可编辑 PPT 的确定性源码能力。
- 提供统一配置和路径解析。
- 保存阶段产物。
- 执行 PPTX 组装和既有结构验证。

Runtime 不负责模拟 Agent 宿主，也不拥有一套新的 subagent scheduler。

### 3.2 共享 runtime 的准确含义

“共享一套 runtime”在 MVP 中只表示：

- 一个 `pyproject.toml` 和一个安装环境。
- 一个 `leo-ppt` console entry point。
- 一套依赖版本。
- 一个配置 facade。
- 一个图片后端 facade。
- 一个任务产物根目录。
- 两个内部领域 adapter，共享基础设施但保留各自算法边界。

它不表示必须把两个上游的全部内部状态强制重写成同一种数据库模型。

### 3.3 建议源码结构

```text
leo-ppt-generator/
├── pyproject.toml
├── src/leo_ppt_generator/
│   ├── cli.py
│   ├── config.py
│   ├── paths.py
│   ├── image_backend.py
│   ├── image_deck/
│   │   ├── adapter.py
│   │   └── upstream/          # 导入的 codex-ppt 必要源码
│   └── editable/
│       ├── adapter.py
│       └── upstream/          # 导入的 editable 必要源码
├── skills/leo-ppt-generator/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── prompts/
│   └── references/
├── third_party/
│   ├── upstreams.yaml
│   └── notices/
└── tests/
    ├── upstream/
    ├── unit/
    └── integration/
```

`upstream/` 命名空间优先保持原文件结构和相对 import，减少“为了整洁而重写”。只有稳定公共入口由 adapter 暴露。

## 4. 接口

### 4.1 CLI

MVP 提供四个命令：

```bash
leo-ppt doctor
leo-ppt generate <content-or-file> --output <dir>
leo-ppt editable <visual-input...> --output <dir>
leo-ppt upgrade <image-deck-run> [--pages 1,3,5] --output <dir>
```

- `doctor`：检查当前命令所需的 Python 依赖、图片后端和可选 OCR 能力。
- `generate`：进入图片式 PPT runtime。
- `editable`：直接进入可编辑重建 runtime。
- `upgrade`：把已生成的逐页图片传给 editable adapter。

CLI 只提供稳定入口，不重新实现 Agent 才能完成的内容澄清、用户确认或 subagent 创建。

### 4.2 Python adapter

```python
class ImageDeckAdapter:
    def generate(self, request: ImageDeckRequest) -> ImageDeckResult: ...

class EditableDeckAdapter:
    def rebuild(self, request: EditableDeckRequest) -> EditableDeckResult: ...
```

adapter 负责把统一路径、配置和结果对象映射到上游源码；不复制上游算法。

### 4.3 输出目录

```text
<run>/
├── run.json
├── input/
├── image-deck/       # codex-ppt 阶段产物，尽量保留上游布局
├── editable/         # editable 阶段产物，尽量保留上游布局
└── final/
```

`run.json` 只记录路由、阶段结果路径、所选升级页面和最终交付物。它是轻量索引，不替代两个上游的页面级状态文件。

写入 `run.json` 使用临时文件加原子替换，避免引入数据库。

## 5. 源码集成策略

### 5.1 导入原则

- 固定两个上游 commit。
- 记录仓库 URL、commit、许可证和导入目录。
- 优先导入真正执行流程需要的 Skill 文件、prompt、reference、runtime 源码和测试。
- 原样保留的文件尽量不改名、不拆分、不重排。
- 必须修改时，把改动限制在 import、配置、路径和统一 adapter 接口。
- 不以“复用率”作为成功指标；是否减少重写和保持行为才是判断标准。

### 5.2 不采用逐文件设计审批

不在主计划中维护 76 行 disposition 和精确行区间。`third_party/upstreams.yaml` 只需记录：

- 上游身份与固定版本。
- 导入的目录或文件集合。
- 本地 patch 摘要。
- 许可证位置。
- 对应回归测试。

需要同步上游时再由脚本生成文件级 diff，不把一次性治理台账变成 MVP 前置系统。

### 5.3 允许的局部修复

集成中只修复直接影响主流程正确性或凭据安全的问题，例如：

- 组装时缺页仍返回成功。
- provider 域名使用子串误判。
- 并发写状态文件没有原子保护。
- editable finalize 不重新确认记录的页面产物仍一致。

每项修复必须有一个聚焦回归测试。Office 沙箱、通用 SSRF 防护和完整凭据迁移不是本阶段目标。

## 6. 配置与依赖

### 6.1 配置 facade

统一 facade 读取：

1. 当前命令显式的非敏感选项。
2. 已支持的环境变量。
3. `${LEO_PPT_HOME}/config.yaml`。
4. 默认值。

凭据只从现有环境变量或上游已支持的认证文件读取；MVP 不复制、迁移或保存 token。

### 6.2 按阶段检查

- `generate` 只检查图片生成依赖。
- `editable`/`upgrade` 再检查 OCR、LibreOffice 或页面重建的可选/必需依赖。
- 可选能力缺失不得阻塞无关路径。

### 6.3 共享图片后端

先提供统一 facade 和配置映射，不要求首版彻底合并两套上游实现。两边能通过同一配置选择相同 provider/model 即达成 MVP；确认重复逻辑稳定后再去重内部代码。

## 7. 实施单元

### U1. 建立统一 package 并导入上游源码

**目标：** 一个环境可导入两个上游能力。

**工作：**

- 创建 `pyproject.toml`、package、CLI 骨架和 Skill 骨架。
- 固定上游 commit、许可证和 notices。
- 将必要源码放入两个清晰的内部命名空间。
- 迁移 editable 现有测试；为 codex 核心脚本建立最小 smoke/fixture 测试。

**完成证据：** 干净环境安装成功；两个 adapter 均可 import；上游回归通过。

### U2. 统一配置、路径和 adapter

**目标：** 两个能力通过同一入口和任务目录运行。

**工作：**

- 实现配置 facade、路径布局和轻量 `run.json`。
- 实现 `doctor`。
- 实现 image backend 配置映射。
- 实现 `generate` 与 `editable` adapter。
- 完成必要的 import/path/config 局部修改。

**完成证据：** 两个命令各自可在 fixture 上运行，并将结果写入同一 run 目录规范。

### U3. 实现统一 Skill 与升级衔接

**目标：** 用户只面对一个 Skill。

**工作：**

- 编写精简 `SKILL.md`，只保留路由、确认点和调用规则。
- 合并必要 reference；页面级规则继续由 editable reference 唯一拥有。
- 保留 codex 的大纲/风格/样张确认流程。
- 实现 `upgrade`：选择页面并把 image-deck 输出映射为 editable 输入。
- 输出 full editable 与 hybrid 的准确交付说明。

**完成证据：** 三条路由均能从 Skill 到 CLI 再到正确 adapter；无需安装旧 Skill。

### U4. 聚焦验证与发布

**目标：** 证明编排有效，而不是证明新平台机制。

**工作：**

- 运行导入的上游测试。
- 增加路由、配置按需检查、跨阶段升级、缺页失败和失败保留测试。
- 运行一个 image-only、一个 direct-editable、一个 selected-page upgrade 的端到端 fixture。
- 校验 wheel 和 Skill bundle。
- 记录已知限制。

**完成证据：** 三条真实路径可执行；产物可打开；结构验证通过；失败不会误报成功。

## 8. 验证策略

### 8.1 必须保留的验证

- editable 上游测试在导入后继续通过。
- codex prompt 准备、图片结果记录和 PPTX 组装有 fixture/smoke 覆盖。
- `doctor` 按命令区分必需和可选依赖。
- `generate` 不因 OCR 缺失而失败。
- `upgrade --pages` 只处理选定页面并保持页序。
- 缺页、页面验证失败或 final deck 构建失败不能报告成功。
- 图片阶段成功、editable 阶段失败时，图片产物仍可交付。
- 两个旧 Skill/CLI 未安装时，统一 package 仍能运行。

### 8.2 端到端验收

MVP 至少完成：

1. Markdown/详细内容稿 → 图片式 PPTX。
2. 图片或 PDF → 可编辑 PPTX。
3. 图片式 PPTX 的指定页面 → hybrid PPTX。

真实图片 provider、OCR 和 Office viewer 的结果分别记录，不把离线 fixture 通过外推为所有环境已验证。

### 8.3 不以文件数量作为质量门

计划不预设 59 个测试文件、8 道 gate 或 11 类 proof。每个新增模块和每个局部修复必须有对应测试；上游已有合同优先由迁移测试保护。

## 9. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 为统一目录而大幅重写上游 | 保留内部命名空间，adapter 只做边界映射 |
| 两套配置继续漂移 | 统一 facade；adapter 不直接读取第二套用户配置 |
| 去重 image backend 引入回归 | 首版先统一接口和配置，内部去重延后 |
| Skill 内容膨胀 | SKILL.md 只保留父级流程，详细规则放 references |
| editable 升级失败影响图片交付 | 两阶段产物隔离，图片阶段结果始终保留 |
| 上游后续更新难同步 | 固定 commit、保留原结构、记录小范围 patch |

## 10. Definition of Done

- 仓库内只有一个用户可发现的 `leo-ppt-generator` Skill。
- 只安装当前 package 即可使用两套源码能力。
- `leo-ppt doctor|generate|editable|upgrade` 可用。
- 两套能力共享依赖环境、配置 facade、图片后端选择和 run 根目录。
- 图片生成、直接可编辑、选择页升级三条路径通过聚焦验证。
- 上游 prompt、算法、manifest 和验证语义没有被静默削弱。
- 不完整结果不会被报告为成功，图片阶段成功结果不会因后续升级失败而丢失。
- 固定上游来源、许可证和本地 patch 可追溯。
- 计划中不包含本目标不需要的平台级状态、调度、安全或审计系统。

## 最终判断

这个项目的最小正确架构是“一个薄 Skill + 一个共享 Python runtime + 两个源码 adapter”，不是“一个新的 PPT 工作流平台”。首版先证明统一入口和三条路径成立；只有真实运行表明现有状态、并发或安全边界无法支撑，才增量引入数据库、调度器或更强隔离。
