# Leo PPT Generator 20 轮多角色优化记录

## 五重审视

### 第一重审视：定义关键问题与领域

深层目标不是“把两个上游放进一个目录”，而是让首次用户只安装一个 Skill，就能从
意图确认走到可恢复、可验证且不夸大质量的 PPTX 交付。关键领域包括 Skill 产品设计、
PPT 内容与视觉质量、可靠性工程、开源发行和可证伪测试。边界是不修改两个上游仓库、
不新增通用 scheduler/数据库/安全平台、不把真实 provider 或人工视觉伪造成自动证据。

这一重改变了什么：完成标准从“功能存在”改为“用户可发现、入口可达、失败可恢复、
交付可验证、声明不越界”的完整闭环。

### 第二重审视：理论体系与判断主轴

- Nielsen 可用性原则用于判断安装、状态可见性、错误预防、用户控制和恢复动作。
- 渐进披露与 Skill Creator 合同用于判断 `SKILL.md`、条件 reference 和确定性脚本的
  信息分层，避免入口文件吞入全部细节。
- SRE 的故障域、幂等、可观测性和恢复用于判断 runtime、run、worker、provider 和
  finalizer 是否隔离，失败是否有稳定动作。
- 科学方法的可证伪与复现用于判断 capability proof、离线 fixture、现场 receipt 和
  claim ceiling，禁止以文件存在或绿色聚合数代替逐项事实。
- PPT 叙事与信息设计以单页单任务、视觉层级、数据真值和非补偿质量门为主轴，禁止
  用视觉效果补偿事实、结构或可编辑性失败。

这一重改变了什么：20 个角色不再平权堆意见，而是统一沿“用户任务、非补偿质量、
故障可恢复、证据可复现”四条主轴判断。

### 第三重审视：关键事实与综合模型

当前树有 60 条能力映射（42 个唯一 proof case）、43 个上游 Python 文件映射、四条有限 route、一个 Skill、
一个 CLI、不可变 runtime identity、versioned run/PageArtifact/Delivery、16 个 Skill
正反向场景和分层现场限制。U10 已逐条运行 60 个 proof 映射；U11 已在两种临时发现布局
完成 `installed → reused`、`--version` 和四 route doctor。

综合模型是：顶层 Agent 负责意图、确认、宿主能力与交付判断；`leo-ppt` 负责确定性
输入冻结、状态、验证、恢复和组装；固定 vendor 只通过 adapter/bridge 暴露；所有完成
声明必须同时经过内容事实、叙事、视觉、PPTX 结构和现场验收五层非补偿门。

这一重改变了什么：优化优先级从新增功能转为关闭“安装断链、弱 proof、错误恢复、
伪可编辑和证据越界”这些会直接破坏交付可信度的缺口。

### 第四重审视：最强反方与前提压力

最强反方是：20 轮角色审查容易成为事后包装；大量 fixture 即使全绿，也不能证明
真实图片质量、在线 OCR、PowerPoint 桌面或人工审美。该反方成立，因此每轮必须有
唯一缺口或明确不修改理由，并绑定当前源码/测试；现场能力保持 `not-run`，不能被
60/60 mappings、coverage 或 doctor `ready` 补偿。

另一反方是：为覆盖所有角色不断增加规则会使 Skill 过长、互相冲突。该前提同样成立，
因此重复要求回到 canonical reference，不在 `SKILL.md`、README、教程和多个 prompt
中复制同一合同。

这一重改变了什么：淘汰“每轮强行改代码”和“全绿即高质量 PPT”两种方案，保留
最小改动、直接 proof、显式限制和最终树重验。

### 第五重审视：全貌与可验证收束

最终系统应表现为：用户选择一种安装机制，runtime 从 Skill 自身定位并自检；Agent
选择唯一 route、完成必要确认、派发真实 worker；CLI 用 versioned 状态推进；失败时
保留已完成产物并给出一项安全动作；交付时准确声明 image/editable/hybrid 类型及
未运行证据。成功信号是最终树的测试、Wheel、clean install、四 route、58 proof、
review 和 fingerprint 同源；失败信号是任一 required gate 失败或现场项被越界声明。

这一重改变了什么：20 轮改进必须进入最终验证矩阵，最后一轮不能靠文档自证完成。

## 逐轮记录

### 第 1 轮：首次安装用户

- **目标：** 不理解两个上游也能只安装一个 Skill。
- **当前证据：** bundle 只有一个 `SKILL.md`，两个上游已固定内嵌。
- **冲突/缺口：** README 原先只写未发布的远端安装路径，且漏掉 `$HOME/.agents/skills`。
- **需求或不修改理由：** 两种发现机制必须分开说明，且禁止同时安装两份。
- **实现：** README/教程改为当前交付目录到 Codex/Agent 两种发现目录的真实安装路径，并补充同名冲突与重发现条件；远端发布前不提供死链接。
- **验证：** `tests/release/test_release_docs.py`；两种临时布局使用同一 bundle。

### 第 2 轮：低技术用户

- **目标：** 首次运行能知道缺什么、什么不需要立刻修。
- **当前证据：** doctor 已分离 runtime、config、credential、worker、provider、viewer、人工验收。
- **冲突/缺口：** 顶层 `ready` 容易被误读为所有外部能力已通过。
- **需求或不修改理由：** 教程必须解释每个 `readiness` 字段和动作。
- **实现：** 新增 readiness 解读表；保留稳定 reason code 和 `not_probed|required`。
- **验证：** 四 route doctor 均返回分层结构，不回显 secret。

### 第 3 轮：熟练用户

- **目标：** 从任意项目目录调用，不依赖 cwd 或旧 PATH。
- **当前证据：** `SKILL_DIR` 来自宿主提供的当前 Skill 绝对路径。
- **冲突/缺口：** 旧文档和 prompt 曾存在仓库相对或旧 CLI 入口，现已移除。
- **需求或不修改理由：** 不再增加 wrapper；现有 runtime manager 已拥有定位职责。
- **实现：** 保持 `ensure|doctor|print-cli` 三个入口和唯一 `leo-ppt`。
- **验证：** 两种临时安装布局均从 unrelated cwd 成功，第二次 ensure 为 `reused`。

### 第 4 轮：产品经理

- **目标：** 在生成、直转、全量升级和指定页升级中选对 route。
- **当前证据：** `application/routes.py` 只有四条 code-owned route，未知值 fail closed。
- **冲突/缺口：** 混合输入若只看文件类型可能静默选错目标。
- **需求或不修改理由：** route 由用户目标和输入共同决定；现有合同已覆盖，不新增第五条 route。
- **实现：** 保持 `input-routing.md` 的最小确认集和 schema enum。
- **验证：** route 单测、CLI protocol 和 16 个 Skill case。

### 第 5 轮：演讲者

- **目标：** PPT 服务于受众、现场时长和行动目标。
- **当前证据：** 图片工作流先冻结受众、场景、时长、行动目标与 notes。
- **冲突/缺口：** 单纯按页数生成会造成内容密度与讲述时间失配。
- **需求或不修改理由：** 现有内容合同已直接覆盖，不重复到 runtime schema。
- **实现：** 保持逐页预计用时和总时长相容要求。
- **验证：** `audience-duration-contract` 反向 Skill case。

### 第 6 轮：内容编辑

- **目标：** 主线完整、页面不重复、每页只有一个可复述任务。
- **当前证据：** 大纲确认后才进入完整逐页稿，每页记录角色、结论与衔接。
- **冲突/缺口：** 自动 schema 不能判断叙事是否真正有意义。
- **需求或不修改理由：** 不伪造确定性“叙事评分”；保留 Agent 判断与人工确认。
- **实现：** 现有单页单任务和五层门不修改。
- **验证：** `one-page-one-task` case；最终叙事层 receipt 独立记录。

### 第 7 轮：事实编辑

- **目标：** 数字、名称、引用和因果关系可追溯。
- **当前证据：** 来源不足项必须标记 `unknown`，不可为了页面完整补写。
- **冲突/缺口：** 视觉模型可能生成看似可信但不存在的数据或文字。
- **需求或不修改理由：** 内容事实是第一层非补偿门，失败直接阻断。
- **实现：** 保持事实来源、不可杜撰项和图表真值合同。
- **验证：** `facts-must-be-sourced` 与 `editable-chart-truth` case。

### 第 8 轮：PPT 专家

- **目标：** 页面角色、视觉焦点、阅读顺序和信息密度清楚。
- **当前证据：** 逐页稿显式区分开场、问题、证据、解释、方案、行动和收束。
- **冲突/缺口：** 统一模板可能稳定但机械，任意布局又会失去层级。
- **需求或不修改理由：** 固定视觉 DNA，按页面语义改变布局；不增加硬编码模板引擎。
- **实现：** 复用样张确认、style brief 和单页任务合同。
- **验证：** 样张继承和 backend fingerprint 流程；人工视觉仍为现场门。

### 第 9 轮：视觉设计师

- **目标：** 整套统一但不模板化。
- **当前证据：** 12 套 exact style brief 和用户风格优先级已集成。
- **冲突/缺口：** 只保存风格名称会丢失可执行视觉 DNA。
- **需求或不修改理由：** 必须写入完整 style brief；自定义风格不能污染 Skill 安装目录。
- **实现：** 风格保存到 `${LEO_PPT_HOME}/styles`，同名先确认覆盖/合并/改名。
- **验证：** 12/12 exact hash 与专用风格合同测试。

### 第 10 轮：图片编辑

- **目标：** 素材真实、清晰、忠于输入且 provenance 完整。
- **当前证据：** required asset、严格参考图、import hash、asset sheet 去背拆分均有 owner。
- **冲突/缺口：** 入口可见性曾被错误当成 provider/编辑行为证明。
- **需求或不修改理由：** provider 协议、批量、多参考图、去背、import 和拆分分别做 fixture。
- **实现：** 新增 `test_capability_behaviors.py` 的直接行为测试。
- **验证：** C16–C20、E16–E18 对应 proof 逐项通过；真实 provider 仍 `not-run`。

### 第 11 轮：数据表达专家

- **目标：** 图表准确而非装饰。
- **当前证据：** 两种工作流都要求数值、单位、标签、图例、排序和来源一致。
- **冲突/缺口：** 视觉完整性可能诱导补造缺失单位或趋势。
- **需求或不修改理由：** 无来源即失败，不生成“看起来合理”的数据。
- **实现：** 现有图表真值门保持 canonical，不重复到 prompt 外层。
- **验证：** `editable-chart-truth` case 和每页 validation 合同。

### 第 12 轮：无障碍审阅者

- **目标：** 投屏可读，状态与风险不只靠颜色表达。
- **当前证据：** 已有字号、对比、overflow、遮挡和字体替代检查。
- **冲突/缺口：** 原合同未明确色觉替代线索与投屏距离。
- **需求或不修改理由：** 两种交付模式都必须提供颜色之外的第二种线索。
- **实现：** 图片式和可编辑 reference 新增文字/标签/形状/线型/位置要求。
- **验证：** `test_both_delivery_modes_require_non_color_accessibility_cues`。

### 第 13 轮：可编辑交付用户

- **目标：** “可编辑”是对象级能力，不是整页截图叠字。
- **当前证据：** manifest、PageArtifact、full-slide-raster-overlay 禁止项和结构验证已存在。
- **冲突/缺口：** 能打开的 PPTX 可能仍是伪可编辑。
- **需求或不修改理由：** editable 必须通过对象、文字、notes、页序和页面模式门。
- **实现：** 保持整页栅格禁止和字体替代后重新测量。
- **验证：** `raster-overlay-is-not-editable`、adapter 和 direct-editable e2e。

### 第 14 轮：可靠性工程师

- **目标：** 中断、重放、并发和升级失败不重复付费、不破坏旧交付。
- **当前证据：** revision、operation id、state hash、safe-to-retry、原子写和锁均已实现。
- **冲突/缺口：** 旧 mutation 入口曾缺少完整四元返回，U9 已补齐。
- **需求或不修改理由：** 所有公开 mutation 保持统一协议，不增加第二状态机。
- **实现：** run/delivery/upgrade mutation 都返回幂等四元合同。
- **验证：** 8 crash checkpoint、并发 winner、6 replay/conflict 与失败升级保留测试。

### 第 15 轮：可观测性负责人

- **目标：** 出错后能定位 stage/page/operation、耗时与下一安全动作。
- **当前证据：** events、timing、diagnose、worker/backend duration 和 reason code 已分层。
- **冲突/缺口：** 损坏或缺失 `run.json`/`timing.json` 不能让诊断本身崩溃或改证据。
- **需求或不修改理由：** diagnose 只读并给一个优先动作。
- **实现：** U9 增加缺失索引、输入 hash 漂移和 timing 损坏诊断。
- **验证：** `tests/integration/test_run_lifecycle.py` 六类只读诊断。

### 第 16 轮：安全与隐私负责人

- **目标：** 凭据和用户内容按最小必要范围传递、记录与保留。
- **当前证据：** backend 只允许 credential reference；日志使用 allowlist/redaction。
- **冲突/缺口：** 用户教程原先没有集中说明网络上传、保留和清理边界。
- **需求或不修改理由：** 文档必须区分 task-local 上传、日志、默认保留和不可恢复清理。
- **实现：** 教程新增隐私与数据边界；未知敏感配置 fail closed。
- **验证：** credential rejection、events redaction、release docs 与 cleanup fingerprint 测试。

### 第 17 轮：测试负责人

- **目标：** 逐功能证明，不能抽查或只看文件存在。
- **当前证据：** 60 条 capability 映射都有 integration、proof 和精确 pytest node id，共 42 个唯一 proof case。
- **冲突/缺口：** 多个相邻能力仍会复用同一场景，映射数不能表述为独立 Judge 数。
- **需求或不修改理由：** collection 必须核对 node，弱项补行为 fixture，再逐条独立运行。
- **实现：** inventory 增加强制路径一致与 collection；新增 20 条行为 proof 绑定。
- **验证：** 60/60 按账本顺序通过，42 个唯一 proof case，Skill eval 为 16 个正反向 case。

### 第 18 轮：发布负责人

- **目标：** 发布包可重复构建、安装，且不带历史垃圾或旧入口。
- **当前证据：** runtime pyproject、平台 lock、identity、vendor lock 和 runtime manager 已存在。
- **冲突/缺口：** 源树残留 build、egg-info、`__pycache__` 和 `.pyc`。
- **需求或不修改理由：** 构建从 clean copy 进行，Wheel inventory 和源码树 cleanliness 都是门。
- **实现：** 新增 Wheel release test并清理生成物；`third_party/` 保持不存在。
- **验证：** Wheel 含 schema/vendor 与唯一 `leo-ppt`，不含 Skill、旧 CLI、缓存或 build。

### 第 19 轮：开源维护者

- **目标：** 用户理解许可证、兼容性、升级和限制。
- **当前证据：** 根 LICENSE 与 Skill LICENSE byte-identical，runtime metadata 为 MIT。
- **冲突/缺口：** 用户要求 README 不出现内部交付导航，同时仍需完整用户说明。
- **需求或不修改理由：** README 只保留产品、安装、配置、使用、验证和 MIT；详细操作进教程。
- **实现：** 补升级/卸载/兼容/隐私，保留两份上游 notice 在 bundle 内但不做 README 导航。
- **验证：** MIT parity、链接、禁止短语和 release docs 测试。

### 第 20 轮：最终验收人

- **目标：** 最终树能诚实交付高质量 Skill，并为真实 PPT 交付提供完整闭环。
- **当前证据：** 五层非补偿质量门、四 route、58 proof、clean install 与 claim ceiling 已建立。
- **冲突/缺口：** 中间树的绿色结果不能作为最终树证据；真实 provider/桌面/人工视觉尚无 receipt。
- **需求或不修改理由：** 完成前必须在 review 修复后重新执行所有 required gate 并生成 fingerprint。
- **实现：** 最终验证报告分开自动机制、外部现场和未运行项；任何 required 失败都阻止完成。
- **验证：** 最终候选树 231/231、覆盖率 87.14%、60/60 capability mappings（42 个唯一 proof case）、U0 7/7、editable 82/82、安装后四 route、双安装各 `installed → reused` 与四 route doctor 已通过；完整文件账本审查发现的问题均已逐项修复。现场缺失保持 `not-run`。

## 本轮综合结论

20 轮没有产生新的架构或 provider 边界。实际增量集中在：双安装机制、readiness 解读、
20 条弱能力行为 proof、无障碍第二线索、隐私/升级/卸载文档、Wheel inventory 和源码
清洁门。其余角色确认现有 canonical owner 已覆盖，避免重复规则扩大 Skill 上下文。
最终完成声明仍由 review 后的最终树门禁决定，本文件不替代最终验证报告。
