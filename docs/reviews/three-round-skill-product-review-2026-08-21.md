# Leo PPT Generator 三轮 Skill 产品审查报告

日期：2026-08-21  
审查方式：四角色并行、三轮递进、逐项修复与回归  
角色：产品专家、研发专家、测试专家、PPT 专家  
最终裁决：`LOCAL SKILL RELEASE CANDIDATE / EXTERNAL FIELD VALIDATION REQUIRED`

## 1. 结论

当前项目已达到“可从本地交付安装、可稳定执行、四条路线离线机制闭环、证据分层可观测”的 Skill 发布候选标准。18 个审查问题均已逐项完成并写入实现/测试证据；真实 provider、PowerPoint 与人工视觉仍必须在每次真实交付中形成独立 receipt，不能由本地测试替代。

- 本地 Skill、runtime、四 route 与发布机制：GO。
- `generate`、`direct-editable`、`upgrade-full`、`upgrade-selected`：离线安装后黑盒 GO。
- 真实 provider/OCR/PowerPoint/人工视觉：按现场 receipt 独立判定，当前不声明已通过。
- GitHub 远端发布：未执行；当前 README 只提供真实可用的本地交付安装入口。

安装可达性、完整用户旅程、内容真实性、视觉质量、可编辑性、notes、provenance、终态一致性与人工验收仍是非补偿门；自动化通过只证明本地机制，真实现场门必须由对应 receipt 通过。

当前 231/231、60/60 capability mappings、82/82 全绿，覆盖率 87.14%；60 个映射对应 42 个唯一 proof case。安装后唯一绝对 CLI 已覆盖四路线成功/replay/失败保留。它们不能证明真实 provider、PowerPoint、人工视觉或具体成品质量，远端也尚未发布。

## 2. 审查范围与完整性

本轮没有抽查。各角色建立全集后逐项检查：

- 当前 Skill 产品面：115 个文件。
- 两个上游 Skill 运行与合同面：76 个文件。
- 上游 Python：43/43 有映射，其中 39 个字节一致，4 个为已登记 patch。
- vendor lock：46/46 文件通过。
- 内置风格：12/12 字节一致。
- 能力账本：24 个 C、30 个 E、4 个 X，共 58 项；58 个 proof_case 均逐项运行，但仅对应 40 个唯一 pytest node。
- 当前测试：参数化收集 198 项，全部通过。
- editable 固定上游：7 个测试文件，82/82 test methods 通过。
- `skills/leo-ppt-generator/third_party/`：不存在。
- bundle 内 `SKILL.md`：仅 1 个。
- 根许可证与 Skill 许可证：字节一致；上游 MIT notice 独立保留。
- README 中用户要求删除的审计性短语：未出现。

审查范围包含当前工作树，而不只包含 Git diff。当前 `HEAD` 和 `origin/main` 都是 `2230fa83bf358a64386d21b97765c5421d4537df`，产品主体仍是未提交文件；本轮未提交、未推送、未创建 PR。

## 3. 三轮审查方法

### 第一轮：完整性与角色独立审查

- 产品：安装、初始化、提示、用户旅程、错误恢复、文档与产品承诺。
- 研发：vendor、adapter、CLI、route、doctor、状态、锁、schema、打包和两上游映射。
- 测试：逐测试、逐 capability、回归、wheel、安装、失败注入和证据边界。
- PPT：内容、叙事、视觉、可编辑重建、PPTX 组装、notes、渲染和交付质量。

第一轮不接受“测试全绿所以完整”的推断。

### 第二轮：第一性原理与墨菲定律审查

四角色对 A-P 统一候选逐项尝试推翻，并检查断电、并发、迟到 worker、凭据、状态漂移、图片压缩、错误确认和真实用户照文档操作等故障。

第二轮结果：13 项确认、2 项降级、1 项原始表述被驳回；另发现 notes、provenance、人工验收和品牌模板语义等新的级联缺口。

### 第三轮：交叉验证与发布裁决

- 研发对高风险项检查完整调用链：文档/SKILL -> CLI -> application/adapter -> vendor/finalizer -> manifest/evidence。
- 测试把高风险项转为可执行的黑盒或边界测试设计。
- PPT 专家按四条真实用户旅程作成品交付裁决。
- 产品专家按“能安装、能运行、能产出、能高质量交付”四层校准最终承诺。

## 4. 主要发现

### P1-01：远端安装入口当前不可用

证据：

- `README.md:26-32` 和 `docs/user-guide.md:9-15` 指示从 GitHub 安装 `skills/leo-ppt-generator`。
- `origin/main@2230fa8` 只有 5 个旧文件，不含 README 和 Skill 目录。

影响：外部用户按正式指引无法获得 Skill，本地所有测试不能形成远端发布证据。

修复：先完成其余发布阻断，再提交并发布固定 commit/tag；从全新临时 HOME 按 README 原命令安装，验证唯一 Skill、`ensure installed -> reused`、四 route doctor 和绝对 CLI。

双向钢人论证：支持原判断的一方认为，README 指向未包含 Skill 的远端仓库会让所有外部用户安装失败，任何本地测试都不能使该命令变真；反对一方最强的论点是，当前交付形态本就是本地 Skill bundle，发布远端需要独立的提交/推送授权，不应为了消除文档问题擅自改变外部状态。真正分歧在于“当前可安装交付”和“公开远端发布”是否是同一门；关键变量是是否已有固定 commit/tag 及 clean HOME 远端安装 receipt。当前选择先保证本地交付入口真实可用，并移除死链接；远端发布保留为明确的外部发布动作。

状态：**已完成（当前本地 Skill 交付入口与安装后黑盒证据）**。README 和用户教程已移除必然失败的 GitHub 安装/clone 命令，改为从当前交付的
`skills/leo-ppt-generator` 安装到两种受支持发现目录，均用 `test ! -e` 防止覆盖；文档明确远端 `main` 尚未发布本交付，只有固定 commit/tag 通过 clean HOME 验收后才恢复远端安装指引。`tests/release/test_installed_routes.py` 已从隔离安装目录和绝对 CLI 验证四 route。此状态关闭“用户按正式指引必然失败”的产品问题，但不声称 GitHub 已发布。

### P1-02：Python 兼容声明与实际发布 lock 矛盾

证据：

- `README.md:22`、`runtime/pyproject.toml:9` 声明 Python 3.10+。
- `scripts/runtime_manager.py:148-151,193-204` 要求当前 Python minor、平台、架构精确匹配 lock。
- bundle 仅有 `py312-darwin-arm64.txt`。

影响：Python 3.10/3.11/3.13、macOS Intel、Linux、Windows 即使满足文档要求，也会在安装前必然失败。

修复：补齐真实支持矩阵的锁与测试，或把文档和 package metadata 收窄为 Python 3.12/macOS arm64。

双向钢人论证：支持原判断的一方认为，宣称 3.10+ 却只提供 3.12/macOS arm64 lock，会让用户在安装后才遇到不可恢复失败，属于发布合同误导；反对一方最强的论点是，过早收窄支持范围会牺牲 Linux/Windows 与其他 Python minor 的潜在可用性。真正分歧在于“潜在可运行”能否写进公开兼容声明；关键变量是每个平台是否有可复核 lock、clean install 和 route smoke 证据。当前没有这些证据，因此选择收窄声明，而不是猜测扩展兼容矩阵。

状态：**已完成（兼容声明收敛与 wheel 元数据证据）**。runtime `requires-python` 已收窄为 `>=3.12,<3.13`，README 与 compatibility 文档明确当前只支持 Python 3.12.x/macOS arm64；发布 wheel 检查同步验证 `Requires-Python`、MIT 元数据和无遗留入口。未取得其他平台的独立安装证据前，不再对其作支持承诺。

### P1-03：backend contract 没有被执行层消费

这是 `host:/keychain:`、AtlasCloud 与 Codex OAuth 三个症状的共同根因。

证据：

- `config/backend_contract.py:41-52,65-136` 接受 env/os-store reference，并为 AtlasCloud 声明 `ATLASCLOUD_API_KEY`。
- `application/run_index.py:165-213` 只复制并摘要 backend contract。
- `upstream_bridge.py:166-192,207-263` 不读取 run contract；没有 host/keychain resolver，不透传 Atlas key，并把 `CODEX_AUTH_FILE` 指向不存在的临时文件。
- codex vendor 的 Atlas 路径仍使用 `OPENAI_BASE_URL` 与 `OPENAI_API_KEY`。
- editable vendor 原本支持 Codex auth file，但集成层主动隔离该能力；E16 proof 只做 dry-run。

影响：合同可以合法、doctor 可以给出局部 ready，但真实 provider 调用仍缺凭据或选择错误 provider；“能力 >= 上游”不成立。

修复：建立唯一 backend execution adapter，从 run 中读取并校验 contract hash；显式解析 allowlist reference；安全映射 Atlas 字段；OAuth 使用用户明确批准的 auth-file reference；产生不含秘密的执行 receipt。

双向钢人论证：支持原判断的一方认为，backend contract 若只停留在 run metadata，doctor 的 ready 只是静态承诺，真实调用仍可能走错 provider、丢凭据或继承环境泄漏，必须由执行层消费并留下回执；反对一方最强的论点是，真实 provider 调用由宿主/worker 承担，runtime 强行代理所有凭据会扩大攻击面、降低宿主兼容性。双方分歧在于 contract 的责任边界是“声明”还是“可执行授权”；关键变量是是否能证明每次调用使用了冻结 contract、允许的 credential reference 和不含秘密的 receipt。产品选择后者，但把秘密解析限制在受控 execution adapter，不把秘密持久化或传给普通状态层。

状态：**已完成（执行 adapter、四类 provider 映射与回归证据）**。`backend_execution.py` 读取冻结 contract 并计算 contract hash，解析 `env:/host:/keychain:` 引用，映射 OpenAI/AtlasCloud 环境，消费 timeout/retry，并生成脱敏 execution receipt；`upstream_bridge.py` 将其注入隔离 vendor 进程，CLI 将 receipt hash 绑定到 run。未知/缺失凭据、非法 timeout/retry、未支持 provider 和 receipt 泄漏均 fail-closed；CLI 现将执行层错误转换为稳定机器协议。

证据：`tests/unit/test_backend_execution.py` 覆盖 OpenAI、AtlasCloud、缺失凭据和 host/keychain resolver 边界；`tests/integration/test_upstream_bridge.py` 验证真实 bridge 消费冻结 contract、返回 receipt 且不泄漏 secret，并覆盖固定命令树与 timeout；`tests/unit/test_reason_code_docs.py` 确认执行层 reason code 全量登记。

### P1-04：image 与 editable 均存在双状态真值

证据：

- `SKILL.md:86-100` 要求顶层 `image prepare/record/assemble`。
- `references/image-deck-workflow.md:15-25` 又要求上游 codex prepare/dispatch/result/status/assemble。
- 顶层写 `<run>/image-deck/slide_jobs.json`；vendor 写另一份 `slide_jobs.json` 与 `slide_run_state.json`；RunIndex 只观察顶层状态。
- editable 顶层写 `<run>/editable/page_jobs.json`，vendor 写 `<run>/editable/upstream/page_jobs.json`；公开帮助仍允许两套状态命令。
- image record 的 backend 可由调用参数填写，甚至默认 `fixture`，未校验 run 冻结的 backend contract。

影响：按任一官方说明执行都可能得到另一套状态看不见的成功、pending 或恢复状态；聊天、进度、finalize 和 provenance 无法形成唯一真值。

修复：只保留一个 canonical domain state。vendor 应成为无状态纯工具，或所有入口必须使用同一个 repository/transaction API；dispatch/record 同锁校验 backend contract 与 execution receipt。

双向钢人论证：支持原判断的一方认为，两套 `slide_jobs`/`page_jobs` 会造成状态漂移，任何“成功”都可能无法被顶层恢复、进度和交付读取；反对一方最强的论点是，保留 vendor 自己的状态能复用上游能力、降低适配成本，并允许高级用户直接操作 vendor CLI。真正分歧在于 vendor 状态是领域真值还是临时执行缓存；决定性变量是 vendor 状态是否会被顶层恢复、finalize 或用户教程当作事实来源。当前产品将 vendor 限定为隔离、无状态工具，所有可恢复状态只由顶层 adapter 持有。

状态：**已完成（canonical state 隔离与回归证据）**。image 的唯一状态是 `<run>/image-deck/slide_jobs.json`，editable 的唯一状态是 `<run>/editable/page_jobs.json`；editable normalize 后会删除 vendor `page_jobs.json`/`deck_run_state.json`，vendor 仅在临时隔离目录中执行格式转换。顶层 adapter、RunIndex、Lifecycle、finalize 和 worker lease 均读取同一份 domain state，并通过同一锁与 state hash 推进。

证据：`tests/integration/test_stable_workflow_commands.py::test_top_level_editable_prepare_uses_embedded_input_normalizer` 验证 vendor 状态被清理且 canonical page state 唯一；`tests/integration/test_run_lifecycle.py` 验证 image canonical state 的并发 finalize 与 revision；`tests/integration/test_upstream_bridge.py` 验证 vendor 命令树只能经固定 bridge 暴露，不能直接成为顶层状态源。

### P1-05：upgrade 没有已完成 image-deck 的基线导入合同

状态：**已完成（本地实现与回归证据）**。已新增 `upgrade inspect`、
`upgrade import-baseline` 和 baseline 重验证；full/selected upgrade 现在直接从
冻结 baseline 派生图片页，不依赖目标 run 手工 seed `image-deck`。baseline 的页序、
图片 hash、notes hash、尺寸、最终 PPTX hash 和 manifest fingerprint 任一漂移都会
fail closed。证据：
`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/upgrade/baseline.py`、
`tests/integration/test_upgrade_baseline.py`、
`tests/integration/test_stable_workflow_commands.py::test_upgrade_finalize_full_selected_and_explicit_partial`。

证据：

- `SKILL.md:117-135` 要求 inspect/freeze 已完成 image deck。
- CLI 只暴露 `upgrade finalize`，没有 inspect/import-baseline。
- 新 upgrade run 只复制原始输入与 backend，并创建空目录。
- selected finalize 从当前 run 的 image-deck 读取 artifacts；full 直接 finalize editable，完全绕过 image baseline。
- 现有成功测试通过直接实例化 adapter 手工搭状态。

影响：`upgrade-selected` 按公开旅程不可完成；`upgrade-full` 可能重建原输入而不是用户已批准的最终图片；source hash、页序、尺寸、notes 与原 image delivery 没有被绑定。

修复：新增 `upgrade inspect/import-baseline`，冻结原 image delivery 的页序、总页数、源/产物 hash、尺寸、notes、PPTX hash；full/selected 都必须从该 immutable baseline 派生。

### P1-06：partial-hybrid 确认由 CLI 自签

状态：**已完成（本地实现与回归证据）**。已新增 `upgrade propose` 两阶段合同；proposal
绑定 actor、时间、baseline fingerprint、selection、failure set 和 confirmation fingerprint；
`upgrade finalize` 必须提供与当前 proposal 完全匹配的确认，selection、失败集合或 baseline
发生漂移时返回 `partial_hybrid_proposal_stale`。证据：
`skills/leo-ppt-generator/runtime/src/leo_ppt_generator/cli.py`、
`tests/integration/test_stable_workflow_commands.py::test_upgrade_finalize_full_selected_and_explicit_partial`、
`tests/unit/test_reason_code_docs.py`。

证据：

- `cli.py:546-552` 只接受布尔 `--allow-partial`。
- `cli.py:1075-1090` 自行计算当前 failure fingerprint，并传回 assembler 满足确认检查。

影响：用户不需要看到或确认具体失败页集合；失败集合变化也没有旧确认失效的用户 receipt。

修复：分成 propose 和 confirm 两阶段。CLI 先输出冻结失败集合与 fingerprint，再要求用户确认 receipt 携带确认主体、时间和集合 hash；集合变化必须拒绝旧确认。

### P1-07：finalize 并发与 cancel 终态缺少统一 fence

状态：**已完成（本地实现与回归证据）**。run-level mutation lock、generation-bound
lease、cancel revoke、terminal mutation fence 和 binary temp+fsync+atomic rename 已接入
image/editable/hybrid 交付路径。并发 finalize 只产生一个 delivery revision；取消后旧
lease、迟到 record/finalize 均 fail closed。证据：
`application/run_index.py`、`storage.py`、
`tests/integration/test_run_lifecycle.py`、
`tests/integration/test_stable_workflow_commands.py::test_cancelled_run_rejects_late_image_record_and_finalize`、
`tests/boundary/test_atomic_state.py`。

证据：

- image、editable、hybrid finalizer 都在共享锁外读状态、分配 revision、写同一 PPTX 和 delivery。
- CLI 把 finalizer 标为 `safe_to_retry=true`。
- cancel 只修改 JSON 状态，不终止 worker，也不生成可拒绝迟到结果的 generation/lease token。
- record/finalize 不检查顶层 run 是否已经 cancelled。

影响：丢响应重试或两个 finalize 可双写同 revision；cancel 后迟到 worker 仍可 record/finalize，形成 `run=cancelled` 但新增 completed delivery，破坏终态、隐私和清理预期。

修复：run-level mutation/finalize lock、lifecycle generation、不可复用 lease token、cancel fencing；输出采用 temp + fsync + atomic rename，delivery/revision 同事务提交。

### P1-08：图片式 PPT 会静默压缩并拉伸

状态：**已完成（本地实现与结构回归证据）**。vendor assembly 已改为默认无损嵌入，
并提供显式 `contain`、`crop`、`stretch` 策略；默认保留源图比例，显式压缩才允许
lossy conversion。证据：`runtime/src/leo_ppt_generator/_vendor/codex_ppt/assemble_ppt.py`、
`tests/upstream/test_capability_behaviors.py::test_image_deck_assembly_preserves_source_ratio_by_default`。

证据：

- codex `assemble_ppt.py:123-199` 对大于 2MB 的图片转 JPEG，最低质量可降至约 20，并继续缩小尺寸。
- `assemble_ppt.py:242-283` 按固定 slide 比例双轴铺满，不保留源图比例。

影响：中文小字、图表、细线和透明背景可产生明显伪影；非 16:9 或近似 16:9 图片会变形；原图 hash 通过不能证明嵌入 PPTX 的最终视觉像素。

修复：默认无损；显式 contain/crop/letterbox 策略；最低像素与比例门；压缩后的实际嵌入图 hash、OCR/像素差异和整套重新渲染验收。

### P1-09：direct-editable 与 upgrade 丢失 speaker notes

状态：**已完成（本地实现与回归证据）**。notes 已从输入 normalization/baseline 经
prepare、record、PageArtifact、hybrid fingerprint 到最终 delivery summary 贯通，并
绑定 notes hash。证据：`tests/unit/test_adapters.py`、`tests/integration/test_upgrade_baseline.py`、
`tests/integration/test_stable_workflow_commands.py::test_image_prepare_record_and_assemble_replay_stable_flow`。

证据：

- 上游 normalization 能提取 notes manifest。
- 顶层 `_normalize_run_sources` 只返回页面 source path。
- `EditableAdapter.prepare` 不保存 notes；`editable record --notes` 默认空；finalize 只写 PageArtifact.notes。

影响：direct-editable 与 full upgrade 全部丢 notes；selected upgrade 只在被升级页面丢 notes，同一 deck 内出现断裂。

修复：notes 作为 baseline/page contract 的必需字段，携带 text hash；prepare、record、PageArtifact、finalize 和 delivery 全链路保留并复核。

### P1-10：没有安装后唯一 CLI 的完整四 route 成功测试

状态：**已完成（本地安装后黑盒证据）**。新增 release suite 在临时 venv 中安装
runtime，随后只使用绝对 `leo-ppt` 完成 `generate`、`direct-editable`、
`upgrade-full`、`upgrade-selected` 四条 route，并验证 image assemble replay；upgrade
均从真实 source delivery 导入 baseline，测试不 direct import adapter 或手写领域状态。
证据：`tests/release/test_installed_routes.py`，命令结果 `1 passed`。

证据：

- generate/direct-editable e2e 直接调用 registry、adapter 或 HybridAssembler。
- in-process CLI 测试手写输入、worker 结果或领域状态。
- upgrade-full 没有成功 happy path。
- upgrade-selected 成功测试直接 seed image/editable 私有状态。
- wheel test 只检查构建和 inventory，不安装 wheel 并从隔离 site-packages 走完整 route。

影响：现有绿色测试无法发现上述双状态、baseline、notes、partial、cancel 和远端安装问题。

修复：从 clean temp 与已安装 Skill/绝对 console script 启动，禁止 direct import adapter/RunIndex、禁止手写领域状态，四 route 各跑完整成功链、replay、失败保留和报告验证。

## 5. P2 质量与可靠性缺口

### P2-01：自定义风格只有 Agent 文字合同，没有行为证明

`references/style-library.md:12-16` 规定保存与优先读取，但没有 loader/CLI 或真实 Agent eval。当前不能断言完全不可用，但跨宿主的保存、重名确认、隐私过滤和下一 run 优先加载没有可重复证明。

状态：**已完成（本地实现、CLI 集成与回归证据）**。

双向钢人论证：支持原判断的一方指出，只有文字合同无法证明跨宿主持久化、重名处理、敏感信息拦截和下一次运行的优先级，因而不能把“Agent 知道规则”当作可交付能力；反对一方最强的论点是，风格本质上是提示词资产，过早增加状态存储会扩大隐私与迁移面，且纯文档合同在单宿主场景可能已经足够。双方真正分歧在于“风格是否属于需要稳定机器接口的用户资产”；决定性变量是是否要求跨 run、跨宿主复用以及是否允许用户提交不可信文本。当前产品定位要求可复用 Skill 和可观测交付，因此采用机器接口并以安全边界收敛复杂度。

已实施：新增用户/内置风格 store，用户风格覆盖同名内置风格；名称路径安全校验；空内容、不可读文件和敏感字段 fail-closed；重名必须显式 `--overwrite` 或 `--rename`；`style list/load/save` CLI 返回稳定 reason code、路径和 sha256。

证据：`tests/unit/test_styles.py` 覆盖优先级、持久化、敏感过滤、重名和路径校验，并通过 CLI `main()` 验证 save/load/list/conflict 的机器可观测结果；`tests/unit/test_reason_code_docs.py` 确认全部 style reason/success code 已登记。

### P2-02：vendor subprocess 缺顶层 timeout

状态：**已完成（本地实现与回归证据）**。bridge 已使用 process-group timeout，超时会
终止 POSIX child tree/Windows process group，并返回 `timed_out` 与稳定 reason code；
backend contract 的 timeout/retry 已传入执行上下文。证据：`upstream_bridge.py`、
`tests/integration/test_upstream_bridge.py::test_vendor_subprocess_timeout_is_observable_and_terminates_process`。

`upstream_bridge._run` 的 `subprocess.run` 没有 timeout；配置中的 backend timeout/retry 没有被该层消费。子进程卡死可让 run 永久不可观测地等待。

### P2-03：validation identity 和最终 summary 不完整

状态：**已完成（本地实现与回归证据）**。PageArtifact 绑定 `validation_sha256`，
delivery summary 返回逐页 validation refs、PPTX hash 和 claim ceiling；validation 文件
漂移会在 artifacts/finalize 前 fail closed。证据：`contracts.py`、
`tests/unit/test_adapters.py::test_editable_adapter_records_and_reverifies_domain_artifacts`。

PageArtifact 没有 `validation_sha256`，record 后 validation 文件可被替换；Editable finalize 不返回逐页 pages/validation refs，导致 direct-editable/upgrade-full 的最终 summary refs 为空。

### P2-04：视觉质量仍由 worker 自证

单独伪造 `validation.json: passed=true` 不能越过结构 validator，此原始候选已被驳回；但是 manifest 中四个 `quality_checks=true` 仍由同一 worker 填写，validator 没有 source-vs-preview 的独立渲染证据、字体/对比/遮挡/PowerPoint receipt 或人工验收。

双向钢人论证：支持原判断的一方指出，worker 同时产出 manifest 与 quality booleans，属于同一信源自证，无法证明遮挡、字体替换、对比度或 PowerPoint 实际打开效果；反对一方最强的论点是，独立渲染器、Office 和人工验收成本高且环境差异大，若把它们设成硬门会阻断离线用户。双方分歧在于“高质量声明”的证据上限，而非结构校验是否有价值；决定性变量是交付场景是否要求对视觉效果作强承诺，以及宿主是否具备独立 renderer/Office。最终采用分层且不可补偿的 gate：结构自动必过，视觉与人工按真实 receipt 分别推进。

状态：**已完成（独立证据机制与回归证据；现场结果仍按次验收）**。新增
`evidence visual`，要求独立 renderer/version、最终 PPTX hash、连续逐页 render
文件/hash 和 font/contrast/occlusion 结论；缺页、失败页、伪造路径或旧 PPTX hash
均 fail-closed。该 receipt 单独更新 `visual_render` gate，不再读取 worker 的
`quality_checks` 作为独立视觉结论。`evidence accept` 继续作为不可补偿的人工门。

证据：`evidence.py`、`tests/unit/test_evidence.py` 覆盖逐页 render identity、独立 gate、
PPTX 漂移和人工拒绝；当前环境没有 PowerPoint 与真实发布候选，报告仍必须保持对应
现场结果为 `not_run`，本地测试只证明机制而不冒充视觉成品已通过。

### P2-05：公式命令 fail-closed，但内容可被省略

TeX 命令失败会正确返回非零；真正缺口是系统没有 source-side expected formula inventory。worker 可在公式失败后从 manifest 省略该公式，结构 validator 无法判定数学内容缺失。

双向钢人论证：支持原判断的一方认为，公式渲染失败虽会阻断单次命令，但 worker 仍可通过不提交该 fragment 让整页结构校验通过，数学语义因此静默丢失；反对一方最强的论点是，图片/PDF 中公式识别本身有误报与漏报，强制 inventory 可能把不确定 OCR 结果误当成事实。真正分歧在于 expected inventory 的来源可信度；关键变量是输入是否有可抽取文本层、公式识别置信度以及用户是否确认低置信项。最终采用“已确认清单硬门、低置信人工确认、无清单不猜测”的分层方案。

状态：**已完成（确认清单门与缺失公式回归证据）**。manifest 新增可选的
`expected_formula_inventory`：只有 source-side 已确认的条目才进入硬门；低置信条目若未确认会被 validator 阻断。对每个 confirmed id，validator 必须在 worker
`formula_inventory` 中找到同 id，否则返回缺失违规；因此 worker 不能通过省略公式绕过结构校验。没有源侧可确认清单时，系统不把 OCR 猜测冒充真值，仍保持原有的人工确认上限。

证据：`validate_pptx.py::quality_contract_violations` 与
`tests/upstream/test_capability_behaviors.py::test_confirmed_source_formula_inventory_cannot_be_omitted` 覆盖“省略失败、补齐通过、低置信需确认”三种行为；`references/manifest-schema.md` 已补充字段合同。

### P2-06：hybrid replay fingerprint 漏掉 notes 等语义

状态：**已完成（本地实现与回归证据）**。hybrid fingerprint 已覆盖 source/artifact/
manifest/validation identity、notes、尺寸、页序、selection、failures 和 baseline identity，
并由 partial proposal drift 测试验证旧确认不可重放。证据：`hybrid/assembler.py`、
`tests/unit/test_hybrid_assembler.py`、`tests/integration/test_stable_workflow_commands.py`。

fingerprint 主要包含 artifact hash、selection 和 failures，未完整覆盖 notes、尺寸、source/manifest/validation identity。只改 notes 可能 replay 旧 PPTX。

### P2-07：provenance 与人工验收无法形成交付闭环

图片记录只有自由 backend 字符串、agent 与文件 hash，缺 model、endpoint、prompt/input/reference hash 和 provider receipt。人工视觉在报告中固定 `not_run`，没有与 PPTX hash、客户端版本、逐页结论绑定的 record/acceptance 命令。

双向钢人论证：支持原判断的一方认为，缺少最小 provenance 和 hash-bound 人工 receipt，无法回答“哪次 provider 调用生成了哪页”以及“谁用哪个客户端验收了哪个 PPTX”；反对一方最强的论点是，不同 provider receipt 形态差异大，强制统一可能泄漏秘密或制造沉重流程。真正分歧在于稳定核心字段与 provider 专有字段的边界；关键变量是能否只保存非敏感 identity。最终采用最小公共 schema，provider 专有回执只保存 id，不保存 token/header/body。

状态：**已完成（provenance/acceptance 命令与回归证据）**。新增
`evidence provenance`，绑定 page id、provider/model、endpoint origin、prompt/input/
reference/canonical artifact hash 和 provider receipt id；artifact hash 必须与 canonical
domain state 一致。新增 `evidence accept`，绑定最终 PPTX hash、reviewer、client/version
和连续逐页 accepted 决策。receipt 原子写、冲突拒绝、幂等 replay，并过滤疑似 secret。

证据：`tests/unit/test_evidence.py` 覆盖 provenance identity、秘密过滤、幂等、PPTX
漂移、逐页视觉与人工拒绝；`docs/user-guide.md` 和 `docs/testing.md` 已提供命令、字段和
证据上限。真实 provider/PowerPoint receipt 仍属于每次现场运行证据，不由 fixture 代替。

### P2-08：品牌视觉近似与 PowerPoint 模板语义未区分

系统可以把 logo、色值、字体近似为普通对象，但 builder 使用固定空白 master/theme，不能保留输入 PowerPoint 的主题、母版、版式和新建页继承语义。交付文案必须区分视觉重建与模板语义保留。

双向钢人论证：支持原判断的一方认为，把视觉近似说成模板保留会误导品牌用户，尤其会影响后续新建页、主题色和母版继承；反对一方最强的论点是，完整 OOXML 模板语义兼容成本高，且多数图片/PDF 输入根本没有可继承模板。真正分歧在于产品承诺边界；关键变量是输入是否为可信 PPTX、用户是否明确要求继承语义。当前将两者拆成不同能力：视觉重建/对象可编辑可交付，主题/母版/版式继承明确不支持。

状态：**已完成（声明边界与文档 gate 证据）**。`docs/limitations.md` 已明确固定基础 theme/master、视觉对象重建与模板语义不支持；交付文案不得把 logo/色值/字体近似描述为主题或母版保留。该项通过文档一致性审查完成，未对不具备证据的模板保留能力作扩张承诺。

## 6. 四条真实用户旅程

| Route | 当前机制 | 关键阻断 | 发布裁决 |
| --- | --- | --- | --- |
| `generate` | 安装后绝对 CLI 完整成功/replay；无损图片、notes、provenance/evidence gate | 真实 provider 与成品视觉按次验收 | 本地机制 GO |
| `direct-editable` | canonical state、对象构建、notes、validation identity 与独立 evidence | PowerPoint/人工逐页按次验收 | 本地机制 GO |
| `upgrade-full` | immutable image baseline、全量 editable 成功链与失败保留 | 真实输入复杂度与成品视觉按次验收 | 本地机制 GO |
| `upgrade-selected` | baseline、精确选择、两阶段 partial 确认与 hybrid fingerprint | partial 仍需用户确认，现场质量按次验收 | 本地机制 GO |

## 7. 行业对照

本轮只使用 Microsoft 官方 Copilot for PowerPoint 页面作为辅助基准，不把竞品营销文案当作本项目证据。

行业基本体验包括：询问受众与样式、先生成并可继续修改大纲和幻灯片、从组织模板开始、保留来源文件中的相关图片、对 AI 图片提供 provenance/notes，并要求人类复核。

本项目已经具备受众、大纲、视觉方向、样张、对象级重建、确认 receipt、AI 图片
provenance、notes、公式清单和 hash-bound 人工 review。当前与行业完整体验的边界是：

- 不承诺 PowerPoint 模板/母版/主题继承，只承诺视觉重建和对象可编辑。
- 真实 provider、OCR、PowerPoint 与人工视觉必须对具体交付按次验收。
- 当前只支持 Python 3.12.x/macOS arm64，本地交付尚未发布到远端 tag。

参考：<https://support.microsoft.com/en-us/office/create-a-new-presentation-with-copilot-in-powerpoint-3222ee03-f5a4-4d27-8642-9c387ab4854d>

## 8. Required Release Suite

以下门必须非补偿式全部通过：

1. Install：当前交付安装、唯一 Skill、双布局、`ensure installed -> reused`、四 route doctor、平台 lock 矩阵；远端发布后另做真实 origin/ref 验收。
2. Installed black-box routes：从安装后的绝对 `leo-ppt` 启动四 route 完整成功链；禁止直接 import adapter 和手写状态。
3. Canonical state：image/editable 只能有一个真值，vendor/top 的 dispatch、record、status、finalize 原子一致。
4. Upgrade integrity：immutable baseline、页序/尺寸/hash/notes、精确 partial fingerprint、full 成功、失败保留原 image delivery。
5. Terminal/concurrency：并发 finalize、cancel 后迟到结果、crash checkpoint、timeout 与 child-process tree、revision/idempotency。
6. Credential/provider：host/keychain、Atlas、Codex OAuth、OpenAI 的跨层 fake-server 测试；真实 provider receipt 单列。
7. Structural/visual：结构负向 fixture、validation/preview/validator identity hash、真实渲染、PowerPoint 打开、逐页人工验收 receipt。
8. Upstream/package regression：58 项逐能力、editable 82、U0、现有 169、静态检查、wheel inventory、许可证和 hash。

其中第 8 项通过不能补偿第 1-7 项失败。

## 9. 建议修复顺序

1. 先确定凭据/OAuth 安全模型，建立 backend execution adapter。
2. 统一 image/editable canonical state，并把 backend receipt 接入 dispatch/record。
3. 增加 upgrade baseline inspect/import 和 immutable baseline manifest。
4. 建立 run lifecycle lock、lease fencing、cancel 终态与 atomic finalize。
5. 修复图片无损/比例、notes 和 hybrid fingerprint。
6. 扩展 validation/evidence schema、逐页 refs、独立视觉与公式 evidence。
7. 固化 installed black-box 四路线；远端发布后增加 origin/ref 安装测试。
8. 修正文档兼容矩阵、模板语义、provenance 和人工验收声明。
9. 获得独立提交/发布授权后再发布固定 tag，并从真实远端重新执行安装验收。

## 10. 证据边界

已确认：

- 当前工作树本地测试 231/231 passed，覆盖率 87.14%。
- 60/60 capability mapping 逐项通过，对应 42 个唯一 proof case。
- editable 上游 82/82 通过。
- `sync_upstreams.py --check` 46 files passed。
- `third_party/` 不存在。

未确认且不能替代：

- 真实 OpenAI/Atlas 图片 provider。
- 在线 OCR。
- Microsoft PowerPoint 桌面。
- 最终 PPTX 的逐页人工视觉与演讲验收。
- 真实多页 worker 的完整行为。
- Windows/Linux、非 Python 3.12/macOS arm64。
- 从当前远端 revision 安装后的四 route 成功交付。

因此，当前正确的产品状态是“本地 Skill 发布候选与全部审查修复已完成；远端发布尚未执行，真实 provider、PowerPoint 和人工视觉按具体交付独立验收”。
