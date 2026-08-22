<!-- spec-first:lang:start -->
## 语言与治理策略
**语言设置：** `Chinese / 中文`
语言规则为绝对硬执行要求：除非用户在当前请求中明确要求其他语言、翻译、双语输出或保留原文，所有面向用户的新生成自然语言内容必须使用简体中文。
适用范围覆盖回答、状态更新、澄清问题、总结、评审、生成文档、需求、计划、任务、变更说明、commit message 和 PR 文案。
代码标识符、命令、路径、配置键、环境变量、API 名称、协议名、日志、工具输出和引用材料可以保留原文；围绕它们新增的解释、结论和说明仍按本语言设置输出。
skill、agent、模板、历史上下文或示例文本的原文语言不得覆盖本设置；新增代码注释也按本设置，只说明非显然意图。
### Workflow 入口治理
<!-- spec-first:workflow-entry:using-spec-first -->
- 在执行实质性工作前，加载当前宿主已安装的 `using-spec-first` skill；完整入口路由与边界由该 skill 提供。
<!-- spec-first:lang:end -->

## graphify

本项目在 Graphify 原生默认目录 `graphify-out/` 中维护 knowledge graph，包含 god node、community structure 与跨文件关系。

当用户输入 `/graphify` 时，先调用 `skill` 工具并设置 `skill: "graphify"`，再执行其他操作。

规则：
- 当 `graphify-out/graph.json` 存在且 runtime 可见 Graphify CLI 时，将 Graphify 用作 architecture relationship、impact analysis 与宽范围 codebase navigation 的 exploration-tier 定向工具。Graphify 候选可以决定下一步检查位置，直接读源码始终合法。优先解析 `PATH` 中的 `graphify`，也可使用 `$HOME/.local/bin/graphify`（Windows 为 `.exe`/`.cmd`）。使用 Provider 原生命令：`graphify query "<question>"` 做宽范围定向，`graphify path "<A>" "<B>"` 查看关系，`graphify explain "<concept>"` 聚焦概念。
- 简单事实问答、当前上下文总结、用户提供的单文档工作或已限定范围的文件读取，默认不使用 Graphify；直接回答、使用 `rg` 或 bounded source read。
- 如果 `graphify-out/graph.json` 存在但 Graphify CLI 不可见，不得把 artifact 当作 runtime readiness。改用 bounded direct source read，并将 `spec-runtime-setup --only graphify` 作为修复路径。
- Hook 或 incremental update 后 `graphify-out/` 出现 dirty 文件属于预期现象，不能仅因此跳过 Graphify。只有任务本身涉及 stale/incorrect graph，或用户明确禁用时才跳过。
- 如果 `graphify-out/wiki/index.md` 存在，用它进行宽范围导航。仅在 query/path/explain 未提供足够上下文时，才读取 `graphify-out/GRAPH_REPORT.md`。
- `.graphify/` 是 spec-first 旧版适配目录，只作 migration evidence；运行 `spec-runtime-setup --only graphify` 将其原子迁移为唯一 current artifact `graphify-out/`。如果两个 root 同时存在，必须先解决冲突，禁止静默选择。
- 将 Graphify/code-graph 输出视为 `provider_untrusted` advisory navigation；重要结论必须由 source、test、log、contract 或 owner evidence 确认。
- 普通 workflow 不会在代码变更后刷新 project graph。按 `docs/contracts/project-graph-consumption.md` 将 freshness 作为 setup/readiness advisory；需要显式刷新时运行 `spec-runtime-setup --only graphify --refresh`。
