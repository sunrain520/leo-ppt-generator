---
artifact_contract: spec-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: spec-plan-bootstrap
status: completed
date: 2026-08-20
deepened: 2026-08-21
title: Top-level PPT Workflow Skill - Embedded Dual-Capability Stabilized Technical Plan
topic: top-level-ppt-workflow-skill
type: feat
supersedes: 2026-08-20-002-feature-ppt-orchestration-skill-plan.md
---

# Top-level PPT Workflow Skill - Embedded Dual-Capability Stabilized Technical Plan

## Goal Capsule

- **产品目标：** 交付唯一可发现的 `leo-ppt-generator` 顶层 Skill，让用户通过一个入口完成图片式 PPT 生成、已有视觉稿转可编辑 PPT、图片版整套或指定页升级可编辑三条路径。
- **产品形态：** 用户只安装当前 Skill；`codex-ppt` 与 `image-to-editable-ppt` 的必要源码、prompt、reference、测试合同和许可证信息全部随当前 Skill 分发，不要求两个旧 Skill 或旧 CLI 存在。
- **编排原则：** 顶层 Skill 拥有意图识别、用户确认、路由、worker 派发、跨阶段衔接和交付判断；内嵌能力只拥有各自领域内的确定性执行与验证。
- **复用原则：** 保留上游已经工作的算法、页面 worker 合同、manifest、状态记录和验证语义；只修改安装、import、资源定位、配置映射、稳定 adapter 和跨阶段组装所必需的部分。
- **运行原则：** 一个 Skill bundle、一个当前受管 Python runtime、一个 `leo-ppt` CLI、一个配置入口和一个 run 根目录；历史 runtime 只为活动 run 的兼容恢复保留，不建设新的通用调度平台或统一数据库。
- **执行 Gate：** 本计划当前可从 U0 开始；U1–U5 只有在 U0 对来源身份、依赖、资源、Office 无网络和 worker 边界给出 `decision: go` 后才能启动。
- **验证焦点：** 先证明干净安装、四条 route、失败保留和交付类型准确，再分别报告真实 provider、OCR、Office viewer 与 PowerPoint 桌面证据。
- **最大未证风险：** 两个上游是否能在同一受管 runtime 中以最小 patch 共存，并保持原状态与 worker 合同。
- **成功标准：** 在没有安装两个旧 Skill/CLI 的干净环境中，仅安装 `leo-ppt-generator` 即可由 Agent 完成三条真实路径，并生成可打开、可验证且交付类型声明准确的 PPTX。

## Product Contract

### 1. 决策结论

采用以下架构：

```text
一个顶层 Workflow Skill
  + 一个随 Skill 分发的受管 Python runtime
  + 两个内嵌、相互隔离的领域能力
  + 一个轻量跨阶段 run index
```

不采用：

- 顶层 Skill 运行时调用两个外部安装的旧 Skill。
- 把两个旧 Skill 继续暴露为用户可发现入口。
- 为统一而重写两个上游的算法、页面状态或 worker 协议。
- 新建 SQLite canonical state、scheduler、daemon、lease 或分布式任务协议。
- 让 Python runtime 模拟 Agent 宿主的用户确认、subagent 或内置图片工具能力。

### Requirements

- R1. 仓库和发布包只暴露一个 `leo-ppt-generator` Skill，用户无需安装两个旧 Skill 或旧 CLI。
- R2. 内容材料必须能够生成经过确认和验证的图片式 PPTX，并保留逐页图片和必要讲稿。
- R3. 图片、PDF 或用户确认可信的 PPT/PPTX 必须能够直接进入对象级可编辑重建，不先重新设计页面。
- R4. 已完成的图片式 PPT 必须支持整套升级或指定页升级；指定页升级必须准确声明 `hybrid` 或经用户确认的 `partial-hybrid`。
- R5. 任一阶段失败都不得误报成功，并且不得删除此前已经通过验证的有效交付物。
- R6. 顶层 Skill 拥有意图、确认、宿主能力判断和 worker 编排；CLI 只拥有确定性准备、状态、验证和组装。
- R7. 两个上游能力必须以固定来源、许可证、最小 patch 和回归证据随当前 Skill 分发，同时继续拥有各自领域状态与验证真值。
- R8. 凭据、用户内容和不可信输入必须遵守最小暴露、明确拒绝和可复核日志边界。
- R9. Skill 必须按当前 Codex 发现与安装机制提供用户级安装指引，并且从任意工作目录都能定位自身脚本、reference、prompt 和 runtime。
- R10. 安装后的 Skill bundle 必须自包含；所有运行时引用都能在 bundle 内解析，不得依赖仓库根目录文档、缺失文件、旧 Skill 或 PATH 中的旧 CLI。
- R11. 首次使用必须经过初始化与 readiness 检查，清楚区分配置有效、本地 runtime 就绪、宿主能力可用和真实 provider/Office/人工验收已完成。
- R12. 内容生成必须先固定受众、目标、场景、时长、叙事主线、事实来源和逐页信息层级，再进入视觉生成；未经内容确认不得批量生成。
- R13. 图片式 PPT 必须经过样张确认、逐页文字准确性、可读性、布局、风格一致性、资产忠实度和整套叙事复核；结构检查不能替代视觉验收。
- R14. 可编辑 PPT 必须验证对象级可编辑性、文字与数据准确性、字体替代、溢出、遮挡、页面尺寸、notes、页序和禁止整页栅格伪装。
- R15. 每次执行必须产出足以回答“失败在哪、是否可重试、保留了什么、下一步是什么”的脱敏状态、时序、诊断、验证和失败报告。
- R16. 发布候选必须通过干净安装、重复安装复用、四 route readiness、离线端到端、Wheel inventory、Skill 结构校验和安装后引用完整性检查。
- R17. 项目必须提供 MIT 许可证、项目 README、用户教程、测试方案、兼容性与已知限制；README 不展示用户明确排除的内部合规与验证报告导航。
- R18. 两个固定上游的每一项登记能力都必须绑定具体、可执行的 proof case；不得以文件存在、聚合数量或抽样结果替代逐项证明。
- R19. 用户输入、prompt、图片、PPTX、凭据引用、日志和失败产物必须有明确的收集、传递、保留与受控清理边界。
- R20. 最终交付必须给出可打开的 PPTX、准确交付类型、hash、验证摘要、失败保留、现场未证项和用户下一步，且任何未运行证据都不得被提升为成功结论。

### 20 轮多角色需求演进

每轮都必须形成“角色目标 → 当前证据 → 冲突或缺口 → 需求/不修改理由 → 验证方式”的记录。轮次是需求与质量闭环，不要求为凑数强行修改代码。

| 轮次 | 主角色 | 核心问题 | 进入计划的增量要求 | 验证焦点 |
| --- | --- | --- | --- | --- |
| 1 | 首次安装用户 | 能否不理解两个上游就安装成功 | 单一 Skill、当前官方发现机制、最短安装路径 | 干净用户目录只出现一个 Skill |
| 2 | 低技术用户 | 首次使用时是否知道缺什么 | 引导式初始化和可执行恢复动作 | 缺 Python、lock、凭据或应用时给稳定原因 |
| 3 | 熟练用户 | 能否从任意项目目录调用 | 所有资源基于 Skill 根目录定位 | 非 Skill cwd 下完成 ensure/doctor/print-cli |
| 4 | 产品经理 | 是否选对生成、直转或升级路线 | 目标优先的路由问题和最少确认集 | 混合输入不会静默选错 route |
| 5 | 演讲者 | PPT 是否服务于受众和现场目标 | 固定受众、场景、时长、行动目标 | 内容合同包含演讲约束与 notes |
| 6 | 内容编辑 | 叙事是否完整且无重复 | 观点主线、章节作用、逐页单一任务 | 大纲和逐页稿通过一致性检查 |
| 7 | 事实编辑 | 数据、名称和引用是否可信 | 事实来源、不可杜撰项和待确认标记 | 关键事实逐项可追溯 |
| 8 | PPT 专家 | 页面是否具有清楚的信息层级 | 页面角色、视觉焦点、阅读顺序和密度预算 | 逐页设计合同覆盖封面、章节、正文、结尾 |
| 9 | 视觉设计师 | 整套是否统一但不模板化 | 视觉 DNA 稳定、布局按语义变化 | 相邻页不机械重复，样张约束可继承 |
| 10 | 图片编辑 | 素材是否真实、清晰且忠于输入 | required asset、裁切、清晰度和 provenance | 输入资产不被相似重绘替代 |
| 11 | 数据表达专家 | 图表是否准确而非装饰 | 数据真值与视觉表达分离 | 图表标签、单位、排序和口径一致 |
| 12 | 无障碍审阅者 | 文字是否可读并适应展示环境 | 对比、字号、长文本、色觉与替代字体检查 | 渲染图无溢出遮挡且关键信息非仅靠颜色 |
| 13 | 可编辑交付用户 | “可编辑”是否名副其实 | 对象级重建和整页栅格禁止项 | 文本、图形、图片对象和 notes 可检查 |
| 14 | 可靠性工程师 | 中断、重放和并发是否安全 | checkpoint、幂等、冲突、恢复和保留 | crash/retry/cancel 不重付费、不误报 |
| 15 | 可观测性负责人 | 出错后能否快速判断与行动 | 状态、时序、操作、诊断和失败报告闭环 | 每个失败有 reason code、证据和安全动作 |
| 16 | 安全与隐私负责人 | 内容和凭据是否被过度暴露 | 最小传递、日志脱敏、保留和受控清理 | 敏感值不进配置、日志和交付报告 |
| 17 | 测试负责人 | 是否覆盖每项功能而非抽查 | 上游逐项 proof、合同/边界/端到端矩阵 | 每个 capability 和 reason code 有可执行锚点 |
| 18 | 发布负责人 | 安装包是否可重复构建和验证 | Wheel、lock、identity、inventory 和 clean install | 发布包无缓存、旧入口和 `third_party/` |
| 19 | 开源维护者 | 用户能否理解许可证、兼容和升级 | MIT、README、教程、兼容与限制分层 | 根目录和 Skill 许可证一致，文档链接有效 |
| 20 | 最终验收人 | 是否能诚实交付高质量 PPT | 分层质量门、现场证据与 claim ceiling | 最终树、最终 Wheel、最终安装和最终 PPTX 同源 |

### 2. 问题定义与设计原则

#### 2.1 真正要解决的问题

两个上游分别拥有成熟能力：

1. `codex-ppt`：从内容生成视觉统一的整页图片式 PPT。
2. `image-to-editable-ppt`：从图片、PDF 或图片型 PPT/PPTX 重建对象级可编辑 PPT。

本项目要解决的是：

- 用户不再选择、安装和理解两个 Skill。
- 两个阶段共享一致的安装、配置和任务目录边界。
- 图片生成结果可以自然进入全量或指定页可编辑升级。
- 失败时保留已经有效的上游阶段产物。
- 当前项目能够独立固定版本、修复缺陷、验证和发布。

#### 2.2 第一性原理边界

- 用户价值来自成功交付 PPT，不来自 runtime 形式上的统一。
- 顶层 Skill 是完整 Workflow 的唯一 owner；CLI 只执行确定性步骤。
- 两个内嵌领域能力可以共享基础设施，但不需要共享内部状态模型。
- 单一安装要求源码和资源随当前 Skill 分发，不要求把所有代码改造成同一种风格。
- MVP 优先证明三条用户路径，平台级完备性只能由真实失败驱动。

#### 2.3 二八原则

首版必须完成的关键 20%：

- 唯一 Skill 发现面和单一安装路径。
- 三条意图路由及必要确认门。
- 两个固定版本上游源码的可追溯内嵌。
- Agent 与 deterministic runtime 的清楚职责边界。
- 图片阶段到 editable 阶段的可靠 handoff。
- 全量 editable 与 selected-page hybrid 的准确组装及声明。
- 三条真实路径、失败保留和误报成功的验证。

首版明确不做的 80% 完备性能力：

- 通用任务数据库、事件溯源和 completion attestation。
- 新的 subagent scheduler、heartbeat、lease 和 attempt quarantine。
- 通用 credential store、旧配置迁移平台和网络策略引擎。
- 多租户/team profile、动态 capability/provider 插件注册和用户自定义 DAG。
- 自建网页抓取器；文章正文由 Agent 使用宿主既有能力取得。
- SSIM 自动视觉回归、密码学证明和逐页审计平台。
- 保证所有复杂视觉元素都成为 PowerPoint 原生对象。

## Planning Contract

### Key Technical Decisions

- KTD1. 采用 `compose / thin-glue`：两个上游继续拥有算法、页面状态和领域验证；顶层只拥有意图确认、有限 route、合同翻译、失败传播和证据聚合。
- KTD2. U0 是实施 gate 而不是第三种 readiness；计划当前可执行，但 U1–U5 必须等待 `docs/reviews/u0-report.md` 的 `decision: go`。
- KTD3. MVP 使用四条 code-owned 有限 route，不建设通用 DAG、动态 capability registry 或 runtime scheduler。
- KTD4. Worker capability 是当前会话事实；CLI 只声明任务需求，顶层 Skill 根据授权、live host capability、容量和实际 outcome 决定派发或 blocked。
- KTD5. runtime 不读取宿主私有认证文件，也不向 worker 传递完整环境；凭据只由宿主管理或经 provider allowlist 引用。
- KTD6. 不可信 Office 输入默认拒绝；MVP 不以“警告后继续”替代隔离能力。
- KTD7. 采用“仓库文档 + 自包含 Skill”双层交付：项目 README 和教程留在仓库根目录，Skill bundle 只保留执行所需资源。这样既满足用户阅读需要，也避免每次触发 Skill 时加载安装与项目治理说明；代价是 release tests 必须验证两层链接和内容不漂移。
- KTD8. Skill 根目录是所有运行资源的唯一解析基准，因为 Codex 可以从任意项目目录触发已安装 Skill。cwd-relative 路径虽短但不可移植，因此任何仓库外链接、缺失 reference 或对 PATH 旧 CLI 的依赖都是发布阻断项。
- KTD9. 安装文档同时覆盖当前官方用户级发现位置与内置 `skill-installer` 的实际目标位置，并明确来源 ref。只写其中一条会掩盖当前产品与安装器实现差异；本地 bundle fixture 只能证明包可安装，不能证明 GitHub 已发布。
- KTD10. PPT 质量采用五层非补偿式门禁：内容事实、叙事结构、视觉呈现、PPTX 结构/可编辑性、现场打开与人工验收。单一综合分数会允许严重错误被其他高分抵消，因此每层分别拥有 required/deferred 状态和 claim ceiling。
- KTD11. 20 轮多角色审视是发布治理输入，不成为 runtime 状态机或新的动态工作流平台。这样保留角色冲突带来的需求价值，同时避免为一次发布审查引入永久编排复杂度；相同缺口只保留一个 canonical owner 和一组验证证据。
- KTD12. 可观测性服务于恢复决策：信号必须能回答 stage、page、operation、耗时、重试性、保留产物和下一安全动作。记录正文或完整环境虽便于临时调试，但会扩大隐私风险，因此只允许结构化 allowlist、hash 和 credential reference。

### Evidence & Limitations

- 当前 `HEAD` 仍为 `2230fa83bf358a64386d21b97765c5421d4537df`，大量实现位于未提交工作树；最终证据必须绑定最终工作树 fingerprint，不能只绑定 `HEAD`。
- 当前源码已经具备四 route、runtime manager、backend contract、adapter、hybrid、幂等 run index、配置、diagnose、cleanup、observability 和发布文档；这些存在性事实不等于最终回归或现场质量已通过。
- 当前 Skill 正文和 worker prompt 存在安装后断链候选：cwd-relative runtime manager、缺失 `references/cli-helper.md`、不存在的 `scripts/image_gen.py` 和仓库外文档引用。它们在修复与 clean-install proof 前构成发布阻断。
- OpenAI 官方 Skill 文档（2026-08-21 获取）将用户级发现位置列为 `$HOME/.agents/skills`，而当前内置 `skill-installer` 实现安装到 `$CODEX_HOME/skills`（默认 `~/.codex/skills`）；文档和测试必须如实覆盖两条当前机制。
- 当前工作树包含既有修改、删除和未跟踪文件；实施必须在目标仓库内保持写集归属，不得覆盖或归因无关改动。
- 两个上游固定身份、逐文件哈希、patch 和能力账本已进入当前树；仍需在最终树逐项重跑 proof，不能复用中间工作树结论。
- 真实图片 provider、OCR、Office viewer、PowerPoint 桌面与人工视觉仍受当前宿主、凭据和应用可用性约束；不可用时只能形成明确的 field limitation。

### 3. 总体架构

```text
User
  │
  ▼
skills/leo-ppt-generator/SKILL.md
  │  唯一发现面；意图、确认、路由、worker、交付
  ▼
scripts/runtime_manager.py
  │  确保随 Skill 分发的 runtime 已安装且版本匹配
  ▼
leo-ppt CLI / leo_ppt_generator package
  ├── application/run_index.py
  ├── config/backend_contract.py
  ├── image_deck/adapter.py
  │     └── _vendor/codex_ppt/
  ├── editable/adapter.py
  │     └── _vendor/editable_ppt/
  └── hybrid/assembler.py
```

用户旅程与质量门按以下顺序推进；这是责任与证据关系图，不规定实现内部调用细节：

```text
发现/安装
  → Skill 自包含与 runtime ensure
  → route-specific doctor
  → 输入、受众、目标与信任边界确认
  → 内容合同（事实 → 叙事 → 逐页稿）
  → 视觉/可编辑策略与样张确认
  → worker 执行 + 幂等状态 + 时序记录
  → 内容质量门
  → 视觉质量门
  → PPTX 结构/可编辑质量门
  → provider/OCR/Office/人工现场证据
  → 准确交付类型 + validation/failure report + 恢复动作
```

每个箭头只消费前一步的 versioned artifact 或明确用户确认。未知协议、缺失证据或质量门失败时保留已有有效产物并停止推进，不允许自由文本“看起来完成”跨越门禁。

#### 3.1 唯一用户发现面

仓库和发布包中只有以下文件可作为 Skill 被发现：

```text
skills/leo-ppt-generator/SKILL.md
```

两个旧 `SKILL.md` 不原路径保留在 `skills/` 下，也不嵌套到当前 Skill 的可发现目录中。其仍需保留的规则按以下方式迁移：

- 顶层路由和确认规则合并到新的 `SKILL.md`。
- 图片生成详细流程进入 `references/image-deck-workflow.md`。
- 可编辑重建详细流程进入 `references/editable-workflow.md`。
- manifest 与页面决策规则作为独立 reference 保留唯一 owner。
- slide/page worker 执行合同原样或最小改造后进入 `prompts/`。
- 原始上游 Skill 文档不复制进发布包；只提取执行所需合同到当前 `references/`、`prompts/` 和能力账本，溯源由固定 commit、hash、patch 与仓库级记录承担。

#### 3.2 顶层 Skill 的职责

顶层 `SKILL.md` 只保留完整 Workflow 必需的规则，目标控制在 500 行以内。它负责：

- 识别输入是内容材料、视觉页面、已有 image-deck run 或混合输入。
- 判断 `generate`、`direct-editable`、`upgrade-full`、`upgrade-selected` 路由。
- 获取会改变结果的最少必要信息。
- 执行大纲、完整内容稿、风格、图片后端、样张和升级范围确认。
- 在宿主支持时派发 slide/page worker，并遵守内嵌 worker 合同。
- 调用确定性 CLI，依据 CLI 产物而非聊天声明推进阶段。
- 在两个能力间传递已确认的路径、页序、页面选择和 backend contract。
- 报告最终交付物、交付类型、验证结果、限制和可恢复产物。

顶层 Skill 不负责：

- 在 Markdown 中重新实现图片或 PPTX 算法。
- 手写上游领域状态文件。
- 用主 Agent 顺序执行替代上游要求的多页 worker。
- 把结构验证通过外推为视觉完全等价。

#### 3.3 内嵌 image-deck 能力

来源：固定版本的 `codex-ppt`。

保留：

- 内容、大纲、风格、后端和样张确认合同。
- slide prompt 准备与单页 worker 合同。
- 图片 provider fallback、结果记录、页面状态、QA、讲稿和组装算法。
- `slide_jobs.json` 与 `slide_run_state.json` 的领域语义。

允许修改：

- package import 与资源定位。
- 配置读取改为从统一 backend contract 映射。
- 输出根目录由 adapter 注入。
- 组装前对预期页集合、页序和缺页进行 hard fail。
- provider 类型不再依赖不安全的域名子串猜测。

不允许修改：

- 样张批准后保持同一图片生成方法的合同。
- 每页最终图片必须来自确认后的图片后端。
- required asset、页面结果记录和未完成页面不得组装成功的语义。

#### 3.4 内嵌 editable 能力

来源：固定版本的 `image-to-editable-ppt`。

保留：

- 图片、PDF、PPT/PPTX 输入规范化。
- OCR/text hints、page worker、页面对象决策树和图片处理能力。
- `manifest.json` 作为页面构建权威。
- prepare、dispatch、record、reset、validate、finalize 的领域语义。
- `page_jobs.json` 与页面级状态。

允许修改：

- package import、资源定位、配置和输出根目录。
- 接受来自 image-deck adapter 的规范化逐页图片和 notes 映射。
- finalizer 在交付前重新确认 manifest、asset 和 notes 的当前一致性。
- 对 selected-page 模式暴露页面级产物，而不让原 finalizer误报全量 editable。

不允许修改：

- 用整页截图叠加少量文本框冒充可编辑结果。
- 绕过 manifest、record 或 top-level validation result。
- 在多页输入无 worker 能力时静默降级为主 Agent 顺序重建。

#### 3.5 hybrid assembler

`hybrid/assembler.py` 是本项目唯一新增的 PPT 领域能力，负责 selected-page upgrade：

- 选中页使用 editable manifest 重建的页面。
- 未选中页使用原 image-deck 的整页图片。
- 保持原始页数、页序、页面尺寸和演讲者备注。
- 为每页记录最终 delivery representation、producer 和来源路径/hash。
- 任一选中页未通过 editable validation 时拒绝声明 hybrid 完成。
- 不把 hybrid 声称为全量 editable。

hybrid assembler 不负责页面重建，不解释 editable manifest 之外的对象语义。

##### 3.5.1 组装前置条件

hybrid assembler 在组装前必须验证以下不变量，任一不满足则进入 `blocked/assembly_precondition_failed`：

| 前置条件 | 验证方法 | 失败原因示例 |
| --- | --- | --- |
| 页面数量一致 | `len(selected_pages) == len(editable_artifacts)` | selection 10 页但 editable 只返回 9 个 PageArtifact |
| 页面顺序对应 | editable artifacts 的 page_id 顺序匹配 selection 顺序 | selection [3,1,5] 但 artifacts 返回 [1,3,5] |
| 页面尺寸一致 | 所有 editable 页面的 width/height 等于对应 image 页面 | image 16:9 但 editable 重建为 4:3 |
| 全部验证通过 | 所有 selected pages 的 validation_ref 指向 status=passed | page 3 的 validation 为 failed 或 missing |
| Notes 映射完整 | source notes 对每个页面都有明确映射（可为空字符串） | image page 5 有 notes 但 editable 未提供映射 |
| Source hash 冻结 | 每个 editable PageArtifact 的 source_hash 匹配 selection 冻结时的 image hash | selection 后 image 页面被修改 |
| Total page count | final page count == image-deck 原始页数 | 组装后 PPTX 只有 8 页但原始 image deck 有 10 页 |

验证失败时：

- 不尝试自动修复或降级。
- 返回结构化诊断报告，指明失败的具体条件、预期值和实际值。
- 保留已完成的 editable PageArtifact 和 image deliverable。
- 建议用户检查 selection、重新 prepare 或放弃 upgrade。

#### 3.6 内部能力合同

顶层 application、CLI 和其他能力不得直接 import `_vendor`。两个上游只通过对应 adapter 暴露的版本化内部合同被调用：

```python
class CapabilityAdapter(Protocol):
    capability_id: str
    contract_version: int

    def prepare(self, request: PrepareRequest) -> PrepareResult: ...
    def inspect(self, run_ref: RunRef) -> CapabilityStatus: ...
    def finalize(self, run_ref: RunRef) -> DeliveryArtifact: ...
```

合同规则：

- request/result 使用当前项目拥有的 dataclass 或 versioned JSON schema，不把 vendor dict 直接透传到顶层。
- adapter 负责把统一合同映射到 vendor 路径、状态、命令和错误。
- vendor 内部字段变化只能影响对应 adapter 和上游回归测试。
- `capability_id` 稳定，破坏性接口变化提升 `contract_version`。
- 未知 required field、未知 contract version 或无法映射的 vendor 状态 fail closed。
- 通过 import-boundary 测试禁止 `application/`、`cli.py`、`hybrid/` 直接引用 `_vendor`。

MVP 不建设动态插件发现或第三方 capability SDK；该合同只用于控制当前两个领域能力与 hybrid assembler 的内部耦合。

#### 3.7 页面交接合同

跨能力和 hybrid 组装只消费统一 `PageArtifact`，不直接消费 vendor 私有目录或状态：

```json
{
  "schema_version": 1,
  "page_id": "page_003",
  "representation_kind": "full-slide-image|object-editable",
  "producer_id": "image-deck|editable",
  "width_inches": 13.333,
  "height_inches": 7.5,
  "render_ref": "...",
  "build_ref": "...",
  "notes_ref": "...",
  "source_hash": "...",
  "validation_ref": "..."
}
```

- image-deck adapter 将逐页最终图片映射为 `representation_kind=full-slide-image`。
- editable adapter 在 manifest 和 validation 通过后映射为 `representation_kind=object-editable`。
- `build_ref` 对 image 页面为空，对 editable 页面指向可由 manifest 重建的页面合同。
- hybrid assembler 只按 `PageArtifact` 组合页面、notes 和页序。
- `PageArtifact` 不替代 editable manifest；它是跨能力交付边界。
- 新增页面生产能力时，只需产生相同合同，不修改 hybrid 主逻辑。

#### 3.8 四条有限 route 合同

MVP 不实现通用 DAG parser、cycle detector 或动态 capability registry。代码只拥有以下四条有限 route；每条 route 的步骤、输入、完成条件和失败保留语义都是 release 合同：

| Route | 固定步骤 | 必要输入 | 完成条件 | 失败保留 |
| --- | --- | --- | --- | --- |
| `generate` | `image.prepare → image.work → image.assemble` | 内容、确认后的风格与 backend | image-deck validation 通过且 PPTX 可打开 | 保留已记录页面和诊断证据 |
| `direct-editable` | `editable.prepare → editable.work → editable.finalize` | 图片/PDF 或确认可信的 Office 输入 | 全部目标页及 deck validation 通过 | 保留 PageArtifact、manifest 和失败证据 |
| `upgrade-full` | `image.inspect → editable.prepare → editable.work → editable.finalize` | 已完成 image run | 全部页面为已验证 editable representation | 原 image deliverable 始终有效 |
| `upgrade-selected` | `image.inspect → editable.prepare → editable.work → hybrid.assemble` | 已完成 image run、冻结的 selection | 默认全部选中页通过；经确认才允许 partial | 原 image deliverable 与成功的单页产物保留 |

规则：

- `application/routes.py` 是四条 route 的唯一代码 owner；`run.json` 只记录所选 route、当前 step 和 step artifact refs，不保存可注入的步骤定义。
- route 只能引用 `image-deck`、`editable` 和 `hybrid-assembler` 三个已知 capability；未知 route、step 或 capability fail closed。
- 顶层 Skill 根据 CLI 返回的 step status 和 live host capability 决定下一动作；CLI 不拥有 worker scheduler，也不推断宿主是否支持 agent。
- 新增第五条 route 或第四个 capability 必须修改代码、canonical schema、测试和 release notes；不承诺“只加配置即可扩展”。

### Interface Contracts

| Interface | Consumers | Canonical artifact / owner | Compatibility | Verification |
| --- | --- | --- | --- | --- |
| CLI machine result v1 | 顶层 Skill、diagnose、测试 | `runtime/src/leo_ppt_generator/schemas/command-result-v1.schema.json` / U3 | v1 内只允许新增 optional 字段；required/改义提升版本 | JSON Schema parser + route behavior eval |
| Four-route table | 顶层 Skill、run index | `runtime/src/leo_ppt_generator/application/routes.py` / U3 | code-owned finite set；新增 route 是 release 变更 | `tests/unit/test_routes.py` |
| PageArtifact v1 | 两个 adapter、hybrid assembler | `runtime/src/leo_ppt_generator/schemas/page-artifact-v1.schema.json` / U2 | 未知 required/version fail closed | schema parser + adapter contract tests |
| Delivery v1 | finalizer、用户报告 | `runtime/src/leo_ppt_generator/schemas/delivery-v1.schema.json` / U4 | representation enum 改义需提升版本 | schema parser + full/hybrid fixtures |
| Backend contract v1 | Skill、provider adapter、worker prompt | `runtime/src/leo_ppt_generator/schemas/backend-contract-v1.schema.json` / U2 | credential reference 不得变成 secret value；breaking change 提升版本 | parser + credential-boundary tests |
| Skill discovery and bundle-root contract | Codex、用户、runtime manager、worker prompts | `SKILL.md` + `agents/openai.yaml` / U6 | 安装位置可并存，但资源统一以当前 Skill 根目录解析 | clean-install + arbitrary-cwd + reference-graph tests |
| PPT quality-gate contract | 顶层 Skill、worker prompts、finalizer、用户报告 | route references + `delivery-v1.schema.json` / U8 | 新增检查可 additive；降低 required gate 或改变 claim 属于 release 变更 | behavior eval + render/structure/editability fixtures |

所有路径均相对 `skills/leo-ppt-generator/`。完整字段由 canonical schema 拥有，本计划只固定 owner、消费者、演化边界和验证方法。

### 4. 单一安装与发行合同

#### 4.1 安装目标

用户只安装 `leo-ppt-generator` Skill。Skill bundle 内必须包含：

- 顶层 `SKILL.md`、`agents/openai.yaml`、prompts 和 references。
- `runtime/` 下完整可安装的 Python package。
- 两个固定版本的必要上游源码和运行资源。
- runtime manager、上游元数据、许可证和 notices。

用户级安装必须覆盖两种当前机制：

- 通过 Codex 内置 `$skill-installer` 从 GitHub 仓库的 `skills/leo-ppt-generator` 子目录安装；安装器当前目标为 `$CODEX_HOME/skills`，默认 `~/.codex/skills`。
- 手动或开发态把同一 Skill 目录放入当前官方用户级发现位置 `$HOME/.agents/skills/leo-ppt-generator`。

安装文档必须标注来源 revision/ref、同名目录冲突行为和 Codex 重新发现条件。未提交工作树只能用于本地 bundle fixture，不能声称 GitHub 已发布该版本。

不得要求用户另行执行：

- 安装 `codex-ppt` Skill。
- 安装 `image-to-editable-ppt` Skill。
- 安装旧 `editppt` CLI。
- 从两个上游仓库复制文件。

#### 4.2 受管 runtime

`scripts/runtime_manager.py` 提供：

所有命令都从宿主提供的 Skill 文件路径解析 `SKILL_DIR`，再调用
`$SKILL_DIR/scripts/runtime_manager.py`。不得依赖用户当前工作目录恰好是 Skill 根目录。

行为合同：

- runtime 按不可变 identity 安装到 `${LEO_PPT_HOME}/runtimes/<runtime_identity>/`，默认根目录使用平台用户数据目录。
- `${LEO_PPT_HOME}/current` 只在新环境通过安装、doctor 和最小 smoke 后原子切换。
- Skill bundle 内的 runtime identity 变化时创建新环境，不原地修改旧环境。
- 不把 token 写入 Skill 安装目录或任务目录。
- `ensure` 使用安装锁且幂等；并发调用只允许一个安装者，失败时保留旧 `current` 并报告依赖、路径和修复动作。
- 已存在 identity 校验失败时，`ensure` 在锁内把该精确目录移动到同根 quarantine，并重新安装；不得让用户手工递归删除宽泛 runtime 路径。
- `print-cli` 返回当前 Skill 对应的准确 `leo-ppt` 可执行路径，避免命中旧环境同名命令。

#### 4.3 Runtime identity、恢复与回滚

`runtime_identity` 至少绑定：

- 当前 Skill runtime source hash。
- 两个上游 commit/tree hash 和本地 patch hash。
- dependency lock hash。
- Python major/minor、操作系统和 CPU architecture。

每个 run 在创建时固定 `runtime_identity`。恢复规则：

- 未完成 run 默认继续使用创建它的 runtime，不能被最新 `current` 静默接管。
- 新 runtime 只有在声明兼容并通过旧 run fixture 时，才能打开旧 identity 创建的 run。
- 缺少原 runtime 且不存在已验证迁移时，进入 `blocked/runtime_incompatible`，不得猜测继续。
- 删除旧 runtime 前必须确认没有未完成 run 引用；MVP 至少保留 `current`、上一个健康版本以及被活动 run 引用的版本。
- 新 runtime 安装、doctor 或 smoke 失败时不切换 `current`；显式 rollback 只切回已验证的旧 identity，不修改任务产物。

#### 4.4 可复现依赖

- `pyproject.toml` 表达支持范围，发布产物同时包含经验证的 constraints/lock。
- 干净安装严格使用 lock；source identity 相同但 lock、Python 或平台不同，runtime identity 必须不同。
- U0 验证支持的 Python major/minor 和目标平台组合，不能只在开发机已有环境中安装。
- 明确首次 bootstrap 是否需要网络；如果声明离线可安装，Skill bundle 必须携带对应平台 wheelhouse，否则只声明源码自包含、依赖安装需要网络。
- 上游仅使用 `>=` 的依赖声明不能直接作为发布锁；由当前项目统一解析、测试和固定实际版本。
- 发布前保存 `pip check`、安装报告和 lock hash，不把“安装成功”外推为 provider/OCR 已就绪。

#### 4.5 建议目录结构

```text
leo-ppt-generator/
├── skills/leo-ppt-generator/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── scripts/runtime_manager.py
│   ├── prompts/
│   │   ├── slide-worker.md
│   │   └── page-worker.md
│   ├── references/
│   │   ├── image-deck-workflow.md
│   │   ├── editable-workflow.md
│   │   ├── input-routing.md
│   │   ├── backend-selection.md
│   │   ├── reason-codes.md
│   │   ├── manifest-schema.md
│   │   └── page-decision-tree.md
│   ├── runtime/
│   │   ├── pyproject.toml
│   │   ├── constraints/
│   │   └── src/leo_ppt_generator/
│   │       ├── cli.py
│   │       ├── contracts.py
│   │       ├── application/routes.py
│   │       ├── application/run_index.py
│   │       ├── config/backend_contract.py
│   │       ├── config/runtime_config.py
│   │       ├── lifecycle.py
│   │       ├── observability.py
│   │       ├── image_deck/adapter.py
│   │       ├── editable/adapter.py
│   │       ├── hybrid/assembler.py
│   │       ├── schemas/
│   │       └── _vendor/
│   │           ├── codex_ppt/
│   │           └── editable_ppt/
│   ├── upstreams.yaml
│   ├── vendor-lock.json
│   ├── patches/
│   ├── LICENSE.codex-ppt
│   └── LICENSE.image-to-editable-ppt
├── tests/
│   ├── upstream/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── skill-evals/
└── docs/plans/
```

运行时需要的源码和资源全部位于 Skill bundle 内；仓库级测试和计划不进入 Skill 上下文。

### 5. Agent 与 CLI 的接口边界

#### 5.1 原则

`leo-ppt` CLI 不是无人值守的完整 PPT agent。它只提供确定性阶段能力和可机器读取的结果。

Agent 负责：

- 理解内容和用户意图。
- 提问与确认。
- 调用宿主内置图片工具。
- 创建和管理 slide/page worker。
- 根据 CLI 的 `next_action` 推进 Workflow。

CLI 负责：

- 创建 run 目录和跨阶段索引。
- 准备确定性输入、job、prompt 和页面产物目录。
- 调用内嵌上游脚本或库。
- 记录结果、验证产物、组装 PPTX。
- 输出结构化状态、证据路径和下一动作。

#### 5.2 稳定命令面

```bash
leo-ppt doctor --route generate|direct-editable|upgrade-full|upgrade-selected
leo-ppt run create --route <route> --input <path> --output <dir> --backend-contract <path> [--idempotency-key <key>]
leo-ppt run status <run> --json
leo-ppt run diagnose <run> --json
leo-ppt run operation <run> --id <operation-id> --json
leo-ppt run retry <run> [--from-failed-pages]
leo-ppt run cancel <run> --wait-workers
leo-ppt run cleanup <run> --scope temp|failed-attempts|input --dry-run|--apply

leo-ppt image prepare <run>
leo-ppt image record <run> --slide <id> --agent-id <id> --result <path> [--expected-state-hash <hash>]
leo-ppt image assemble <run> [--rebuild]

leo-ppt editable prepare <run> [--pages <list>]
leo-ppt editable next <run> --json
leo-ppt editable dispatch <run> --page <id> --agent-id <id> --prompt-file <path>
leo-ppt editable record <run> --page <id> --agent-id <id> [--expected-state-hash <hash>]
leo-ppt editable reset <run> --page <id> [--confirm-lost]
leo-ppt editable finalize <run>

leo-ppt upgrade finalize <run> [--allow-partial]
```

顶层 Skill 可以只展示 Workflow，不向用户暴露这些内部命令。
`editable dispatch` 只在宿主已接受派发后记录 agent/page 绑定和 expected state；它不能调用、发现或模拟宿主 agent。

#### 5.3 幂等性与重试合同

| 命令 | 相同输入重复调用 | 输入或状态不同 |
| --- | --- | --- |
| `run create --idempotency-key` | 相同 key、route 和 input hash 返回原 run | 相同 key 但 fingerprint 不同返回 conflict |
| `image prepare` | fingerprint 相同返回已有 jobs | 不同 fingerprint 要求新 run 或显式重建 |
| `image record` | 相同 slide、agent、result hash 返回原成功 | hash 或 expected state 不同返回 conflict，禁止覆盖 |
| `image assemble` | 页面 hash 集合相同返回已有 PPTX | 页面集合变化要求显式 `--rebuild` 并产生新 artifact revision |
| `editable prepare` | input/selection/backend hash 相同返回已有结果 | fingerprint 不同拒绝复用 |
| `editable dispatch` | 同一 page 已由同一 agent active 时返回已有 dispatch | 不同 agent 或状态冲突拒绝 |
| `editable record` | 相同 page、agent、manifest/result hash 返回原成功 | hash 或 expected state 不同返回 conflict，需先 reset |
| `editable finalize` | recorded manifest 集合相同返回已有 PPTX | manifest 集合变化拒绝复用并要求重新验证 |
| `upgrade finalize` | selection 与 PageArtifact hash 相同返回已有交付物 | 变化后生成新 artifact revision，不覆盖旧交付物 |
| `run retry` | 相同失败集合和 state hash 返回同一 retry operation | 状态变化时返回 conflict 并要求重新 diagnose |
| `run cancel` | 已 cancelled 返回原 terminal operation | active/completed 状态变化时返回 conflict；`safe_to_retry=false` |
| `reset`、`cleanup --apply` | 非自动重试 mutation | 必须显式确认范围和当前状态 |

每个 mutation 返回：

```json
{
  "operation_id": "...",
  "idempotency_status": "created|replayed|conflict",
  "safe_to_retry": true,
  "state_hash": "..."
}
```

- 顶层 Skill 只在 `safe_to_retry=true` 时自动重试，并沿用同一 idempotency key。
- 网络或宿主丢失响应时，先查询 operation/status，不创建新 mutation。
- `conflict` 必须重新读取状态并诊断，不允许盲重试。
- 非幂等 mutation 不进入通用自动重试循环。

#### 5.4 机器结果合同

所有推进 Workflow 的命令在 `--json` 模式至少返回：

```json
{
  "schema_version": 1,
  "run_id": "...",
  "route": "generate|direct-editable|upgrade-full|upgrade-selected",
  "stage": "image.sample_approval",
  "status": "ready|waiting_for_user|waiting_for_worker|blocked|failed|interrupted|completed|cancelled",
  "next_action": {
    "kind": "request_sample_approval|request_worker_dispatch|wait_completion",
    "payload": {
      "sample_path": "...",
      "allowed_decisions": ["approve", "revise", "cancel"]
    }
  },
  "progress": {
    "total_units": 10,
    "completed": 7,
    "failed": 1,
    "active": 1,
    "pending": 2,
    "estimated_remaining_seconds": 360
  },
  "reason_code": null,
  "artifact_refs": [],
  "evidence_refs": [],
  "warnings": [],
  "blockers": []
}
```

该结果只索引上游事实，不取代 `slide_jobs.json`、`slide_run_state.json`、`page_jobs.json`、manifest 或 validation。

机器协议规则：

- `route`、`stage`、`status`、`next_action.kind` 和 `reason_code` 使用文档化稳定枚举。
- `message` 等自由文本可以用于展示，但不得驱动 Workflow 控制流。
- `next_action.payload` 按 `kind` 使用 versioned schema，引用路径必须位于当前 run 或 Skill bundle 的允许范围。
- 新增 optional 字段可以保持 schema version；删除、改义或新增 required 字段必须提升版本。
- 未知 required 字段、未知 schema version、状态与 CLI exit code 不一致时 fail closed。
- CLI 为配置、依赖、输入、状态冲突、validation 和 runtime incompatibility 提供稳定 reason code。
- 顶层 Skill 行为 eval 必须证明它依据结构化字段推进，而不是匹配命令输出文案。

##### 5.4.1 Worker 派发请求与宿主判定

当 `next_action.kind = "request_worker_dispatch"` 时，CLI 只返回任务需求，不声明当前宿主具备 worker 能力：

```json
{
  "kind": "request_worker_dispatch",
  "payload": {
    "dispatch_requirement": "multi_agent_required|single_unit_current_agent_allowed",
    "page_count": 10,
    "estimated_duration_per_page_seconds": 180,
    "suggested_max_concurrent": 4,
    "runtime_fallback": false
  }
}
```

判定规则：

- 顶层 Skill 在每次派发前分别确认用户授权、当前会话可见的 host capability、容量和实际调用结果；静态配置或 CLI `doctor` 不能证明这些事实。
- `multi_agent_required` 用于多页生成或重建。宿主能力缺失、未知或调用失败时进入 `blocked/worker_capability_unavailable`，不得让主 Agent 静默串行处理整套页面。
- `single_unit_current_agent_allowed` 只适用于恰好一页，并且当前 Agent 能完整遵守同一 worker prompt、record 和 validation 合同的场景。
- `runtime_fallback=false` 是 MVP 固定值。只有 U0 证明上游已经存在等价、确定性的本地页面执行器，后续计划修订才可引入 runtime fallback。
- `suggested_max_concurrent` 只是任务建议；实际并发由宿主容量和 provider 限流共同约束。
- 每次派发记录 `dispatch_requested|dispatch_started|dispatch_failed|dispatch_completed` outcome；permission、capacity 和 execution success 分开报告。

##### 5.4.2 进度报告

`progress` 字段为可选，当 status 为 `waiting_for_worker` 时应包含：

- `total_units`：总工作单元数（通常为页面数）。
- `completed`：已完成单元数。
- `failed`：已失败单元数。
- `active`：已经派发但尚未形成最终记录的单元数。
- `pending`：尚未派发的单元数（total - completed - failed - active）。
- `estimated_remaining_seconds`：预估剩余时间，基于已完成单元的平均耗时。

规则：

- 进度只反映已确认的结果，不预测未完成任务。
- `estimated_remaining_seconds` 为 null 表示无法估算（样本不足或耗时波动大）。
- 进度更新频率由 CLI 控制，Agent 不应高频轮询（建议 ≥ 5 秒间隔）。
- 进度不是完成的真值，只用于用户展示；status 和 artifact 仍是权威。

### 6. 运行目录与状态所有权

```text
<run>/
├── run.json
├── input/
├── tmp/              # 可安全重建的临时文件
├── work/             # attempt、worker 中间产物和失败证据
├── image-deck/
│   └── 保留 codex-ppt 的领域目录和状态文件
├── editable/
│   └── 保留 editable 的领域目录和状态文件
├── logs/
├── events.ndjson
├── reports/
└── final/
    ├── deck.pptx
    ├── delivery.json
    ├── failure-report.json   # partial-hybrid 或升级失败时存在
    └── validation-summary.json
```

#### 6.1 `run.json`

`run.json` 是轻量跨阶段索引，只记录：

- schema version、单调 revision 和创建该 run 的 runtime identity。
- run id、route 和创建时间。
- 输入与规范化输入路径。
- image-deck 和 editable 子运行路径。
- selected pages、页序和 notes 映射。
- 当前阶段、最终交付物和交付类型。
- 上游源码 identity 与 backend contract hash。

规则：

- 只有顶层 CLI 可以写入；slide/page worker 和 vendor 代码不得直接写入。
- mutation 使用 file lock、`expected_revision`、临时文件、fsync 和原子替换；revision 不匹配时拒绝覆盖并要求重新读取。
- 不复制页面级状态。
- 不单独决定页面是否完成。
- `status`、恢复和 finalize 前必须根据上游状态、正式产物和 hash 做 reconciliation，不盲信缓存 stage。
- reconciliation 只能修正可由领域事实唯一推导的索引；无法证明的一致性进入 `blocked/state_mismatch`。
- `delivery.json` 是 finalizer 从 selection 和页面产物派生的不可手写交付报告，不与 `run.json` 共同拥有 selection 真值。

#### 6.2 持久化等级与 checkpoint barrier

按文件职责固定持久化等级，不提供会让用户关闭关键持久化的配置：

| 等级 | 写入步骤 | 适用对象 |
| --- | --- | --- |
| cache | 普通写入，可丢失并重建 | contact sheet、可重建预览、临时下载 |
| durable-file | temp write → flush → fsync(file) → atomic replace | worker result、非入口正式 JSON |
| barrier | durable-file → fsync(parent directory) | `run.json`、vendor job/run state、`delivery.json`、`validation-summary.json`、runtime `current` pointer |

规则：

- barrier 成功后才能向调用者返回 mutation 成功；如果平台不支持目录 fsync，记录 `durability=degraded` 并在 doctor 中明确，不伪称完整 barrier。
- 正式 PPTX、manifest、asset 和 notes 在进入 recorded/finalized 状态前必须 flush/fsync 并记录 hash。
- 临时文件命名包含 operation id，启动 reconciliation 可识别并删除未晋级 temp；不得按模糊 glob 删除未知文件。
- 状态先声明 completed、产物后落盘的顺序被禁止；必须先持久化候选产物和 hash，再 barrier 提交状态索引。
- 对 API 已消费但状态未确认的场景，通过 result hash、operation id 和现有文件恢复，不能自动重新调用付费 provider。

#### 6.3 状态 owner

| 状态或合同 | 唯一 owner |
| --- | --- |
| Workflow 路由与跨阶段路径 | `run.json` |
| 图片页面 job 和结果 | image-deck 上游状态 |
| editable 页面 job 和结果 | editable 上游状态 |
| editable 页面对象 | `manifest.json` |
| selected-page 选择 | `run.json` |
| 最终 PPTX 交付类型 | finalizer/hybrid assembler |
| 最终逐页交付报告 | 由 finalizer/hybrid assembler 派生的 `delivery.json` |

#### 6.4 最小可观测性与诊断

```text
<run>/
├── logs/run.log
├── logs/workers/<unit_id>.log
├── events.ndjson
└── reports/
    ├── timing.json
    └── diagnosis.json
```

- `events.ndjson` 由顶层 CLI 在 event lock 下追加单调 seq、时间、actor、event kind、subject、status、operation id 和 evidence refs；不拥有 Workflow 状态，尾部不完整事件可在 diagnose 中截断到最后一个合法边界。
- 日志采用字段 allowlist 和脱敏 credential/provider 信息，不写正文、OCR 全文、token 或任意环境变量 dump。
- worker 各自写独立日志，避免并发拼接同一自由文本文件；顶层只通过 evidence ref 聚合。
- `timing.json` 记录阶段、页面和 provider 调用耗时，不把性能统计作为完成真值。
- MVP 不建设远程 telemetry、指标服务或自动上传。

##### 6.4.1 日志级别与调试模式

日志级别（CLI stderr 和 run.log）：

| 级别 | 内容 | CLI 默认输出 | run.log |
| --- | --- | --- | --- |
| ERROR | 失败和阻塞 | ✅ | ✅ |
| WARNING | 降级、重试和可恢复问题 | ✅ | ✅ |
| INFO | 阶段转换和关键决策 | ✅ | ✅ |
| DEBUG | 详细执行和状态变化 | ❌（需 --verbose） | ✅ |
| TRACE | Vendor 内部调用 | ❌（需 --trace） | ❌（仅开发） |

日志格式（结构化 JSON Lines）：

```json
{"timestamp": "2026-08-20T10:30:45.123Z", "level": "INFO", "component": "image-deck.adapter", "event": "slide_recorded", "slide_id": "slide_003", "duration_ms": 1234}
```

调试模式（`LEO_PPT_DEBUG=1` 或 `--debug`）：

- 保留所有临时文件（tmp/ 不自动清理）
- 输出详细的状态转换（每次 run.json mutation）
- 记录 backend adapter、endpoint origin、HTTP method、status、duration 和 retry count；不记录 URL query、headers 或 request/response body
- 不删除失败的 worker 输出
- worker logs 仍遵守同一字段 allowlist；TRACE 只能记录代码路径和状态转换，不记录 prompt、用户内容或 provider payload

脱敏规则：

- Credential：只记录 `credential_status: available|expired|missing`，不记录值
- API keys 和 token：不记录前缀、后缀、长度或 hash；只记录 provider、reference type 和可解析状态
- 用户内容：不记录完整正文、OCR 全文或 prompt 内容（只记录 hash 和长度）
- 环境变量：只记录已知安全的变量（如 `LEO_PPT_HOME`），不 dump 全部环境

`leo-ppt run diagnose <run> --json` 至少检查：

- runtime/config/protocol compatibility。
- `run.json` revision 与有限 route step 可达性。
- vendor 状态、PageArtifact、正式产物和 hash 一致性。
- 缺失文件、未晋级 temp、active/failed worker 和可安全重试 operation。
- 当前可执行的 repair/reset/rollback/cleanup 动作；diagnose 本身只读，不自动 mutation。

#### 6.5 生命周期与受控清理

- `tmp/` 只保存可安全重建的文件；成功结束时可以自动清理，失败或进程中断时由下一次 diagnose 标记候选。
- `work/` 保存 attempt 和失败诊断证据；默认不自动删除。
- `image-deck/`、`editable/` 和 `final/` 是正式阶段/交付证据，cleanup 默认不删除。
- run 根目录默认仅当前用户可访问；目录使用 `0700` 等价权限，包含用户内容、prompt、OCR 或中间页面的普通文件使用 `0600` 等价权限。
- `input/` 默认保留以支持恢复，不自动上传或跨 run 复用；用户可在 run 进入 `completed|failed|cancelled` 且无 active worker 后显式选择 `--scope input` 删除，删除后该 run 标记为不可重新 prepare。
- `cleanup --dry-run` 输出按类别、路径、大小、保留理由和 containment 校验组成的计划。
- `cleanup --apply` 只执行完全相同 fingerprint 的 dry-run 计划，active worker、未完成 run、symlink escape 或 revision 变化时拒绝。
- 删除使用显式路径和 no-follow containment；不接受宽泛 glob、工作区根目录或未解析环境变量。
- MVP 不提供全局自动 `gc`；跨 run 垃圾回收等真实磁盘压力出现后再设计。
- 清理完成后在保留的 `reports/cleanup-receipt.json` 写入脱敏 receipt，删除对象不可恢复时明确报告。

### 7. 三条产品 Workflow

#### 7.1 路由 A：内容生成图片式 PPT

```text
内容输入
→ 确认受众、目的、页数和约束
→ 确认大纲与必要素材
→ 确认完整逐页内容稿或明确跳过
→ 确认风格与图片后端
→ 生成并批准一页样张
→ 准备 slide jobs
→ 派发 slide workers
→ 记录结果并逐页 QA
→ 组装图片式 PPTX
→ 报告 image deliverable
→ 询问是否升级可编辑
```

图片版一旦通过自身验收，即成为独立有效交付物。

#### 7.2 路由 B：直接转可编辑 PPT

```text
图片/PDF/PPTX 输入
→ 确认直接重建可编辑版本
→ 按 route 做依赖和 OCR 能力检查
→ editable prepare
→ 单页本地模式或多页 worker 派发
→ record + page validation
→ editable finalize
→ deck validation
→ 报告 editable deliverable
```

不得先生成新的图片式设计，除非用户明确要求重新设计。

#### 7.3 路由 C：图片版升级可编辑

```text
已完成 image-deck run
→ 用户选择全部页面或指定页面
→ 冻结 selection 与源页面 hash
→ editable prepare selected pages
→ page workers 重建并验证
→ full: editable finalizer
→ selected: hybrid assembler
→ 验证页数、页序、notes 和每页 mode
→ 报告 editable 或 hybrid deliverable
```

升级失败时：

- 原 image deliverable 保持有效。
- 报告失败页面和可恢复的 editable 页面产物。
- 不把失败的 selected-page upgrade 改写成 hybrid 完成。

默认交付策略为 fail closed：只有全部选中页通过 editable validation 才交付 `hybrid`。如果部分页面成功，顶层 Skill 可以向用户提供一次显式降级选择；只有用户确认后才调用 `upgrade finalize --allow-partial`：

| 交付类型 | 条件 | 交付行为 |
| --- | --- | --- |
| `hybrid` | 全部选中页验证通过 | 选中页 editable，未选中页 image |
| `partial-hybrid` | 部分选中页失败且用户明确接受降级 | 成功页 editable，失败页和未选中页 image；附失败报告 |
| `image` | 用户不接受部分降级或全部升级失败 | 不生成新的最终 deck，继续交付原 image deck |

`partial-hybrid` 规则：

- 不得由 runtime 自动选择；用户确认记录需绑定 selection、成功/失败页集合和当前 hash。
- `delivery.json` 逐页标明目标 mode、实际 representation、producer、validation 和失败原因。
- 单页 editable 页面产物、manifest 和 validation 保留在 `editable/` 中供修复和重新 finalize；它们不是需要用户手工合并的正式交付。
- 失败页继续使用原 image 页面，不得用未通过验证的 editable 页面。
- 顶层报告必须明确“部分升级”，不能使用“指定页全部可编辑”等表述。

### 8. 配置与图片后端合同

#### 8.1 配置优先级

统一 facade 读取：

1. 当前命令显式的非敏感选项。
2. 已支持的环境变量。
3. `${LEO_PPT_HOME}/config.yaml`。
4. 默认值。

凭据只来自宿主管理的内置工具、provider adapter allowlist 中的环境变量引用或明确支持的操作系统 credential store reference；不复制到 run 目录。

配置合同：

- `config.yaml` 必须包含 `schema_version: 1`。
- `doctor --json` 输出每个非敏感配置项的最终值、来源和适用 route；secret 只输出引用类型和是否可解析。
- 未知安全敏感字段、无法理解的更高 schema version 和非法枚举 fail closed；未知普通 optional 字段给出 warning。
- 首版不建设通用迁移系统；破坏性配置变化提升 schema version，并提供显式 validate/migrate 命令后才允许读取旧配置。
- task option 只覆盖当前 run，不反写用户配置。

#### 8.2 backend contract

统一的是”选择合同”，不是强行合并两套实现：

```json
{
  "schema_version": 1,
  "backend_kind": "builtin-imagegen|openai-compatible|atlascloud",
  "provider": "...",
  "model": "...",
  "mode": "generate|edit",
  "credential_source": "host-managed|environment-reference|os-store-reference",
  "selection_source": "user-confirmed|fallback-policy",
  "capabilities": {
    "generate": true,
    "edit": true,
    "mask": false,
    "max_reference_images": 4,
    "execution_owner": "agent-host|runtime"
  }
}
```

##### 8.2.1 Backend 选择算法

当用户未显式确认 backend 时，顶层 Skill 按以下顺序形成 backend contract：

```yaml
backend_selection:
  policy: prefer_builtin_then_credential_available
  fallback_chain:
    - backend_kind: builtin-imagegen
      condition: live_agent_host_capability_confirmed AND capabilities.generate
      priority: 1
    - backend_kind: openai-compatible
      condition: credential_available AND endpoint_configured
      priority: 2
    - backend_kind: atlascloud
      condition: credential_available
      priority: 3
```

选择规则：

- 按 priority 升序检查，第一个满足 condition 的 backend 被选中。
- `live_agent_host_capability_confirmed` 只能来自当前会话的宿主能力检查；静态配置、历史成功或 CLI `doctor` 不能替代。
- `credential_available` 只表示凭据 reference 当前可解析，不表示 provider 已接受、未过期或具备目标模型权限。
- 用户显式确认的 backend 覆盖 fallback policy，记录为 `selection_source=user-confirmed`。
- 顶层 Skill 把选定合同写入当前 run 的受控输入，再通过 `run create --backend-contract` 交给 CLI；CLI 校验 schema、capability 和 credential reference，不自行改选 backend。
- 样张批准后，该 backend 冻结到 run.json，后续 worker 必须继承。
- `doctor --route <route>` 输出 runtime 可验证的依赖、配置和 credential-reference 状态；内置图片工具只报告 `host_check_required`，最终选择由顶层 Skill 报告。

##### 8.2.2 Credential 生命周期与过期处理

凭据来源优先级：

1. Agent 宿主管理的内置工具凭据；runtime 不读取或转存。
2. provider adapter 明确 allowlist 的环境变量引用。
3. provider adapter 明确支持的操作系统 credential store reference。

凭据安全规则：

- 不得写入 run 目录、Skill 安装目录或 `config.yaml`（只记录 reference）。
- 不得通过 CLI 参数传递（会出现在进程列表）。
- 不得在日志中明文记录（仅记录 “credential_status: available|expired|missing”）。
- Backend 调用时，Agent 宿主调用内置工具由宿主管理凭据；runtime 调用 API 从环境变量或 credential store 读取。
- runtime 不读取 `~/.codex/credentials`、其他宿主私有认证文件或未登记环境变量。
- Worker 不接收完整 Agent 环境；宿主内置工具继续使用宿主凭据，runtime subprocess 只继承 provider adapter allowlist 中当前任务必需的变量引用。

凭据过期处理：

| 阶段 | 检测方式 | 处理动作 |
| --- | --- | --- |
| doctor | reference/schema/config check | 只报告 available/missing/unresolvable，不声称凭据有效或过期 |
| 样张生成 | 首次 API 调用返回 401 | 返回 `credential_rejected`，中止 run |
| 样张生成 | 首次 API 调用返回 403 | 返回 `provider_permission_denied`，中止 run |
| worker 运行中 | API 调用返回 401/403 | 按上述原因标记该页面，不阻塞其他已派发页面 |
| 恢复 | 用户刷新凭据后 | `leo-ppt run retry <run> --from-failed-pages` |

规则：

- 凭据过期时不自动尝试其他 backend（避免意外切换生成方法）。
- 过期后的 retry 只重新执行失败页面，已完成页面不重复调用。
- API rate limit (429) 与凭据过期分开处理：rate limit 自动 exponential backoff，凭据过期需要用户介入。

内部 provider 扩展边界：

```python
class ProviderAdapter(Protocol):
    provider_id: str
    contract_version: int

    def describe_capabilities(self) -> BackendCapabilities: ...
    def validate_config(self, config: BackendConfig) -> ValidationResult: ...
    def validate_credential(self, credential: CredentialRef) -> CredentialStatus: ...
    def execute(self, job: ImageJob) -> ImageResult: ...
```

- 内置图片工具只能由 Agent 宿主调用。
- API/CLI fallback 由内嵌 runtime 调用。
- 样张批准后，image-deck worker 必须继承同一生成方法。
- editable 页面内的图片任务继续遵守其串行 backend 规则。
- adapter 不得为了统一接口自动换用另一 backend。
- provider adapter 先验证 capability，再接受任务；不根据 provider 名称或 URL 猜测能力。
- credential reference 与精确 endpoint origin 绑定，认证请求不得因 redirect 被发送到其他 origin。
- provider 通过代码拥有的静态 registry 绑定 `provider_id → ProviderAdapter`；新增 provider 必须随代码、能力声明、凭据边界和回归测试发布。
- 不提供会修改已安装 Skill/runtime 的动态 `register_backend.py`；用户配置只能选择当前 release 已注册的 provider 和非敏感参数。

#### 8.3 按路由检查

- `generate`：只检查图片生成、PPTX 组装和 image-deck 所需依赖。
- `editable`/`upgrade`：再检查输入转换、OCR、公式或页面重建能力。
- 可选能力缺失不得阻塞无关路径。
- “配置存在”与”真实 provider 当前可调用”分开报告。

#### 8.4 并发度与资源限制

Worker 并发度控制：

- 默认并发度：`min(cpu_count // 2, 4, page_count)`
- 配置覆盖：`config.yaml` 中 `max_concurrent_workers`（范围 1-16）
- 环境变量：`LEO_PPT_MAX_WORKERS` 覆盖配置文件
- 单页本地模式：固定串行（max_concurrent=1）

Backend API 限流策略：

- 自动检测 rate limit 响应（HTTP 429、provider 特定错误码）
- Exponential backoff：初始 1s，最大 64s，抖动 ±25%
- 重试上限：单个请求最多 3 次，超过后标记该页面 `backend_rate_limited`
- 记录到 `reports/timing.json`，包含 retry 次数和累计等待时间

资源使用限制：

| 资源类型 | 限制 | 超限行为 |
| --- | --- | --- |
| 单个 run 磁盘占用 | 10 GB（可配置） | 拒绝组装，返回 reason_code=disk_quota_exceeded |
| Worker 内存峰值 | 不限制（依赖系统） | 记录到 reports/resource_usage.json |
| 单页图片大小 | 25 MB | 警告，不阻止（可能影响 PPTX 打开速度） |
| 总 PPTX 大小 | 200 MB | 警告，不阻止 |

规则：

- 并发度同时约束活跃 worker 和该 run 的 backend API 调用；provider adapter 可以进一步降低并发，但不得扩大上限。
- MVP 不提供 pause/resume 命令；用户需要停止新派发时使用可恢复的宿主中断，明确终止整个 run 时使用 `run cancel`。

### 9. 上游源码集成与同步

#### 9.1 U0 前置 spike

正式实施前必须完成一次最小内嵌验证：

1. 从当前 owner 提供或项目可复核的来源解析两个上游的 repository URL、commit、tree hash、license 和导入范围；任一身份无法确认时 no-go，禁止按项目名猜测来源。
2. 从已确认 commit 的 Git tree 导出源码，禁止从 dirty worktree 复制。
3. 在临时干净目录中按建议 `_vendor/` 结构放置源码。
4. 只修改 import 和资源定位，证明两个 adapter 可 import。
5. 运行一个 image-deck fixture 和一个 editable fixture。
6. 构建并安装 Skill bundle 内 runtime，证明 prompts/references/package data 可定位。
7. 记录必须修改的文件、原因和对应回归测试。

U0 是本计划唯一允许立即启动的实施单元。只有 `docs/reviews/u0-report.md` 记录 `decision: go`，且上游身份、许可证、依赖、资源定位、最小 fixture、Office 无网络边界和 worker 执行边界全部达到通过标准后，U1–U5 才能启动。`decision: no-go` 时停止本计划并返回 `spec-plan` 修订 vendoring、package、输入支持或 worker 边界，不得在实现中临时扩建平台能力。

##### 9.1.1 U0 量化通过标准

| 指标类别 | 指标 | 通过标准 | 测量方法 |
| --- | --- | --- | --- |
| 源码修改量 | Vendor 代码变化率 | < 5% 行数变化 | `git diff --stat` 统计修改/总行数 |
| Adapter 代码量 | 新增 adapter 代码 | < 500 行/adapter | `cloc` 统计 adapter.py |
| 依赖冲突 | 无法解决的版本冲突 | 0 个 | `pip-compile` 成功且 `pip check` 通过 |
| 上游测试通过率 | 核心测试通过比例 | ≥ 95% | 运行标记为 `@core` 的上游测试 |
| 资源定位 | wheel/editable 都能定位资源 | 100% 成功 | 两种安装模式下运行 fixture |
| Import 隔离 | 顶层代码直接 import vendor | 0 次 | `grep -r "from.*_vendor" application/ cli.py` |
| 状态隔离 | 两个 adapter 独立运行 | 互不干扰 | 并发运行两个 fixture 不冲突 |
| 核心算法保留 | 页面生成/重建逻辑未改 | 输出一致 | golden file 对比或 hash 验证 |
| 来源身份 | URL/commit/tree/license/import set | 100% 可复核 | `upstreams.yaml` 与 clean export hash 对比 |
| Office 网络边界 | Office 转换/OCR 出站访问 | 0 次 | 受控 fixture 记录网络访问并 fail closed |
| Worker 边界 | 无 worker 时的多页行为 | 明确 blocked | host-capability fixture，不允许 runtime 模拟 Agent |

定性边界（任一触发则 U0 失败）：

- 需要重写 manifest 或 page_jobs 的状态模型结构。
- 需要在 adapter 中模拟上游 CLI 的子命令调度逻辑。
- 两个依赖集合要求不同的 Python major 版本。
- 必须移除上游的关键测试才能通过 fixture。
- wheel 安装后无法定位 prompts/references（resource 机制失效）。

U0 失败时不引入平台控制面；应先调整 vendoring/package 边界或寻求上游修改。

##### 9.1.2 U0 交付物

- `docs/reviews/u0-report.md`：量化指标实测值、定性边界检查结果、go/no-go 结论。
- `skills/leo-ppt-generator/upstreams.yaml`：初始版本，记录固定 commit 和 tree hash。
- `skills/leo-ppt-generator/patches/`：必要的最小 patch 文件。
- `tests/upstream/`：adapter 后仍能通过的上游核心测试清单。
- `tests/integration/u0_isolation.py`：验证 import 隔离和状态隔离的 fixture。

#### 9.2 溯源记录

`skills/leo-ppt-generator/upstreams.yaml` 至少记录：

- 仓库 URL、commit、license 和导入时间。
- 导入目录或文件集合及源 tree hash。
- 本地 patch 摘要和 patch 文件。
- 运行时保留的关键合同。
- 对应上游回归和本地聚焦测试。

不在主方案人工维护逐行 disposition 表。同步时由脚本或 Git diff 生成文件级差异供审查。

提供确定性同步入口：

```bash
python scripts/sync_upstreams.py --check
python scripts/sync_upstreams.py --update <upstream> --commit <sha>
```

- `--check` 验证源 tree hash、导入文件集合、本地 patch、vendor 目录、license/notices 和对应测试映射。
- `--update` 只在临时 staging 目录导出新 tree、应用已登记 patch、生成文件级 diff 并运行聚焦回归；验证通过前不覆盖正式 vendor。
- vendor 目录存在未登记修改时失败，不执行 blind rsync。
- 更新 commit、patch 或依赖 lock 任一项都产生新的 runtime identity。

#### 9.3 允许的局部修复

首版只修复直接影响三条主路径的问题：

- image-deck 缺页仍可能组装成功。
- provider 类型由域名子串错误推断。
- 并发写状态缺乏原子保护。
- editable finalize 未重新确认已记录产物的一致性。
- hybrid 页序、notes 或 page mode 声明错误。

每个修复必须先有 characterization 或失败 fixture，再有聚焦回归测试。

### 10. 输入信任与安全边界

MVP 默认处理用户明确提供的本地可信文件或由 Agent 已经取得的规范化正文。

- 不自建公开网页抓取器。
- 不把网页正文当作 Agent 指令。
- 不在 run 目录保存凭据。
- 用户正文、OCR、prompt、中间图片和 PPTX 都属于用户内容；只写入当前 run，禁止进入遥测、全局缓存、跨 run 去重或诊断 bundle，除非用户另行明确授权。
- `run create` 将输入复制到 `<run>/input/`，记录 hash、大小和规范化类型；拒绝 symlink escape、特殊设备、超出规模限制的输入和解析结果与声明类型不一致的文件。
- PPT/PPTX 只有在用户明确确认来源可信，且 preflight 未发现宏、嵌入对象、外部关系或远程模板时才进入 Office 解析路径。
- 来源未知或命中主动内容/外部关系的 Office 文件必须返回 `blocked/untrusted_office_input`；MVP 不提供“警告后继续”，只接受用户另行提供的 PDF 或逐页图片。
- Office 转换和 OCR 默认禁用网络访问；如果当前依赖无法在无网络条件下运行，U0 必须将该路径判定为 no-go 或缩小支持范围。
- 如果未来产品要公开处理任意不可信 Office 输入，再独立设计转换隔离和网络策略，不在本 MVP 中隐式承诺。

### 11. 失败与恢复语义

#### 11.1 失败报告要求

- 失败必须报告 route、stage、slide/page id、证据路径和可执行恢复动作。
- image deliverable 已通过时，后续 editable 失败不得删除或降级它。
- 不完整页面、validation failed 或 finalizer failed 不得报告成功。
- 重试使用两个上游已有 reset/record 机制；顶层不建设第二套重试状态机。
- 同一条件下的重复失败必须先改变输入、配置、backend 或实现，再重新派发。
- 用户取消升级不影响已经完成的图片版交付。
- runtime 安装或升级失败时继续使用旧 `current`；不得留下指向半安装环境的入口。
- run 的 runtime identity 不可用或不兼容时明确 blocked，不自动用最新 runtime 猜测恢复。
- `run status` 在报告恢复动作前执行 revision、领域状态、正式产物和 hash reconciliation。

#### 11.2 错误分类与恢复动作

所有失败必须返回结构化 `reason_code`，对应明确的恢复路径或阻塞原因：

| 错误类别 | Reason Code | 可恢复 | 恢复动作 | CLI 命令示例 |
| --- | --- | --- | --- | --- |
| 配置错误 | `config_invalid` | ✅ | 修正配置后 retry | 修正 config.yaml → `retry <run>` |
| 配置版本不兼容 | `config_schema_too_new` | ✅ | 升级 runtime 或降级配置 | `ensure` 新版本 |
| 凭据缺失 | `credential_missing` | ✅ | 配置凭据后 retry | 设置环境变量 → `retry <run>` |
| 凭据过期 | `credential_expired` | ✅ | 刷新凭据后 retry-from-failed | 刷新 token → `retry <run> --from-failed-pages` |
| 凭据被拒绝 | `credential_rejected` | ✅ | 更新或重新授权凭据后 retry-from-failed | 更新凭据 → `retry <run> --from-failed-pages` |
| Provider 权限不足 | `provider_permission_denied` | ⚠️ | 修正账号/模型权限或由用户重新选择 backend | `doctor` → 用户确认 backend → 新 run |
| Runtime 不兼容 | `runtime_incompatible` | ⚠️ | 安装兼容 runtime 或放弃 run | `ensure` 匹配版本或 `run create` 新 run |
| 输入格式错误 | `input_invalid` | ❌ | 提供有效输入并创建新 run | 转换输入 → `run create` |
| 不可信 Office 输入 | `untrusted_office_input` | ✅ | 提供 PDF/逐页图片或可信且通过 preflight 的 Office 文件 | 转换输入 → `run create` |
| 输入规模超限 | `input_too_large` | ✅ | 缩小页数或拆分输入 | 拆分输入 → `run create` |
| 输入文件缺失 | `input_file_missing` | ⚠️ | 恢复文件后 retry | 恢复文件 → `retry <run>` |
| Backend 能力不足 | `backend_capability_missing` | ⚠️ | 样张批准前可重新选择；冻结后必须新建 run 并重新确认样张 | 用户确认 backend → `run create` |
| Backend 不可用 | `backend_unavailable` | ✅ | 冻结后只允许等待同一 backend 恢复；切换 backend 必须新建 run | 等待 → `retry`，或用户确认后 `run create` |
| Backend rate limit | `backend_rate_limited` | ✅ | 自动 backoff，或稍后 retry | 等待 → `retry <run> --from-failed-pages` |
| Backend 超时 | `backend_timeout` | ✅ | 自动重试耗尽后从失败页面恢复 | 等待 → `retry <run> --from-failed-pages` |
| Worker 能力不可用 | `worker_capability_unavailable` | ⚠️ | 切换到具备所需 worker 能力的宿主 | 重新打开 run → `run status` |
| 页面验证失败 | `page_validation_failed` | ⚠️ | reset 失败页面并重新派发 | `editable reset <run> --page <id>` → dispatch |
| 状态不一致 | `state_mismatch` | ⚠️ | diagnose 分析，可能需要 reconciliation | `run diagnose <run>` → 按建议操作 |
| 状态文件损坏 | `state_corrupted` | ❌ | 无法自动恢复 | 从备份恢复或放弃 run |
| Worker 超时 | `worker_timeout` | ✅ | retry 该页面 | `editable reset <run> --page <id>` → dispatch |
| Worker 崩溃 | `worker_crashed` | ✅ | retry 该页面 | `editable reset <run> --page <id>` → dispatch |
| Run 被中断 | `run_interrupted` | ✅ | reconciliation 后继续 pending/failed 页面 | `run diagnose <run>` → `run retry <run>` |
| 组装前置条件失败 | `assembly_precondition_failed` | ⚠️ | 检查上游结果，可能需要重新 prepare | `run diagnose <run>` → 按建议操作 |
| 磁盘空间不足 | `disk_quota_exceeded` | ✅ | 清理空间后 retry | `cleanup` → `retry <run>` |
| 依赖缺失 | `dependency_missing` | ✅ | 安装依赖后 retry | 安装依赖 → `doctor` → `retry <run>` |
| 未知错误 | `unknown_error` | ❌ | 收集证据并报告 | `run diagnose <run>` 收集日志 |

图标说明：
- ✅ 可恢复：用户操作后可安全 retry
- ⚠️ 部分可恢复：取决于具体情况
- ❌ 不可恢复：需要放弃 run 或手动干预

规则：

- 每个 reason_code 必须文档化并在 `skills/leo-ppt-generator/references/reason-codes.md` 中维护。
- CLI 返回 reason_code 时必须附带 human-readable message 和 suggested_actions。
- 多个错误同时发生时，返回最具体的 reason_code（如 `credential_expired` 优先于 `backend_unavailable`）。
- `unknown_error` 只在确实无法分类时使用，并记录详细上下文到 logs。

#### 11.3 用户中断与取消

中断类型与处理：

| 中断类型 | 触发方式 | 行为 | 恢复路径 |
| --- | --- | --- | --- |
| 用户主动取消 | Ctrl+C、Agent stop | Grace period 5 min，已派发 worker 允许完成 | `run status` 查看状态 → `retry` 或 `cleanup` |
| Agent 超时 | 宿主策略 | 同上 | 同上 |
| 系统崩溃 | 进程被杀、机器重启 | 无 grace period，状态保持最后 barrier | `run diagnose` → reconciliation |
| 用户明确取消 | `run cancel` | 立即停止派发，grace period 等待已运行 worker | 不可恢复，只能 cleanup |

中断后状态：

- **Image-deck worker 派发中**：已派发 worker 继续运行，未派发标记 `cancelled`
- **Editable worker 运行中**：grace period 内允许完成，超时标记 `timeout`
- **组装中**：中断，保留已完成阶段产物
- **Finalize 中**：不响应协作式取消；进程仍可能被系统终止，恢复时以最后 barrier 和候选产物 hash 做 reconciliation

恢复检查：

```bash
leo-ppt run status <run>
# 输出：
# - active workers: 2 (grace period: 3m remaining)
# - timed out workers: page_5 (可 reset)
# - pending pages: page_8, page_9 (run 未终止时可 retry)
```

取消命令（明确不可恢复）：

```bash
leo-ppt run cancel <run> --wait-workers
# 行为：
# - 停止派发新 worker
# - 等待运行中 worker 完成（最多 grace period）
# - 标记 pending 为 cancelled
# - 保留已完成产物
# - run 进入 terminal 状态 cancelled
```

规则：

- Grace period 期间，CLI 定期检查 worker 状态并更新 page_jobs。
- Grace period 过期后，强制标记为 timeout，不等待结果。
- 中断不删除任何已完成的产物或状态文件。
- Ctrl+C 或 Agent stop 只把 run 留在可恢复的 interrupted checkpoint；未派发页面保持 pending，不写成 terminal `cancelled`。
- `run cancel` 后 run 不可 retry，只能 cleanup 或保留供调试。

## Implementation Units

| U-ID | 标题 | 关键文件 | 依赖 |
| --- | --- | --- | --- |
| U0 | 验证可内嵌性与发行边界 | `upstreams.yaml`、`vendor-lock.json`、`tests/upstream/` | 无 |
| U1 | 建立顶层 Skill 与受管 runtime | `SKILL.md`、`runtime_manager.py`、`pyproject.toml` | U0 |
| U2 | 导入两个领域能力并建立 adapter | `_vendor/`、两个 adapter、backend contract | U0、U1 |
| U3 | 实现顶层 Workflow 和跨阶段索引 | routes、run index、CLI、lifecycle | U1、U2 |
| U4 | 实现 full editable 与 hybrid 交付 | hybrid assembler、PageArtifact、delivery schema | U2、U3 |
| U5 | 聚焦验证与基础发布 | e2e、Skill eval、兼容与安全测试 | U1–U4 |
| U6 | 修复安装与 bundle 自包含性 | Skill、prompts、references、发布测试 | U1、U2、U5 |
| U7 | 完成初始化、配置与 readiness 体验 | runtime manager、runtime config、doctor | U3、U6 |
| U8 | 建立内容、视觉与可编辑质量门 | workflows、worker prompts、质量合同 | U2–U4、U6 |
| U9 | 收紧稳定性、恢复与可观测闭环 | lifecycle、observability、run index | U3、U4 |
| U10 | 建立逐能力 proof 和 Skill 行为评测 | capability ledger、upstream tests、skill evals | U2–U6 |
| U11 | 完成开源发布包与用户文档 | LICENSE、README、教程、测试方案、Wheel | U6–U10 |
| U12 | 20 轮复核与最终交付门 | 全套测试、clean install、最终验证报告 | U6–U11 |

### U0. 验证可内嵌性与发行边界

**目标：** 用最小代码证明两个固定上游可以随一个 Skill bundle 安装和运行。

**覆盖：** R6、R7、R8。

**文件：** `docs/reviews/u0-report.md`、`skills/leo-ppt-generator/upstreams.yaml`、`skills/leo-ppt-generator/vendor-lock.json`、`skills/leo-ppt-generator/patches/`、`tests/upstream/`、`tests/integration/u0_isolation.py`。

**依赖：** 无；这是唯一允许立即启动的单元。

**工作：**

- 固定 commit、license 和 clean-tree export。
- 建立临时 `_vendor/` 结构和两个 import adapter。
- 验证依赖解析、lock、支持的 Python/平台、资源定位、fixture 和 runtime 安装。
- 验证最小 `CapabilityAdapter` 与 `PageArtifact` 能隐藏 vendor 内部路径和状态。
- 对两个上游做并发 record、进程中断和文件写入持久化 characterization，明确 U1/U2 必须修复的边界。
- 输出必要 patch 清单和 go/no-go 结论。

**完成证据：** 干净环境仅使用当前 Skill bundle 和发布 lock，即可 import 两个 adapter、运行两个最小 fixture，并证明顶层代码没有直接 import `_vendor`。

**测试场景：** 上游身份缺失时 no-go；clean export 能复现 tree hash；两个最小 fixture 独立运行；Office/OCR 无网络 fixture 不出站；无 worker 的多页路径明确 blocked。

### U1. 建立顶层 Skill 与受管 runtime

**目标：** 用户只安装并发现 `leo-ppt-generator`。

**覆盖：** R1、R6、R7。

**文件：** `skills/leo-ppt-generator/SKILL.md`、`skills/leo-ppt-generator/agents/openai.yaml`、`skills/leo-ppt-generator/scripts/runtime_manager.py`、`skills/leo-ppt-generator/runtime/pyproject.toml`、`skills/leo-ppt-generator/runtime/constraints/`。

**依赖：** U0 `decision: go`。

**工作：**

- 创建精简 `SKILL.md`、`agents/openai.yaml`、references 和 prompts。
- 创建 Skill 内 `runtime/pyproject.toml` 与 `runtime_manager.py`。
- 实现不可变 runtime identity、安装锁、ensure、doctor、原子 current 切换、rollback 和准确 CLI 路径解析。
- 实现 run 固定 runtime identity、旧版本保留和 runtime incompatibility 行为。
- 实现 runtime current pointer 的 barrier 写、半安装清理和 operation id 幂等 ensure。
- 确保两个旧 `SKILL.md` 不可被发现。

**完成证据：** 新环境安装当前 Skill 后，Skill 可发现，旧 Skill/CLI 不存在；并发 ensure、安装中断、失败不切换、成功升级和 rollback 测试通过。

**测试场景：** 并发 ensure 只有一个安装者；依赖安装失败保持旧 current；中断留下的半安装环境不会被选中；活动 run 引用的旧 runtime 不能删除。

### U2. 导入两个领域能力并建立 adapter

**目标：** 在保留领域合同的前提下提供稳定 Python/CLI 边界。

**覆盖：** R2、R3、R6、R7、R8。

**文件：** `skills/leo-ppt-generator/runtime/src/leo_ppt_generator/image_deck/adapter.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/editable/adapter.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/config/backend_contract.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/_vendor/`、`tests/upstream/`、`tests/unit/test_adapters.py`。

**依赖：** U0 `decision: go`、U1 runtime 和 package 边界。

**工作：**

- 按 U0 结论导入源码、prompt、reference 和测试。
- 实现 versioned image-deck/editable adapter 与统一 `PageArtifact` 映射。
- 实现 versioned config、静态 ProviderAdapter registry、backend capability contract 和来源报告。
- 保留各自状态文件与验证 owner。
- 完成已识别的局部正确性修复，包括 editable 状态文件的锁、原子写和并发 record 防丢更新。
- 为 vendor 正式状态、manifest、asset 和 notes 实现 durable-file/barrier checkpoint；崩溃恢复不得重复付费 provider 调用。
- 增加 import-boundary 测试，禁止 adapter 外部直接引用 vendor。

**完成证据：** 两套上游回归通过；两个 adapter 在统一 run 根目录下分别完成 fixture；并发状态写、未知 contract version 和 vendor 字段变化 fixture 均 fail closed。

**测试场景：** adapter 外部 import vendor 被拦截；未知 contract version fail closed；并发 record 不丢更新；provider 响应丢失不重复付费调用；敏感字段不进入日志。

### U3. 实现顶层 Workflow 和跨阶段索引

**目标：** 一个 Skill 能准确路由和推进三条路径。

**覆盖：** R1、R2、R3、R5、R6、R8。

**文件：** `skills/leo-ppt-generator/SKILL.md`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/application/routes.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/application/run_index.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/cli.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/lifecycle.py`、`tests/unit/test_routes.py`、`tests/integration/test_run_lifecycle.py`、`tests/skill-evals/`。

**依赖：** U1、U2。

**工作：**

- 实现输入分类、route 选择和 `run.json`。
- 实现四条 code-owned route definition；不实现通用 DAG parser、cycle detector 或动态 capability registry。
- 实现 canonical route 枚举、versioned CLI 机器协议、稳定 `next_action.kind` 和 reason code。
- 实现 `run.json` schema/revision、file lock、expected revision、原子写和 reconciliation。
- 实现命令 idempotency key、operation status、safe-to-retry 和 state hash 冲突合同。
- 实现 `events.ndjson`、分离 worker logs、`run diagnose`、分类 tmp/work 生命周期和 scoped cleanup。
- 合并上游确认门和 worker 派发合同。
- 实现 image-deck → editable 的页面、notes 和 backend handoff。

**完成证据：** Skill 到 CLI 到正确 adapter 的路由可通过行为 eval 验证；修改 CLI 展示文案不改变控制流；revision/idempotency 冲突不丢更新；crash 后 diagnose 可给出唯一安全恢复动作；cleanup 不越过 dry-run fingerprint 和 containment。

**测试场景：** 四条 route 分别到达正确 adapter/assembler；未知 route/step fail closed；无授权或无 host worker capability 的多页请求 blocked；Ctrl+C 可恢复而 `run cancel` 不可 retry；cleanup fingerprint 或 revision 漂移时零删除。

### U4. 实现 full editable 与 hybrid 交付

**目标：** 整套和指定页升级都具有准确的页面与交付语义。

**覆盖：** R4、R5、R7。

**文件：** `skills/leo-ppt-generator/runtime/src/leo_ppt_generator/hybrid/assembler.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas/page_artifact.schema.json`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas/delivery.schema.json`、`tests/unit/test_hybrid_assembler.py`、`tests/integration/test_upgrade_routes.py`。

**依赖：** U2、U3。

**工作：**

- full upgrade 复用 editable finalizer。
- selected upgrade 实现 hybrid assembler。
- hybrid 只消费统一 `PageArtifact`，输出逐页 `image|editable` delivery manifest。
- 默认全部选中页通过才交付 hybrid；部分成功只在用户确认后生成 `partial-hybrid` 和 failure report。
- 验证页数、页序、尺寸、notes、source hash 和最终 PPTX。

**完成证据：** 首、中、尾页选择 fixture 均保持页序和 notes；未授权时任何失败页阻止 hybrid 完成；授权 partial 时失败页保持 image 且准确报告。

**测试场景：** 页数、页序、尺寸、notes、source hash、validation ref 各自失败；全部通过生成 hybrid；部分失败未经确认拒绝，确认后生成准确的 partial-hybrid。

### U5. 聚焦验证与发布

**目标：** 证明统一产品真实可用，而不是只证明 package 能 import。

**覆盖：** R1–R8。

**文件：** `tests/e2e/`、`tests/skill-evals/`、`tests/integration/test_runtime_manager.py`、`tests/boundary/`、`skills/leo-ppt-generator/LICENSE.codex-ppt`、`skills/leo-ppt-generator/LICENSE.image-to-editable-ppt`、`CHANGELOG.md`。

**依赖：** U1–U4 全部完成。

**工作：**

- 运行上游测试、局部修复测试和四条 route 的 e2e fixture。
- 运行顶层 Skill 行为 eval。
- 运行 runtime/config/run/protocol 的跨版本兼容、恢复和回滚矩阵。
- 运行 `sync_upstreams.py --check`、dependency lock 和 bundle inventory 验证。
- 运行命令幂等重放、关键 checkpoint crash point、diagnose 和 cleanup 安全矩阵。
- 使用真实图片 provider 做最小 image-deck smoke。
- 使用真实 OCR/Office viewer 分别记录现场能力，不与离线 fixture 混报。
- 校验 Skill bundle、受管 runtime、许可证和已知限制。

**完成证据：** 只有当前 Skill 被安装时，三条真实路径均能产生准确类型的可验证 PPTX；旧 run 恢复、失败升级回滚和同 identity 重复安装均有确定结果。

**测试场景：** 干净安装完成四条 route；真实 provider、OCR、Office viewer 和 PowerPoint 桌面证据分层报告；旧 runtime 恢复与不兼容阻断；安装包 inventory 只有一个可发现 Skill。

### U6. 修复安装与 bundle 自包含性

**目标：** 从用户安装后的真实目录启动 Skill，不依赖仓库根目录、当前工作目录或缺失资源。

**覆盖：** R1、R9、R10、R16、R17。

**文件：** `skills/leo-ppt-generator/SKILL.md`、`skills/leo-ppt-generator/agents/openai.yaml`、`skills/leo-ppt-generator/prompts/slide-worker.md`、`skills/leo-ppt-generator/prompts/page-worker.md`、`skills/leo-ppt-generator/references/`、`tests/release/test_release_docs.py`、`tests/integration/test_runtime_manager.py`。

**依赖：** U1、U2、U5。

**工作：** 统一 Skill 根目录解析；修复或移除缺失 `cli-helper`、不存在的图片脚本和仓库外引用；把 Skill bundle README 的唯一用户内容归并到仓库 README/教程后移除该 README，避免触发时上下文与双重说明；增加全部 Markdown 链接、prompt placeholder 和命令目标的静态解析测试。

**完成证据：** 把 Skill 目录复制到隔离用户级发现目录后，从任意 cwd 执行启动流程；bundle 内所有相对引用存在，只有一个 `SKILL.md`，且不存在 `third_party/`、旧 Skill 入口或旧 CLI 依赖。

**测试场景：** 任意 cwd；空 `CODEX_HOME`；`$HOME/.agents/skills`；安装器默认目录；缺失 reference；错误旧 CLI 命中；同名目录冲突；Skill 更新后重新发现。

### U7. 完成初始化、配置与 readiness 体验

**目标：** 让首次用户明确知道当前能运行什么、缺什么以及如何恢复。

**覆盖：** R9、R11、R15、R19。

**文件：** `skills/leo-ppt-generator/scripts/runtime_manager.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/config/runtime_config.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/cli.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/lifecycle.py`、`docs/guides/user-guide.md`、`tests/integration/test_runtime_manager.py`、`tests/unit/test_runtime_config.py`。

**依赖：** U3、U6。

**工作：** 对齐 runtime manager 与 runtime config 的 home 解析；明确 `ensure → doctor → print-cli` 的输入、输出和恢复动作；四 route doctor 分开报告本地机制、配置来源、credential reference、worker、provider、Office 应用和人工验收状态；配置错误不得阻断只读诊断对错误本身的报告。

**完成证据：** 新用户可按 doctor 输出修复缺失项；重复 ensure 为 reused；配置非法、schema 过新、凭据缺失和应用缺失均有稳定 reason code，且不泄露值。

**测试场景：** 默认/显式 home、配置覆盖、环境变量覆盖、非法敏感字段、坏 YAML、四 route、无凭据、无 PowerPoint、配置损坏下 diagnose。

### U8. 建立内容、视觉与可编辑质量门

**目标：** 把“生成了 PPTX”提升为内容可信、叙事清楚、视觉可读、交付类型准确。

**覆盖：** R2–R4、R12–R14、R20。

**文件：** `skills/leo-ppt-generator/references/image-deck-workflow.md`、`skills/leo-ppt-generator/references/editable-workflow.md`、`skills/leo-ppt-generator/references/style-library.md`、`skills/leo-ppt-generator/prompts/slide-worker.md`、`skills/leo-ppt-generator/prompts/page-worker.md`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas/delivery-v1.schema.json`、`tests/skill-evals/`、`tests/e2e/`。

**依赖：** U2–U4、U6。

**工作：** 增加受众/场景/时长/事实/叙事内容合同；定义页面角色和样张继承；将文字准确性、可读性、遮挡、截断、required asset、图表真值、风格一致性、对象级可编辑性和禁止整页栅格分成非补偿式检查；最终图片变化后必须重新组装、渲染和验证 PPTX。

**完成证据：** 行为 eval 证明确认门顺序和失败阻断；离线 fixture 证明结构、文字、notes、页序与交付类型；真实视觉和桌面检查只在实际执行后升级 claim。

**测试场景：** 长标题、中文字体、低对比、文字溢出、required asset 丢失、图表单位不一致、样张后切 backend、整页栅格伪装、部分页面失败、最终图片替换后未重验。

### U9. 收紧稳定性、恢复与可观测闭环

**目标：** 任意失败都能被定位、保留并给出唯一安全动作。

**覆盖：** R5、R8、R15、R19、R20。

**文件：** `skills/leo-ppt-generator/runtime/src/leo_ppt_generator/lifecycle.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/observability.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/application/run_index.py`、`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/schemas/run.schema.json`、`tests/integration/test_run_lifecycle.py`、`tests/integration/test_stable_workflow_commands.py`、`tests/boundary/`。

**依赖：** U3、U4。

**工作：** 检查 diagnose 在 hash mismatch、配置损坏和缺失 artifact 时仍能返回只读证据；确保所有稳定 mutation 返回 operation id、idempotency status、safe-to-retry 和 state hash；补齐 page/backend timing 与 redaction；验证 cleanup 不破坏恢复所需产物。

**完成证据：** 并发、crash、响应丢失、取消、清理和损坏状态测试均能得到确定结果；日志、timing、validation 和 failure report 互相引用同一 run identity。

**测试场景：** reconcile mismatch、损坏 timing、部分日志写入、active worker cleanup、输入已清理后 prepare、重放与 fingerprint 冲突、provider 调用后响应丢失。

### U10. 建立逐能力 proof 和 Skill 行为评测

**目标：** 对两个上游和顶层 Skill 的全部登记能力逐项证明，不做抽样。

**覆盖：** R6、R7、R18。

**文件：** `skills/leo-ppt-generator/upstream-capabilities.yaml`、`tests/upstream/test_feature_inventory.py`、`tests/upstream/core-tests.yaml`、`tests/skill-evals/cases.yaml`、`tests/skill-evals/test_skill_contract.py`、`docs/audits/upstream-feature-integration-audit-2026-08-21.md`。

**依赖：** U2–U6。

**工作：** 为每条 capability 增加具体 `proof_case`；用 pytest collection 或 AST 验证锚点存在并实际进入测试执行；分开结构合同、行为质量、runtime 成本和现场结果；增加安装、路由、确认、恢复和交付的正向/反向触发 eval。

**完成证据：** 账本每一行都有 owner、来源、集成路径和可执行 proof；固定上游 commit、逐文件 hash、exact assets 和 patch apply check 在最终树重新通过。

**测试场景：** 缺 proof case、拼错测试名、测试未收集、重复能力 id、上游 hash 漂移、patch 不可应用、功能存在但顶层不可达、旧 Skill 被错误触发。

### U11. 完成开源发布包与用户文档

**目标：** 形成可安装、可理解、可验证、许可证清楚的 Skill 发布候选。

**覆盖：** R9–R11、R16、R17、R20。

**文件：** `LICENSE`、`README.md`、`docs/guides/user-guide.md`、`docs/guides/testing.md`、`docs/guides/compatibility.md`、`docs/guides/limitations.md`、`skills/leo-ppt-generator/LICENSE`、`skills/leo-ppt-generator/runtime/pyproject.toml`、`tests/release/test_release_docs.py`。

**依赖：** U6–U10。

**工作：** 校准官方与安装器两条安装说明；补齐升级、卸载、配置、四 route、恢复、验收与隐私说明；保持 README 不出现用户排除的内部报告导航；构建 Wheel 并核对 MIT metadata、schema、vendor、缓存和旧入口 inventory。

**完成证据：** 根许可证与 Skill 许可证一致；项目 README 与教程链接有效；Wheel 可在隔离环境安装；release docs tests 和 Skill quick validation 通过。

**测试场景：** README 禁止短语、许可证不一致、broken link、Wheel 缺新模块、Wheel 含 pycache/旧 CLI/`third_party/`、远端 ref 与本地版本混报。

### U12. 20 轮复核与最终交付门

**目标：** 按 20 个角色闭环最终树，并只在所有自动门关闭后交付。

**覆盖：** R1–R20。

**文件：** `docs/reviews/optimization-rounds-2026-08-21.md`、`docs/guides/testing.md`、`docs/reviews/verification-report-2026-08-21.md`、`tests/`、最终 Skill bundle 与 Wheel inventory。

**依赖：** U6–U11。

**工作：** 逐轮记录证据、冲突、决策、改动或不改理由；运行简化审查和完整代码审查；修复 findings 后重跑受影响测试与全套回归；执行最终 clean install、四 route doctor、离线 smoke、Wheel inventory、上游全量 proof、文档与许可证校验；清理 build/cache/orphan；生成最终工作树 fingerprint。

**完成证据：** 20 轮每轮有唯一结论和 proof；最终测试、Wheel、安装和验证报告绑定同一工作树；`third_party/`、`__pycache__`、`.pyc`、旧 build 和未登记临时产物不存在。

**测试场景：** 中间树测试结果被误用于最终树、review finding 未复验、安装后断链、四 route 只抽测部分、field evidence 缺失却宣称完整、清理破坏发布包。

## Verification Contract

### 13.0 证据权威与退出门

- Product Contract confirmation：`confirmed`，用户在 2026-08-21 明确确认以“最终形成一个高质量 Skill”为目标，并接受单一 Skill、20 轮非形式化角色审视、真实证据分层和不建设通用平台的范围。
- Largest unproven risk：最终发布包能否在隔离安装目录和任意 cwd 中自包含运行，并把内容、视觉、结构、可编辑和现场质量门落实为真实证据而非文档声明。
- Source binding：所有结果必须绑定最终 git revision、runtime identity、两个 upstream tree hash、patch hash 和 dependency lock hash；仅有命令退出码不构成 source-bound 证据。
- Required-proof reconciliation：U12 结束时逐项对照下表；缺失 required proof、只存在计划文本或只有离线 fixture 时，不得声明完整交付已验证。

| Proof intent | 状态 | 权威证据 | Claim ceiling |
| --- | --- | --- | --- |
| U0 来源、依赖和边界可行性 | required | `docs/reviews/u0-report.md` + clean export/fixture receipts | 只决定 go/no-go，不证明三条产品路径完成 |
| 安装与 bundle 自包含 | required | 隔离 Skill 安装、任意 cwd、引用解析和四 route doctor receipts | 证明当前平台安装机制，不证明所有宿主平台 |
| 四条 route 机制正确 | required | source-bound unit/integration/e2e results | 证明受控输入机制，不证明所有视觉质量 |
| 两个上游逐项能力 | required | 每条 capability 的可执行 `proof_case` + 最终 collection result | 证明登记能力可达，不证明外部 provider 现场效果 |
| 内容与叙事质量 | required | 受众/目标/事实/大纲/逐页稿确认和行为 eval | 证明流程门，不自动证明具体演讲效果 |
| 视觉与可编辑质量 | required | 渲染检查、结构验证、对象检查和准确 delivery manifest | 自动检查不替代人工审美与桌面验收 |
| 发布包与开源文档 | required | Wheel inventory、MIT parity、Skill validation、README/tutorial link tests | 证明发布候选完整，不证明远端仓库已发布 |
| 真实图片 provider | required | 当次 provider smoke receipt | 只证明当次模型、网络和凭据路径 |
| OCR 与 Office viewer | required | 分开的现场 receipt；Office 路径需无网络证据 | 不互相替代，也不证明任意不可信 Office 安全 |
| PowerPoint 桌面打开与页面检查 | required | 最终 PPTX 的桌面验收记录 | 证明该 fixture，不证明所有客户端兼容 |
| 人工视觉等价 | deferred | Owner 验收；触发条件为发布候选 PPTX | 未完成时只能声明结构和交付类型正确 |

### 13.1 上游回归

- editable 已有测试在导入后继续通过。
- codex prompt 准备、backend 选择、结果记录、缺页拒绝和 PPTX 组装有 fixture/smoke。
- import/path/resource 修改不改变关键输出合同。
- 每个本地 patch 有对应聚焦回归。

### 13.2 顶层 Skill 行为 eval

至少包含：

1. 内容输入：先确认内容和样张，走 image-deck，不提前触发 editable。
2. 视觉输入并要求可编辑：直接走 editable，不重新设计页面。
3. image-deck 完成后指定页升级：只处理选中页，最终声明 hybrid。
4. editable 失败：保留 image deliverable，不误报升级成功。
5. 无旧 Skill/CLI：不得要求用户安装或调用旧入口。
6. Skill frontmatter description 能触发内容生成、视觉转可编辑、全量升级和指定页升级，并通过 `quick_validate.py`。
7. reference 按 route 渐进加载；image-only 任务不读取 editable 页面规则，direct-editable 不读取内容生成细节。
8. 部分页面升级失败时默认不交付 partial；只有用户明确接受后才生成并准确声明 `partial-hybrid`。

### 13.3 端到端验收

必须完成：

- Markdown/详细内容稿 → 图片式 PPTX。
- 图片或 PDF → 全可编辑 PPTX。
- 图片式 PPTX 的指定页面 → hybrid PPTX。
- 指定页部分失败 → 默认保留 image；显式接受降级 → partial-hybrid PPTX + failure report。

每条路径验证：

- route 和确认点正确。
- worker 产物由真实 worker 产生；恰好一页时允许当前 Agent 按同一 worker contract 执行。
- 页数、页序、notes 和最终 PPTX 可打开。
- 结构验证通过且交付类型声明准确。
- 最终证据可追溯到固定上游版本和当前 runtime identity。

### 13.4 稳定性与兼容矩阵

至少验证：

- 同一 identity 重复 `ensure` 不重建、不改变当前环境。
- 两个并发 `ensure` 只有一个安装者，另一个等待后复用结果。
- 安装在创建环境、安装依赖、doctor 和 current 切换前后各失败一次；旧 current 始终可用。
- v1 创建未完成 run，安装 v2 后仍由 v1 runtime 恢复；删除 v1 时因活动引用被拒绝。
- v2 声明兼容旧 run 时，必须通过固定旧 run fixture；不兼容时返回稳定 reason code。
- `run.json` expected revision 冲突、进程中断和可恢复索引缺失；无丢更新且可由领域事实 reconciliation。
- 四条有限 route 只能按固定步骤推进；未知 route、未知 step、未知 capability、缺失 step output 和运行时注入任意 step 均 fail closed。
- 各 mutation 在成功响应丢失后用同一 idempotency key 重放；相同 fingerprint 返回 replay，不同 fingerprint 返回 conflict。
- 在 temp write、file fsync、atomic replace、directory fsync 和状态提交前后模拟 crash；恢复后不误报完成、不重复调用付费 provider。
- config schema 过新、未知普通字段、未知敏感字段和来源冲突。
- backend 缺少 generate/edit/mask/reference capability 时在派发前拒绝不兼容 job。
- CLI 展示文案变化不改变 Skill 行为，未知机器协议版本 fail closed。
- vendor 目录未登记改动、patch 无法应用、upstream tree hash 漂移和 lock 漂移均由 `sync_upstreams.py --check` 拦截。
- diagnose 对缺失文件、hash mismatch、半安装 runtime、遗留 temp 和失败 operation 只报告证据与安全动作，不自动修改状态。
- cleanup dry-run/apply fingerprint、revision、active worker、symlink escape、no-follow containment 和保留 receipt 全部验证。
- partial-hybrid 未经用户确认拒绝；确认后失败页保持原 image，成功页使用已验证 editable PageArtifact。

### 13.5 测试覆盖率要求

单元测试覆盖率：

| 模块 | 目标行覆盖率 | 关键要求 |
| --- | --- | --- |
| `image_deck/adapter.py` | ≥ 80% | 所有 public 方法至少 1 个正向 + 1 个异常场景 |
| `editable/adapter.py` | ≥ 80% | 同上 |
| `hybrid/assembler.py` | ≥ 85% | 所有前置条件验证必须覆盖 |
| `application/run_index.py` | ≥ 90% | revision 冲突、reconciliation、锁竞争全覆盖 |
| `application/routes.py` | ≥ 85% | 四条 route 的固定步骤、输入和终态 |
| `config/backend_contract.py` | ≥ 75% | 各 backend 选择分支和 credential 验证 |
| `lifecycle.py` | ≥ 80% | cleanup、checkpoint、idempotency 核心路径 |

不要求覆盖：

- Vendor 内部代码（由上游测试负责）
- CLI 展示文案生成函数
- 日志格式化代码
- 已废弃但保留的兼容代码

集成测试覆盖矩阵：

- **Route × Backend 组合**：每种 route（4 种）× 至少 2 种 backend = 8 个 fixture
- **Route × Host capability**：多页任务覆盖 worker available/unavailable；单页覆盖 current-agent allowed/blocked
- **状态转换**：所有有效 stage 转换至少测试 1 次（通过 stage 图枚举）
- **错误路径**：每个 reason_code 至少 1 个触发测试

边界测试（必须覆盖）：

| 测试类别 | 最小场景数 | 示例 |
| --- | --- | --- |
| 并发写 run.json | 3 | 两 worker 同时 record、revision 冲突、reconciliation |
| 并发写 vendor 状态 | 3 | 两 worker 同时更新 page_jobs、expected_revision 冲突 |
| Crash 注入 | 8 | 在 temp write、file fsync、atomic replace、directory fsync、状态提交前后各 crash 一次 |
| Idempotency 重放 | 6 | 成功响应丢失、网络超时、相同 fingerprint、不同 fingerprint |
| Version 不兼容 | 4 | config schema 过新、protocol version 过新、runtime incompatible、vendor contract 过新 |
| Hybrid 前置条件 | 7 | 表格中 7 个前置条件各失败一次 |

端到端验收覆盖率：

- **四条 route**：必须全部通过（generate、direct-editable、upgrade-full、upgrade-selected）
- **Partial-hybrid 路径**：包含默认拒绝和明确授权两种场景
- **失败保留**：editable 失败后 image deliverable 仍可访问
- **恢复路径**：credential 过期 → 刷新 → retry-from-failed 完整流程

覆盖率验证：

```bash
# 单元测试
pytest --cov=leo_ppt_generator --cov-report=term-missing --cov-fail-under=80

# 集成测试
pytest tests/integration/ --cov-append

# 边界测试
pytest tests/boundary/ --cov-append

# 最终报告
coverage report --fail-under=80 --omit="*/_vendor/*,*/tests/*"
```

覆盖率不足时：

- 识别未覆盖的关键分支（if/else、exception handlers）
- 优先补充错误路径和边界条件测试
- 不为达标而添加无意义测试（如纯 getter/setter）

### 13.7 Claim ceiling

- fixture 通过证明受控输入下的机制正确，不证明所有视觉页面效果一致。
- 真实 provider smoke 只证明当次模型、网络和凭据路径可用。
- 结构验证不等于视觉完全等价。
- 未经 PowerPoint 桌面查看的产物不得声称已完成桌面兼容验证。
- 20 轮角色审视证明需求覆盖与决策可追溯，不替代任何代码、安装、PPTX 或现场验证。

### 14. 性能基线与资源管理

#### 14.1 典型场景预期耗时

以下数值是 U5 首轮测量所使用的预算假设，不是当前已验证的性能承诺。U5 必须在固定 provider、网络条件、页面 fixture、worker 数量和 runtime identity 下记录实测分布；未取得实测前只报告 `baseline_unverified`。

以 10 页标准 PPT 为测量场景（16:9 宽屏，中等内容密度）：

| 阶段 | 预期耗时 | 主要影响因素 |
| --- | --- | --- |
| Image-deck prepare | 10-30s | 内容解析、样张生成 |
| 单页图片生成 | 1-3 min | Backend API 速度、内容复杂度 |
| 多页并发（4 workers） | 3-8 min | 并发度、API rate limit |
| Image 组装 | 5-15s | 图片大小、页数 |
| Editable prepare | 30-90s | OCR、输入规范化 |
| 单页重建 | 2-5 min | 页面对象数量、图片处理 |
| 多页并发（4 workers） | 6-15 min | 并发度、OCR 准确度 |
| Editable finalize | 20-60s | Manifest 验证、PPTX 组装 |
| Hybrid 组装 | 10-30s | 页面数量、前置条件验证 |

总耗时预估：

- **Generate 路由**（纯图片）：5-12 分钟
- **Direct-editable 路由**：8-18 分钟
- **Upgrade-full 路由**：在 generate 基础上 + 8-18 分钟
- **Upgrade-selected 路由**（选中 3 页）：在 generate 基础上 + 3-8 分钟

#### 14.2 超时策略

| 超时类型 | 默认值 | 可配置 | 超时后行为 |
| --- | --- | --- | --- |
| Worker 单页超时 | 10 min | ✅ config.yaml | 标记该页面 timeout，不阻塞其他页面 |
| Backend API 单次调用 | 60s | ✅ config.yaml | Retry 3 次，exponential backoff |
| CLI 命令超时（非组装） | 5 min | ❌ | 返回 timeout，可 retry |
| 组装/finalize 超时 | 10 min | ❌ | 返回 timeout，不可部分完成 |
| Run 总超时 | 无限制 | ❌ | 由用户或 Agent 宿主取消 |

超时后行为：

- **Worker 超时**：标记为 `worker_timeout`，可通过 reset + retry 恢复
- **Backend API 超时**：自动 retry，3 次失败后标记页面 `backend_timeout`
- **CLI 超时**：CLI 进程被终止，状态回滚到最后 checkpoint
- **组装超时**：拒绝交付半成品 PPTX，保留中间产物供诊断

超时配置示例（config.yaml）：

```yaml
timeouts:
  worker_page_seconds: 600      # 10 minutes
  backend_api_seconds: 60       # 1 minute
  backend_api_retries: 3
```

#### 14.3 性能监控与报告

`reports/timing.json` 结构：

```json
{
  "schema_version": 1,
  "run_id": "...",
  "stages": [
    {
      "stage": "image.prepare",
      "started_at": "2026-08-20T10:00:00Z",
      "completed_at": "2026-08-20T10:00:15Z",
      "duration_seconds": 15
    }
  ],
  "pages": [
    {
      "page_id": "page_003",
      "capability": "image-deck",
      "started_at": "2026-08-20T10:01:00Z",
      "completed_at": "2026-08-20T10:03:30Z",
      "duration_seconds": 150,
      "retry_count": 1
    }
  ],
  "backend_calls": [
    {
      "provider": "atlascloud",
      "operation": "generate",
      "duration_seconds": 45,
      "retry_count": 0,
      "rate_limited": false
    }
  ],
  "summary": {
    "total_duration_seconds": 720,
    "worker_wait_seconds": 420,
    "backend_api_seconds": 380,
    "assembly_seconds": 12
  }
}
```

`run diagnose` 可以读取 `reports/timing.json` 并给出以下确定性提示，不增加独立 performance 命令：

- Backend API 频繁 rate limit → 建议降低并发度或切换 provider
- 单页耗时 > 2× 平均值 → 标记异常页面，建议检查内容复杂度
- 总耗时 > 预期 1.5 倍 → 建议检查网络、backend 健康度或 worker 资源

#### 14.4 规模限制

首版支持范围：

| 限制项 | 值 | 超限行为 |
| --- | --- | --- |
| 图片生成最大页数 | 50 页 | 拒绝创建 run，reason_code=input_too_large |
| Direct-editable 最大页数 | 100 页 | 同上 |
| Upgrade 最大可选页数 | 50 页 | 同上 |
| 单页图片最大尺寸 | 25 MB | 警告，不阻止（可能影响性能） |
| 总 PPTX 最大大小 | 200 MB | 警告，不阻止 |
| Run 目录最大磁盘占用 | 10 GB | 拒绝组装，reason_code=disk_quota_exceeded |

规模限制检查：

- 在 `run create` 时预检查输入页数
- 在组装前检查磁盘占用
- 超限时明确报告限制和建议（分批处理、选择子集）

未来扩展方向（不在 MVP 范围）：

- 流式处理输入 PDF（避免一次性加载全部页面）
- 增量组装 PPTX（边生成边组装，不等待全部完成）
- 页面级缓存和去重（相同内容页面复用生成结果）
- 分布式 worker 调度（跨机器并发）

### 15. Risks & Dependencies

| 风险 | 控制 |
| --- | --- |
| 顶层 Skill 膨胀成三套规则拼接 | SKILL.md 只保留路由和主流程；详细规则一层 references 渐进加载 |
| 安装说明与 Codex 发现机制漂移 | 同时记录官方用户级位置和内置安装器实际目标；release tests 校验两条路径，不隐藏差异 |
| Skill 在仓库内可用但安装后断链 | 所有资源以 Skill 根目录解析；隔离 bundle、任意 cwd 和完整引用图作为发布门 |
| 20 轮审视退化为形式化凑数 | 每轮必须改变需求、风险、验证或给出证据充分的不修改理由；重复项合并到 canonical owner |
| 内容正确但视觉不可读，或视觉漂亮但事实错误 | 内容、叙事、视觉、结构/可编辑和现场质量使用非补偿式独立门禁 |
| 自动视觉规则被外推为人工审美通过 | 自动检查只证明可读性和结构底线；人工视觉与演讲效果保持独立 claim ceiling |
| 两个旧 Skill 仍被宿主发现 | 不在可发现目录保留旧 SKILL.md；增加 bundle inventory 测试 |
| 脚本式 codex 源码难 package 化 | U0 先验证 import/resource；只做必要路径改造 |
| 为统一配置而重写 backend | 统一选择合同和映射，保留内部实现 |
| Agent 与 CLI 职责重叠 | CLI 只提供确定性步骤和 `next_action`；Skill 拥有交互与 worker |
| CLI 文案变化破坏 Workflow | 控制流只消费 versioned enum、payload 和 reason code，不匹配展示文本 |
| 新能力直接耦合 vendor 内部字段 | `CapabilityAdapter`、`PageArtifact` 和 import-boundary 测试 |
| route 扩展演化成通用 DAG 平台 | 只实现四条 code-owned 有限 route，不提供 parser、cycle detector、动态 registry 或 scheduler |
| 成功响应丢失导致重复 mutation/API 消费 | operation id、idempotency key、result hash、safe-to-retry 和冲突合同 |
| 原子 rename 后断电仍丢失 checkpoint | 关键状态和 current pointer 使用 file fsync + parent directory barrier |
| hybrid 被误称全可编辑 | 逐页 mode manifest + finalizer hard check |
| 部分失败被自动包装为成功 | 默认 fail closed；partial-hybrid 需要绑定当前失败集合的用户确认 |
| 上游更新难同步 | clean-tree pin、patch 文件、上游回归和同步 diff |
| 相同 Skill 在不同时间安装出不同依赖 | 发布 lock、runtime identity 绑定 lock/Python/平台、clean install 测试 |
| Skill 更新导致活动 run 无法恢复 | 不可变版本环境、run 固定 identity、旧版本保留和兼容 fixture |
| 并发写 `run.json` 丢更新 | 单 writer、file lock、expected revision、原子替换和 reconciliation |
| 临时文件和失败 attempt 长期占满磁盘 | tmp/work 正式分层、scoped dry-run/apply cleanup、active run 拒绝和 receipt |
| 日志泄露正文或凭据 | 字段 allowlist、脱敏引用、worker 独立日志和禁止环境/正文 dump |
| editable 失败破坏图片交付 | 两阶段目录隔离，image deliverable 独立完成 |
| 离线测试被外推为现场质量 | fixture、真实 provider、OCR、viewer 和人工视觉证据分层报告 |

## Definition of Done

- U0 的 `docs/reviews/u0-report.md` 为 `decision: go`；若为 no-go，本计划正确终止并返回修订，不得把 U1–U5 的未执行状态解释为完成失败。
- 仓库和发布包中只有一个用户可发现的 `leo-ppt-generator` Skill。
- 用户只安装当前 Skill；两个旧 Skill 和旧 CLI 不存在时，主流程仍可运行。
- Skill 可按当前官方用户级发现位置或内置 `skill-installer` 安装；文档准确说明两者的实际目标目录、来源 ref 和重新发现条件。
- 从任意 cwd 启动时，所有 script、prompt、reference、schema、patch、license 和 runtime 路径都以 Skill 根目录解析；安装包内零 broken reference。
- 发布包中不存在 `third_party/`、第二个 `SKILL.md`、旧 CLI 入口、`__pycache__`、`.pyc`、`.pyo`、旧 build 或未登记临时产物。
- Skill bundle 内包含受管 runtime、两个固定版本的必要源码、prompt、reference、测试合同和许可证信息。
- `runtime_manager.py ensure|doctor|print-cli` 可用且 source identity 可验证。
- runtime 使用不可变 identity 目录、安装锁、验证后原子切换和可验证 rollback；活动 run 固定并保留创建它的 runtime。
- 发布依赖由经过 clean install 验证的 lock 固定，runtime identity 绑定 source、upstream、patch、lock、Python 和平台。
- 顶层 Skill 拥有路由、确认、worker 派发、阶段衔接和交付判断；runtime 不模拟 Agent 宿主。
- image-deck 与 editable 保持独立 versioned adapter、状态文件和领域验证 owner；adapter 外部不能 import `_vendor`。
- 跨能力页面只传 versioned `PageArtifact`，hybrid 不读取 vendor 私有状态。
- 四条 route 由 `application/routes.py` 的有限 code-owned 定义表达；运行时不能注入任意步骤，新增 route 必须经过代码、schema、测试和 release 变更。
- `run.json` 只做轻量跨阶段索引，不成为第三套页面状态；具备 schema、revision、锁、expected revision 和 reconciliation。
- CLI 机器协议的 route/stage/status/action/reason code 版本化，自由文本不驱动控制流。
- 所有 mutation 有 idempotency、operation status、state hash、safe-to-retry 和 conflict 合同；成功响应丢失不导致重复 provider 调用。
- `run.json`、vendor 正式状态、delivery/validation 和 runtime current pointer 达到规定的 durable-file/barrier 等级，并通过 crash-point 测试。
- config 和 backend contract 具有 schema version、配置来源和 capability validation。
- 首次使用流程能区分配置有效、本地 runtime、宿主 worker、provider 凭据、Office 应用和人工验收状态，并为每个未就绪项给出稳定 reason code 与安全动作。
- 图片生成、直接可编辑、全量升级和指定页 hybrid 路由语义明确。
- 内容生成先完成受众、目标、场景、时长、事实边界、叙事主线、大纲、逐页稿、视觉方向、backend 和样张确认。
- 图片式交付通过文字准确性、可读性、布局、风格一致性、required asset、图表真值和整套叙事检查；最终图片变化后重新组装、渲染并验证 PPTX。
- 可编辑交付通过对象级可编辑、字体替代、文本溢出、遮挡、页面尺寸、notes、页序和整页栅格禁止项检查。
- selected-page hybrid 保持页数、页序、尺寸和 notes，并逐页声明 `image|editable`。
- partial-hybrid 默认关闭；只有用户确认当前成功/失败集合后才生成，失败页保持原 image 并附 failure report。
- 缺页、页面验证失败或 finalizer 失败不能报告成功。
- 图片阶段成功结果不会因后续 editable 失败而丢失。
- 上游固定 commit、license、导入 tree、patch 和回归测试可追溯。
- 能力账本每一项都有具体可执行 `proof_case`，最终 collection 逐项覆盖，不使用抽样或文件存在性代替行为证明。
- `sync_upstreams.py --check` 能拦截 tree、patch、vendor、license、测试映射和 lock 漂移。
- `events.ndjson`、分离 worker logs 和 `run diagnose` 提供脱敏、只读、可复核的运行证据。
- `cleanup --dry-run|--apply` 具有 fingerprint、revision、active worker、containment 和 receipt 保护，不提供宽泛全局删除。
- 四条 route e2e、partial 降级 fixture、Skill 行为 eval、受管 runtime 安装测试、稳定性兼容矩阵和聚焦回归全部通过。
- 真实 provider、OCR、Office viewer 和人工视觉验证分别报告，任何单项结果不越过其 claim ceiling。
- 每个 reason_code 在 `skills/leo-ppt-generator/references/reason-codes.md` 中文档化，包含含义、可恢复性和建议恢复动作。
- 测试覆盖率达到规定标准（adapter ≥80%、run_index ≥90%、hybrid ≥85%），边界测试覆盖并发、crash、idempotency 和版本不兼容场景。
- 发布附带版本兼容性声明，包含 runtime 兼容性、config schema 支持范围、上游版本和已知限制。
- 提供 troubleshooting 文档或 diagnose 命令输出，覆盖常见失败场景和恢复路径。
- 根目录与 Skill bundle 的 MIT 许可证一致；README、用户教程、测试方案、兼容性和已知限制链接有效，README 不包含用户明确排除的内部报告导航。
- 20 轮多角色复核每轮都有证据、冲突、决策、改动或不修改理由；重复发现合并到 canonical owner，不以轮次数量替代质量。
- 最终全套测试、Wheel、Skill clean install、四 route doctor、上游逐项 proof、发布文档检查、代码审查和工作树 fingerprint 均绑定同一最终树。
- MVP 不包含新的通用数据库、scheduler、安全平台或审计系统。

## Appendix

### A. 常见问题排查

#### A.1 安装与配置问题

**Q: `ensure` 失败，提示 "lock hash mismatch"**
```
A: 运行 doctor 确认精确 identity，再由 ensure 在安装锁内隔离损坏目录并重装：
   python "$SKILL_DIR/scripts/runtime_manager.py" doctor --route <route>
   python "$SKILL_DIR/scripts/runtime_manager.py" ensure
```

**Q: `doctor` 报告 "OCR capability missing"**
```
A: 按 doctor 返回的 OCR provider、credential reference 和恢复动作配置当前后端。
   不把安装任意本地 OCR 软件视为通用修复；配置后重新运行：
   leo-ppt doctor --route direct-editable
```

**Q: `doctor` 报告 "credential_missing"**
```
A: 配置 backend 凭据：
   使用 provider adapter 文档列出的环境变量或操作系统 credential reference；不要把 secret 写入 config.yaml。
   验证：leo-ppt doctor --route generate
```

#### A.2 运行时问题

**Q: Run 卡在 "waiting_for_worker"**
```
A: 检查 worker 状态和日志：
   leo-ppt run status <run> --json
   查看日志：cat <run>/logs/workers/<page_id>.log
   如果 worker 超时：leo-ppt editable reset <run> --page <id>
```

**Q: Hybrid 组装失败 "assembly_precondition_failed"**
```
A: 运行诊断：
   leo-ppt run diagnose <run>
   常见原因：
   - page dimension mismatch: image-deck 和 editable 使用了不同页面尺寸
   - validation failed: 部分选中页未通过 editable validation
   - source hash changed: selection 后 image 页面被修改
   建议：检查 diagnose 输出的具体失败条件，重新 prepare 或调整 selection
```

**Q: Backend API 频繁返回 429 (rate limited)**
```
A: 调整并发度：
   编辑 config.yaml:
     max_concurrent_workers: 2  # 降低并发
   或切换到支持更高 rate limit 的 provider
```

#### A.3 恢复与清理问题

**Q: 旧 run 无法打开，提示 "runtime_incompatible"**
```
A: 检查 runtime 兼容性：
   leo-ppt run status <run>
   如果 runtime 不可用：
     - 安装对应版本 Skill（如果有兼容新版）
     - 或检查 ${LEO_PPT_HOME}/runtimes/ 中是否有对应 identity
   如果 runtime 已删除：
     - 运行 diagnose 查看是否可恢复
     - 或放弃该 run 并创建新 run
```

**Q: Backend 凭据过期，如何从断点继续**
```
A: 刷新凭据并从失败页面重试：
   1. 刷新凭据（重新登录或更新环境变量）
   2. 验证凭据：leo-ppt doctor --route <route>
   3. 从失败页面重试：leo-ppt run retry <run> --from-failed-pages
```

**Q: Run 目录占用磁盘过大**
```
A: 清理临时文件和旧 run：
   leo-ppt run cleanup <run> --scope temp --dry-run  # 预览可重建临时文件
   leo-ppt run cleanup <run> --scope temp --apply    # 执行同一 fingerprint 的计划
   # MVP 不提供跨 run 全局 gc；每个 run 必须单独 dry-run/apply
```

#### A.4 性能问题

**Q: 生成耗时远超预算假设**
```
A: 运行诊断并查看 timing report：
   leo-ppt run diagnose <run>
   cat <run>/reports/timing.json
   根据 bottleneck 提示：
   - Backend API slow: 切换 provider 或检查网络
   - Worker timeout: 检查内容复杂度，考虑增加超时时间
   - Rate limited: 降低并发度
```

**Q: 单个页面耗时特别长**
```
A: 检查该页面日志：
   cat <run>/logs/workers/<page_id>.log
   查看 timing report:
   cat <run>/reports/timing.json | jq '.pages[] | select(.page_id=="<page_id>")'
   如果内容过于复杂，考虑简化或分批处理
```
