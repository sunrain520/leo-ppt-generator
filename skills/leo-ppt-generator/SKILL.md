---
name: leo-ppt-generator
description: 从文章、报告、笔记或大纲生成图片式 PPTX；把图片、PDF 或用户确认可信的 PPT/PPTX 重建为对象级可编辑 PPTX；或将已完成的图片式演示文稿整套、指定页面升级为 editable/hybrid。用于用户要求制作 PPT、生成幻灯片、把视觉稿转成可编辑 PowerPoint、升级图片版 PPT 或保留部分图片页时。
---

# Leo PPT Generator

通过一个入口完成图片式、全可编辑或 hybrid PPTX。顶层 Agent 拥有意图、确认、
live host capability、worker 派发和交付判断；`leo-ppt` 只拥有确定性准备、状态、
验证和组装。

## 首次使用

1. 读取 [输入路由](references/input-routing.md)，选定且仅选定
   `generate`、`direct-editable`、`upgrade-full` 或 `upgrade-selected`。
2. 读取 [首次使用](references/first-use.md)，由 Agent 自动运行当前平台 launcher，
   消费其 `cli_reference`，再运行 setup。不要让普通用户执行 runtime 初始化命令。
3. 只有宿主现场明确声明图片能力 available，才走零密钥内置路径；unknown 先核实，
   unavailable 才展示符合任务 capability 的外部图片 Provider。
4. 只有确实缺少所选外部服务凭据时，暂停原任务并给用户一条本地终端命令；禁止用户
   在聊天中粘贴 secret。命令成功后自动回到原任务，不重复询问已确认的内容。
5. 使用统一配置入口读取与解释状态，不手写 backend JSON 或凭据字段：

   `"$LEO_PPT" config status --json --route <route>`

   `configured_unverified` 表示本地配置完整且允许开始任务（`
   execution_eligibility=allowed`、`installation_readiness=usable_unverified`），
   首张真实业务图片承担惰性验证；`ready` 只表示当前 Route 所需能力已被有效
   evidence 或宿主现场能力完整覆盖。`not_configured`/`invalid` 才暂停图片节点，
   只输出一个 `run_cli` Primary_Action 终端命令。

不得调用、安装或要求用户安装额外历史 CLI。不得从 PATH 猜测 `leo-ppt`，不得把
launcher、setup、backend JSON 或内部诊断步骤当作普通用户的前置教程。

6. 在产生 backend contract、样张、逐页合同或 run 前，先冻结唯一项目目录
   `<project-root>`。共享输出根下必须为每个课件创建独立子目录；禁止把输入、样张、
   backend contract、run 或最终 PPTX 直接写到共享输出根。项目目录固定分层为
   `sources/`、`contracts/`、`samples/`、`runs/` 和 `deliveries/`；其中正式运行状态
   只写入 `runs/<run-id>/`，canonical PPTX 只写入该 run 的 `final/`。
7. 用户确认 provider 与 mode 后，用 registry 生成并校验 backend contract，不手写
   capability 或 credential 字段：

   `"$LEO_PPT" backend create --provider <builtin-imagegen|openai|openai-compatible|atlascloud> --mode <generate|edit> --output <project-root>/contracts/backend-<mode>.json`

   `"$LEO_PPT" backend validate <project-root>/contracts/backend-<mode>.json`

   `valid` 只证明合同结构有效；仍须按 `credential_reference_status` 处理真实凭据，
   并在执行前完成 provider smoke。

8. 为每次交付创建独立 run：

   `"$LEO_PPT" run create --route <route> --input <project-root>/sources/<input> --project-root <project-root> --output <project-root>/runs/<run-id> --backend-contract <project-root>/contracts/backend-<mode>.json --idempotency-key <key> [--office-trusted]`

   `--office-trusted` 只表示用户已确认来源可信；preflight 仍会拒绝旧 `.ppt`、宏、
   嵌入对象、external relationship、远程模板或损坏 PPTX。`run create` 会流式
   复制输入和 backend contract，记录 hash、大小、类型并固定 runtime identity。
9. 推进前运行 `"$LEO_PPT" run status <run> --json`；失败时运行
   `"$LEO_PPT" run diagnose <run> --json`。响应丢失时使用
   `"$LEO_PPT" run operation <run> --id <operation-id> --json`，不得换 key 重复创建。

## 不变边界

- 在会改变结果前确认大纲、完整内容、风格、图片 backend、样张或升级页集合。
- 只依据 CLI 的 versioned JSON、状态文件、manifest、validation 和 artifact
  推进；聊天声明与自由文本不构成完成证据。
- 不手写领域状态 JSON，不直接 import `_vendor`，不让 hybrid 读取 vendor
  私有状态。
- 顶层 Agent 不模拟本地 scheduler。多页任务要求 worker 时，分别核对当前用户
  授权、当前会话可调用能力、容量和实际派发结果。
- 多页 worker 缺失、未知或调用失败时返回
  `blocked/worker_capability_unavailable`；不得由主 Agent 静默串行替代。
- 恰好一页时，只有 CLI 明确返回
  `single_unit_current_agent_allowed`，当前 Agent 才可按同一 prompt、record 和
  validation 合同执行。
- 不可信 Office 输入、宏、嵌入对象、external relationship 或远程模板返回
  `blocked/untrusted_office_input`；不得“警告后继续”。
- 凭据由宿主或 backend allowlist 管理。不得读取宿主私有认证文件，不得把
  token、完整环境或用户正文写入日志。
- backend contract 只允许 `env:`、`host:` 或 `keychain:` credential reference；
  不得调用旧 `setup/config` 保存明文凭据。
- 统一配置入口是 `leo-ppt config`；`config status` 只读零外部调用，
  `config provider` 与 `config credential` 管理 Provider 和安全凭据引用，`verify --yes`
  是显式付费 smoke（默认拒绝、一次性 consent），`repair` 从最早未完成步骤续接。
  宿主不得代替用户录入密钥或把聊天内容变成凭据通道。
- `configured_unverified` 允许开始任务；只有 `not_configured`/`invalid` 才暂停
  图片节点并只给一个 `run_cli` Primary_Action。`ready` 需要有效 Capability_Evidence
  或宿主现场能力，禁止把 `unknown` 当 `available` 产生零密钥假绿。
- 结构验证不等于视觉等价；真实 provider、OCR、Office viewer、PowerPoint
  桌面和人工视觉证据分别报告。
- 顶层 `status=completed` 只表示产物阶段结束；继续读取 `delivery_readiness`。
  `acceptance_pending` 必须补齐独立渲染与人工验收，只有 `accepted` 才能报告交付闭环。
- 顶层 run 的 `image assemble`、`editable finalize` 和 `upgrade finalize` 只能把 canonical
  PPTX 写入当前 run 的 `final/`；不得用 `--output` 绕过项目目录或直接发布到共享根。

## 固定上游能力入口

所有保留的上游确定性工具都通过 `LEO_PPT` 指向的当前 runtime 唯一 CLI 调用：

- `"$LEO_PPT" upstream codex-ppt -- <tool> <args...>`：图片生成、编辑、prompt
  准备、dispatch/result/blocker/status、chroma-key 与 notes/PPTX 组装；
- `"$LEO_PPT" upstream editable-ppt -- <command...>`：输入规范化、OCR hints、
  page worker 状态、manifest build/validate/finalize、图片资产与公式工具。

这些入口运行 bundle 内固定 commit 的源码，不查找 PATH 中的旧 CLI。返回值外层始终
使用 `leo-ppt-machine/v1`；`result.stdout` 保留上游结构化或文本结果，
`result.returncode != 0` 必须阻止推进。逐项映射位于 bundle 内的
`upstream-capabilities.yaml`。

## Route 执行

### generate

读取 [图片式工作流](references/image-deck-workflow.md)、
[Backend 选择](references/backend-selection.md) 和
[视觉质检规范](references/visual-qa.md)。

先确认内容、大纲、完整逐页稿、视觉风格、backend 与一个样张；选择风格前读取
[风格库](references/style-library.md)。选定视觉风格、论证模式、版式与信息图
类型后，用 `"$LEO_PPT" style render <视觉风格> --mode <论证模式> [--layout <版式>
--image-type <信息图类型>]` 得到**确定性模板注入内容**（视觉风格 brief + 配对
图片渲染 paste-ready + 论证骨架 + 版式骨架），写进 `deck_spec.style` 与
`slides[].layout`；不得自由文本手写 style/layout。样张通过后准备
slide jobs；多页时按 [slide worker prompt](prompts/slide-worker.md) 每页派发
一个受限 worker。记录每个结果，缺页或未完成状态必须阻止组装。每页视觉质检按
`visual-qa.md` 对抗式审查：worker 正向自查后，父 Agent 独立复核、专门找茬，
任一失败打回该页重做，其他检查通过不能补偿。最终报告图片式
PPTX、逐页图片、notes、backend provenance 和验证结果。

确定性阶段依次使用 `"$LEO_PPT" image prepare <run>`、
`"$LEO_PPT" image record <run> --slide <id> --agent-id <id> --result <path> --expected-state-hash <hash>`
和 `"$LEO_PPT" image assemble <run> [--rebuild]`。`--rebuild` 只能创建新 artifact
revision，不能覆盖旧交付物。

### direct-editable

读取 [可编辑工作流](references/editable-workflow.md)、
[Manifest Schema](references/manifest-schema.md) 和
[Page Decision Tree](references/page-decision-tree.md)。

图片/PDF 可直接 prepare；PPT/PPTX 必须先完成可信确认与 preflight。多页按
[page worker prompt](prompts/page-worker.md) 派发，逐页 record 后才能
finalize。不得用整页截图加少量文本框冒充对象级可编辑。

稳定入口依次为 `editable prepare`、`editable next`、`editable dispatch`、
`editable record`、`editable reset` 和 `editable finalize`；真实 spawn 成功前不得
调用 dispatch。PDF/可信 PPTX 的 prepare 必须产生逐页 source，不能把容器文件
冒充单页图片。

### upgrade-full

先 inspect 已完成的 image-deck 并冻结每页 source hash、页序、尺寸与 notes，
再按 `direct-editable` 处理全部页面。editable 失败不得删除或降级原图片式
交付物；只有全部页面和 deck validation 通过才声明全可编辑。

### upgrade-selected

先 inspect image-deck 并确认、冻结选中页集合，再只对选中页执行 editable
工作流。组装前验证页数、selection 顺序、尺寸、validation、notes、source
hash 与总页数。

默认任一选中页失败即不交付 partial。只有用户在看到当前成功/失败集合后明确
接受，才能生成 `partial-hybrid`；失败页保持原 image。`hybrid` 和
`partial-hybrid` 均不得声称全可编辑。

最终使用 `"$LEO_PPT" upgrade finalize <run>`；只有已展示并确认当前失败集合时才传
`--allow-partial`。相同 PageArtifact、selection 和 failure fingerprint 重放原
结果；变化时创建新 revision 并保留旧 PPTX/manifest。

## Worker 返回

每个 worker 只拥有一个 slide/page 目录。父 Agent 在真实 spawn 成功后才记录
dispatch，并要求 worker 返回：

- worker/agent id 与 slide/page id；
- 选中产物的绝对路径；
- backend 与输入 provenance；
- validation/QA 结果和可复核证据路径；
- 失败时的稳定 reason code。

worker 不修改其他页面、顶层 run index、最终 PPTX 或 Git 状态。父 Agent 负责
record、最终验证和交付。

## 失败与恢复

- 读取 [Reason Codes](references/reason-codes.md)，报告 route、stage、
  slide/page id、证据路径和可执行恢复动作。
- 相同失败再次执行前，必须改变输入、配置、backend 或实现。
- 自动重试只复用同一 idempotency key，且只在 `safe_to_retry=true` 时执行。
- 响应丢失时先查询 operation/status，不创建重复 mutation。
- 中断保留已完成产物和 checkpoint；显式 cancel 才进入不可 retry 的 terminal
  状态。
- `run retry <run> [--from-failed-pages]` 只在 `safe_to_retry=true` 时执行；
  `run cancel <run> --wait-workers` 不可自动重试。
- 清理先运行 `run cleanup <run> --scope temp|failed-attempts|input --dry-run`，再对
  完全相同 fingerprint 运行 `--apply`；`input` 只允许 terminal run，删除不可恢复。
- image deliverable 已验证后，后续 editable/hybrid 失败不得破坏它。

## 交付

最终回复必须给出：

- route、runtime identity、上游/patch/lock identity；
- PPTX 与必要逐页/notes/failure report 路径；
- `image`、`editable`、`hybrid` 或 `partial-hybrid` 的准确交付类型；
- 结构验证结果与未运行的 provider/OCR/viewer/desktop/人工视觉验证；
- 保留的可恢复产物、限制和下一步。

没有通过对应 validation、缺页、finalizer 失败或未知机器协议时，不得声明成功。
