# Requirements Document

## Introduction

安装成功不等于图片生成能力已经可用。Leo PPT Generator Skill 安装后会在 Codex、Claude、Kiro 等 Agent 宿主中执行；这些宿主可能没有可交互 TTY，也不应接触用户的明文 API Key。当前底层已经具备凭据存储、Provider 档案和 setup 检查能力，但普通用户仍需自行拼接多条命令，安装器、CLI 与宿主对“已安装”“已配置”“真实可用”的表达也没有形成统一合同。

本功能新增统一的 `leo-ppt config` 用户入口，将 Provider 选择、凭据录入、非敏感档案配置、本地校验、可选真实图片接口验证和故障修复编排为一条引导流程。凭据录入不以交互终端为硬性前提，而是支持多通道：优先隐藏式交互输入，同时接受既有环境变量引用与用户显式选择的 stdin 通道，唯一被禁止的是以明文命令行参数传入密钥。安装或更新完成后必须检查配置状态：存在交互终端时默认进入首次配置引导（用户可明确推迟）；不存在交互终端时不视为失败，而是提示可用的非交互通道或稍后在终端执行的准确命令。本地配置完整后即允许开始任务，状态为 `configured_unverified`；只有显式付费 smoke 或真实业务图片成功并持久化当前 readiness scope 所需的 Capability_Evidence 后，该 scope 才升级为 `ready`。配置失败或被推迟不得回滚已经成功激活的 Skill，系统必须分别报告安装、配置、验证和执行资格，不得把“未验证”误报为“不可执行”。

当前版本以终端为配置主通道，不提供 localhost 配置服务、自动打开浏览器或网页密钥录入。浏览器配置只作为二期可选增强候选，需另行完成需求、威胁模型与验证方案后决策，不得成为当前安装、配置、宿主守卫或任务恢复流程的依赖。

进入 Agent 宿主后，Skill 在首次执行任务前再次检查状态。若宿主自身图片能力可用，则由宿主现场验证；若 External_Provider 为 `configured_unverified`，Agent 允许进入图片节点，并将首张真实业务图片作为惰性验证；只有配置缺失或无效时才暂停并给出终端配置命令。Agent 不能读取、转发或代填密钥；用户完成修复后必须复查并从中断点恢复原 PPT 任务，不要求用户重新提交材料。

本功能覆盖 macOS arm64 的 Keychain 和 Windows x64 的当前用户 DPAPI 存储，支持 OpenAI、OpenAI-compatible 中转站、AtlasCloud 和宿主内置图片能力。项目尚未对外发布，当前开发期配置格式和底层命令不构成向下兼容承诺。

## Glossary

- **Config_Command**: 面向普通用户的统一配置命令组，包括 `leo-ppt config`、`leo-ppt config status`、`leo-ppt config verify`、`leo-ppt config repair` 和 `leo-ppt config change`。
- **Config_Wizard**: 运行 `leo-ppt config` 时启动的交互式配置向导。
- **Install_Transaction**: 下载、runtime 准备、route doctor 和 Skill 原子激活组成的安装事务，不包含外部 Provider 的真实可用性承诺。
- **Post_Activation_Onboarding**: Install_Transaction 成功后执行的配置状态检查、首次配置引导与结果提示。
- **Host_Readiness_Guard**: Skill 在 Codex、Claude、Kiro 等宿主开始 PPT 任务前执行的就绪检查与恢复流程。
- **Provider**: 图片服务来源，取值 `openai`、`openai-compatible`、`atlascloud` 或 `builtin-imagegen`。
- **External_Provider**: 需要 Leo PPT runtime 自行调用和验证的 Provider，包括 `openai`、`openai-compatible` 与 `atlascloud`。
- **Host_Provider**: 只能在 Agent 宿主现场确认能力的 `builtin-imagegen`。
- **Route**: PPT 交付流程，取值 `generate`、`direct-editable`、`upgrade-full` 或 `upgrade-selected`。
- **Credential_Store**: 平台凭据存储；macOS 使用 Keychain，Windows 使用当前用户 DPAPI 文件。
- **Credential_Reference**: 指向 Credential_Store 或既有环境变量的非敏感引用，不包含密钥明文。
- **Provider_Profile**: Provider 的非敏感连接档案；OpenAI-compatible 至少包含 `endpoint_origin` 与 `model`。
- **Config_File**: `LEO_PPT_HOME` 下的 `config.yaml`，仅保存 schema 版本和非敏感配置；首次正式发布的目标格式为 schema v1，平台路径、字段约束和凭据边界见 [`config-file.md`](./config-file.md)。
- **LEO_PPT_HOME**: 独立于 Skill 安装目录的 runtime 配置根目录，用于跨重装和升级保留配置。
- **CLI_Path**: 当前受管 runtime 中 `leo-ppt` 可执行文件的绝对路径，由安装器或 runtime manager 解析。
- **Local_Configuration_Check**: 不调用外部接口，仅检查 Provider_Profile、Credential_Reference、配置 schema 和 route/provider 兼容性的本地检查。
- **Auth_Probe**: 仅在 Provider registry 明确声明无费用且无实质副作用时，向目标 Provider 发起的鉴权检查（如模型列表或账户查询）；它只能尽早发现部分鉴权或模型错误，不能证明图片生成能力。
- **Provider_Smoke**: 向 External_Provider 发起一次最小真实图片生成请求并校验产物的显式验证；v1 只验证 `generate`，不得据此证明 `edit`、`mask` 或 `reference`。
- **Provider_Registry**: runtime 拥有的静态 Provider 能力与验证策略真值，声明 Provider/adapter 的能力、免费且无实质副作用的探测、模型发现、幂等、重试和 receipt 有效期策略；未声明的能力或策略一律按 `unknown` 处理。
- **Route_Capability_Matrix**: checked-in runtime source 中由 Route owner 维护的 Route 基础能力真值；v1 中 `generate` 需要 `generate`，`direct-editable`、`upgrade-full` 与 `upgrade-selected` 需要 `edit`，实际任务使用 mask 或额外参考图时再分别增加 `mask` 或 `reference`。
- **Default_Route**: 用户或安装器未指定 Route 时用于状态显示和显式 smoke 的稳定默认 Route，v1 固定为 `generate`，且必须在输出的 `readiness_scope.route` 中可见。
- **Verification_Policy**: Provider_Registry 中约束一次真实验证如何授权、校验、重试、过期和恢复的版本化策略；v1 默认 TTL 为每项能力成功后的 7 天，Registry 可按 Provider/能力显式覆盖。
- **Paid_Verification_Consent**: 用户对当前一次独立 Provider_Smoke 的肯定授权；交互提示默认值必须为“否”，非交互模式仅以显式 `config verify` 或 `--verify` 表达授权，不能持久化为未来调用的默认同意。
- **Verification_Fingerprint**: 用于标识 Provider 基础配置身份的非敏感组合，至少覆盖 Provider、endpoint、model、凭据版本、runtime adapter 版本和验证策略版本；它不包含验证结果或已验证能力。
- **Capability_Evidence**: Verification_Receipt 中按能力独立保存的成功证据，至少记录 capability、验证时间、过期时间、operation id、验证来源和产物摘要；每项能力独立过期。
- **Verification_Receipt**: Provider_Smoke 或真实业务图片成功后写入 `LEO_PPT_HOME` 的非敏感 Provider 回执，保存 Verification_Fingerprint 与一个或多个 Capability_Evidence；新增能力证据不得覆盖仍有效的其他能力证据。
- **Configuration_State**: 本地配置状态，取值 `not_configured`、`locally_configured` 或 `invalid`。
- **Verification_State**: 真实验证状态，取值 `not_run`、`passed`、`failed` 或 `stale`。
- **Config_Status**: 面向用户和自动化的聚合状态，按明确优先级归并为 `not_configured`、`configured_unverified`、`ready`、`degraded` 或 `invalid`。
- **Execution_Eligibility**: 当前目标 Route 的执行资格，取值 `allowed`、`retryable` 或 `blocked`；它与是否已有真实验证证据分开判断。
- **Installation_Readiness**: 安装后的整体可用性，取值 `ready`、`usable_unverified` 或 `installed_not_ready`。
- **Verification_Scope**: 一次真实验证意图的协调作用域，由 Verification_Fingerprint 与规范化后的目标能力集合组成；一个能力的成功不得自动验证其他能力。
- **Host_Capability_State**: 当前宿主现场声明的 Host_Provider 能力状态，取值 `unknown`、`available` 或 `unavailable`；它不写入 External_Provider 的 Verification_State 或 Verification_Receipt。
- **Reason_Code**: 稳定的机器可读原因码，用于标识状态、失败原因与恢复路径。
- **Primary_Action**: 当前状态下唯一推荐给普通用户的下一步操作；无动作时为 `null`，非空时 `kind` 只能是 `run_cli`、`start_task`、`resume_task`、`wait_and_retry` 或 `confirm_new_request`，且只有 `run_cli` 包含可直接执行的 `command`。
- **TTY**: 可安全进行隐藏式交互输入的真实终端；它只是凭据录入通道之一，并非完成配置的必要条件。
- **Credential_Input_Channel**: 可接受的密钥录入通道，包括交互终端的隐藏输入、既有环境变量引用、用户显式选择的 stdin（如 `--key-stdin`）；明文命令行参数不属于可接受通道。

## Requirements

### Requirement 1: 统一配置入口

**User Story:** 作为普通用户，我想通过一个统一命令完成图片服务配置和验证，这样我不必理解多条底层命令的组合关系。

#### Acceptance Criteria

1. THE Config_Command SHALL 将 `leo-ppt config` 作为普通用户的唯一推荐配置入口。
2. THE Config_Command SHALL 提供 `status`、`verify`、`repair` 与 `change` 子命令，分别用于只读检查、真实验证、按当前故障恢复和主动切换 Provider 或档案。
3. WHEN 用户在交互终端中运行 `leo-ppt config` 且未指定 Provider, THE Config_Wizard SHALL 展示 OpenAI、OpenAI-compatible 中转站、AtlasCloud 和退出选项。
4. WHEN 用户选定 External_Provider, THE Config_Wizard SHALL 按需完成凭据录入、Provider_Profile 配置和 Local_Configuration_Check，并仅在用户明确同意可能计费的验证时执行 Provider_Smoke。
5. THE Config_Command SHALL 优先复用现有 auth、provider、setup 和 backend 的有效内部能力；THE 功能 SHALL NOT 为尚未发布的底层命令建立公共兼容承诺，且 MAY 在统一入口形成后删除或收敛重复入口。
6. THE Config_Command SHALL NOT 复制或另建与现有凭据、Provider_Profile、setup 或 backend 合同冲突的第二套真值。
7. WHERE 目标 Provider 的凭据已可用（既有环境变量引用或平台存储）或当前宿主已现场确认 Host_Provider, THE Config_Wizard SHALL 跳过 Provider 选择与非必要提问，直接执行 Local_Configuration_Check 并给出结果（零提问 happy path）。

### Requirement 2: 状态模型与机器可读合同

**User Story:** 作为用户或 Agent，我想准确区分已安装、已配置和真实可用，这样不会在缺少图片服务时误以为系统已经就绪。

#### Acceptance Criteria

1. THE Config_Command SHALL 单独报告 Configuration_State、Verification_State 和聚合 Config_Status，不得用一个字段混合“本地配置完整”和“真实验证通过”。
2. THE Configuration_State SHALL 以 `not_configured` 表示目标 Route 所需凭据或 Provider_Profile 缺失，以 `locally_configured` 表示本地配置完整，以 `invalid` 表示本地配置不可解释或违反合同。
3. THE Verification_State SHALL 针对当前 `readiness_scope` 计算：`passed` 表示全部 required capabilities 均有匹配且有效的 Capability_Evidence；`failed` 表示当前真实验证操作失败；`stale` 表示至少一项 required capability 的既有证据已过期或 fingerprint 变化；`not_run` 表示其余尚未获得完整目标能力证据的情况。
4. THE Config_Status SHALL 以 `not_configured` 表示 Configuration_State 不完整且 Host_Provider 尚未在宿主现场确认。
5. THE Config_Status SHALL 以 `configured_unverified` 表示 Configuration_State 为 `locally_configured` 但当前 readiness scope 的 required capabilities 尚未被有效 Capability_Evidence 完整覆盖，且 SHALL 允许进入目标 Route 的图片节点。
6. THE Config_Status SHALL 仅在当前 readiness scope 的 required capabilities 已被有效 Capability_Evidence 完整覆盖，或 Host_Provider 已被当前宿主确认覆盖目标能力时返回 `ready`。
7. THE Config_Status SHALL 以 `degraded` 表示本地配置有效但外部服务暂时失败、限流或超时，且存在可执行的重试或切换路径。
8. THE Config_Status SHALL 以 `invalid` 表示配置 schema、Provider_Profile、凭据引用或兼容性存在必须修复的错误，并 SHALL 使 `invalid` 优先于其他聚合状态。
9. THE Execution_Eligibility SHALL 将 `ready` 与 `configured_unverified` 映射为 `allowed`，将可重试的 `degraded` 映射为 `retryable`，并将 `not_configured` 与 `invalid` 映射为 `blocked`。
10. THE Installation_Readiness SHALL 将 `ready` 映射为 `ready`，将 `configured_unverified` 映射为 `usable_unverified`，并仅将执行资格为 `blocked` 或 `retryable` 的结果映射为 `installed_not_ready`。
11. WHEN 用户请求 JSON 输出, THE Config_Command SHALL 返回协议 `leo-ppt-config/v1`，至少包含 `status`、`configuration_state`、`verification.status`、`execution_eligibility`、`installation_readiness`、`readiness_scope`、`reason_code`、`selected_provider`、Provider 列表、evidence refs 和可为 `null` 的 `primary_action`。
12. WHEN `primary_action` 非空, ITS `kind` SHALL 只取 `run_cli`、`start_task`、`resume_task`、`wait_and_retry` 或 `confirm_new_request`；WHEN 无需用户动作, THE Config_Command SHALL 返回 `primary_action: null`，不得同时使用空对象或 `kind=none` 表达相同语义。
13. WHEN `primary_action.kind` 为 `run_cli`, THE Primary_Action 生产者 SHALL 保证 `primary_action.command` 是当前平台可直接执行且正确引用的本地命令；配置、验证、修复或切换 Provider 的动作 SHALL 使用绝对 CLI_Path，唯有 `reason_code=cli_path_unresolved` 时 SHALL 使用安装器已知的绝对 runtime manager 或 launcher 修复命令，且不得伪造尚未解析出的 CLI_Path。其他 kind SHALL NOT 包含或伪造 CLI 命令。
14. THE Config_Command 的人类可读界面 SHALL 只呈现单一结论与至多一个 Primary_Action；`configured_unverified` 的结论 SHALL 为“配置完成，可以开始使用；首次生成图片时验证服务”，不得使用失败或阻断措辞；完整分层仅在 JSON 输出中呈现。
15. WHEN `config status` 成功完成检查, THE Config_Command SHALL 以成功退出表示“状态检查已完成”；WHEN `config` 或 `repair` 达到 `configured_unverified` 或 `ready`, THE Config_Command SHALL 以成功退出表示配置目标已达到；WHEN `verify` 未达到 `ready`, THE Config_Command SHALL 使用稳定的非成功退出类别并仍输出完整机器可读结果。
16. THE Config_Command SHALL 仅在目标 Route 的 `required_capabilities` 是匹配 Verification_Receipt 中当前有效 Capability_Evidence 所对应能力的子集时返回该 Route 的 `ready`；否则 SHALL 返回 `configured_unverified` 或与缺失能力对应的非就绪状态。

### Requirement 3: 密钥安全录入

**User Story:** 作为用户，我想通过隐藏输入安全录入 API Key，这样密钥不会进入屏幕、shell 历史、Agent 上下文或项目文件。

#### Acceptance Criteria

1. WHERE 存在交互终端, THE Config_Wizard SHALL 默认通过隐藏输入（不回显）读取密钥。
2. WHERE 目标 Provider 已设置环境变量凭据（如 `OPENAI_API_KEY`）, THE Config_Command SHALL 识别该环境变量为有效 Credential_Reference 并不再要求录入。
3. WHERE 用户显式选择 stdin 通道（如 `--key-stdin`）, THE Config_Wizard SHALL 从 stdin 读取一次密钥并写入 Credential_Store，且不回显、不记录。
4. THE Config_Wizard SHALL NOT 以明文命令行参数（如 `--api-key`）、URL 查询参数或 Agent 聊天消息形式接受密钥。
5. IF 需要录入新密钥但既无交互终端、又无环境变量凭据、也未显式选择 stdin 通道, THEN THE Config_Wizard SHALL 返回 `credential_input_channel_unavailable`，并列出可用的非交互通道与在终端运行的准确命令。
6. WHERE 密钥来自 TTY 隐藏输入或显式 stdin, THE Config_Wizard SHALL 将密钥写入 Credential_Store；WHERE 使用既有环境变量, THE Config_Wizard SHALL 只保存 `env:<NAME>` Credential_Reference，不得复制环境变量值。两种路径均只输出 Credential_Reference 和非敏感状态。
7. IF 用户输入空密钥, THEN THE Config_Wizard SHALL 返回 `credential_empty` 并允许用户重新输入或安全退出。
8. IF Credential_Store 已存在目标 Provider 的凭据且用户未选择覆盖, THEN THE Config_Wizard SHALL 保留原凭据并返回 `credential_overwrite_confirmation_required` 或继续使用现有引用。
9. WHEN 用户确认覆盖凭据, THE Config_Wizard SHALL 使依赖旧凭据的 Verification_Receipt 失效。
10. THE Config_Wizard SHALL NOT 将密钥写入 Config_File、Skill 目录、项目目录、run 目录、Verification_Receipt、stdout、stderr 或日志。
11. THE Credential_Store adapter SHALL NOT 将密钥放入当前进程或子进程的 argv、命令回显或普通临时文件；如需调用平台工具，SHALL 使用不暴露 secret 的平台 API、受保护输入通道或等价机制。

### Requirement 4: OpenAI-compatible 中转站配置

**User Story:** 作为使用中转站的用户，我想在同一向导中配置服务地址、图片模型和独立密钥，这样可以直接验证中转站是否真正支持图片生成。

#### Acceptance Criteria

1. WHEN 用户选择 `openai-compatible`, THE Config_Wizard SHALL 收集 `endpoint_origin`、`model` 和该 Provider 独立的 Credential_Reference。
2. THE Config_Wizard SHALL 将 `endpoint_origin` 与 `model` 写入 Provider_Profile；TTY 隐藏输入或显式 stdin 提供的密钥 SHALL 写入 Credential_Store，环境变量通道 SHALL 只写入独立 Credential_Reference。
3. IF `endpoint_origin` 不是不含用户名、密码、查询串与片段的 HTTPS 地址, THEN THE Config_Wizard SHALL 返回 `provider_profile_invalid:endpoint_origin` 并允许重新输入。
4. IF `model` 为空或仅包含空白, THEN THE Config_Wizard SHALL 返回 `provider_profile_invalid:model` 并允许重新输入。
5. THE Config_Wizard SHALL NOT 将中转站密钥与 OpenAI 官方 Provider 的密钥引用混用。
6. WHEN 用户更改 `endpoint_origin` 或 `model`, THE Config_Wizard SHALL 使旧 Verification_Receipt 失效并返回 `configured_unverified`，但 SHALL NOT 因此阻止首次真实业务图片承担惰性验证。
7. WHERE Provider registry 明确声明目标 endpoint 的模型列表查询无费用且无实质副作用, THE Config_Wizard SHALL 在发起付费 Provider_Smoke 或首次真实业务图片请求前校验 `model` 是否在该列表中，并在不在时返回 `provider_profile_invalid:model` 而不发起图片请求。

### Requirement 5: 本地配置检查

**User Story:** 作为用户，我想快速查看配置结构是否完整，而不在每次状态查询时产生接口费用。

#### Acceptance Criteria

1. WHEN 用户运行 `leo-ppt config status`, THE Config_Command SHALL 只执行 Local_Configuration_Check，不发起 Provider_Smoke。
2. THE Local_Configuration_Check SHALL 检查 Config_File schema、Provider_Profile、Credential_Reference、目标 Route 与 Provider 的兼容性以及 Verification_Receipt 新鲜度。
3. THE Local_Configuration_Check SHALL 列出所有已配置 Provider 的非敏感状态，并明确当前选择的 Provider。
4. IF 发现多个可用 Provider 且未设置当前选择, THEN THE Config_Command SHALL 返回稳定的选择规则或 `provider_selection_required`，不得静默随机选择。
5. IF Config_File 包含疑似 secret、token、password 或 key 的未知字段, THEN THE Config_Command SHALL 返回 `unknown_sensitive_field`，不得回显字段值。

### Requirement 6: 真实图片服务验证

**User Story:** 作为用户，我想自己决定是否在配置时付费验证，也能在首次真实任务中完成验证，这样 `ready` 保持“确实生成过可用图片”的强语义，同时安装配置不被额外费用阻断。

#### Acceptance Criteria

1. WHEN External_Provider 首次配置完成且 Local_Configuration_Check 通过, THE Config_Wizard SHALL 返回 `configured_unverified`，并明确询问用户是否立即执行一次可能计费的 Provider_Smoke；提示默认值 SHALL 为“否”，且未收到 Paid_Verification_Consent 时 SHALL NOT 发起图片请求。
2. WHEN 用户跳过 Provider_Smoke, THE Config_Wizard SHALL 以成功结果结束，返回 `execution_eligibility=allowed`，并说明首次真实业务图片将完成验证；跳过不得被表述为取消配置或失败。
3. WHEN 用户运行 `leo-ppt config verify`、显式传入 `--verify` 或在向导中肯定同意计费验证, THE Config_Command SHALL 将该动作视为仅对当前验证操作有效的 Paid_Verification_Consent，并对当前或明确指定的 External_Provider 执行 Provider_Smoke；安装器、更新器和 Agent 宿主 SHALL NOT 代替用户生成该授权。
4. THE Provider_Smoke SHALL 向目标 endpoint/model 发起一次最小真实图片生成请求，并验证返回图片非空、可读取且格式受支持；v1 Provider_Smoke SHALL 只产生 `generate` Capability_Evidence，不得声称验证 `edit`、`mask` 或 `reference`。
5. WHEN Provider_Smoke 成功, THE Config_Command SHALL 原子合并 `generate` Capability_Evidence；WHEN Default_Route 为 `generate` 且该证据有效, THE Config_Command SHALL 返回该 Route 的 `ready`。
6. BEFORE `configured_unverified` Provider 的首张真实业务图片请求, THE 业务执行器 SHALL 使用与 Provider_Smoke 相同的验证包装器、错误分类、产物校验和幂等机制；WHEN 请求成功且图片有效, THE 业务执行器 SHALL 保留该业务图片，并为实际执行的每项能力原子合并独立 Capability_Evidence，不得覆盖仍有效的其他能力证据。
7. IF Provider 返回 401、403、404、429、5xx、超时、空产物或不可读产物, THEN THE Config_Command 或业务执行器 SHALL 返回可区分的 Reason_Code 和对应 Primary_Action，不得写入本次操作对应的成功 Capability_Evidence。
8. IF 显式 Provider_Smoke 失败但本地配置仍完整, THEN THE Config_Command SHALL 保留现有凭据与档案，并返回 `degraded` 或 `invalid`，不得删除用户配置。
9. IF 首次真实业务图片失败, THEN THE 业务执行器 SHALL 保留主题、材料、大纲、逐页稿和已经完成的中间产物，并在修复后从图片节点恢复，不得要求用户重新开始任务。
10. THE Provider_Smoke SHALL NOT 将其专用验证图片长期保存为用户交付物；仅保留完成验证所需的摘要和最小非敏感证据。真实业务图片 SHALL 作为任务产物保留，不适用此删除规则。
11. WHERE Provider registry 明确声明 Auth_Probe 无费用且无实质副作用, THE Config_Command SHALL 默认执行 Auth_Probe；否则 SHALL 跳过且不得通过试调用推断其免费性或安全性。
12. IF Auth_Probe 判定凭据无效, THEN THE Config_Command SHALL 返回对应鉴权 Reason_Code 且不发起图片请求；IF Auth_Probe 成功, THEN THE Config_Command SHALL NOT 因此写入任何 Capability_Evidence、返回 `ready` 或声称图片能力已验证。
13. WHEN Provider_Smoke 或首次真实业务图片遇到瞬时类失败（429、5xx、超时、网络错误）, THE 执行器 SHALL 仅在 Provider registry 明确声明目标接口支持幂等语义，或能够证明请求尚未被 Provider 接受时执行有界退避重试。
14. THE Config_Command 和业务执行器 SHALL 为每次 Provider_Smoke 或首次真实业务图片验证意图生成稳定 operation id，并在 Provider 支持时传递幂等键；重试、中断恢复和 Capability_Evidence 持久化恢复 SHALL 复用同一 operation id。
15. IF Provider 不支持可证明的幂等语义且失败发生在请求结果不确定之后, THEN THE 执行器 SHALL NOT 自动重试，SHALL 返回 `provider_outcome_unknown` 与 `degraded`，保留任务上下文，并由用户明确决定是否发起新的可能计费请求。
16. IF 真实图片已经成功但 Capability_Evidence 原子合并失败, THEN THE 执行器 SHALL 保留有效图片和由现有 run lifecycle 持有的非敏感恢复证据，并返回可恢复的证据持久化原因，不得返回当前 Route 的 `ready`；重试合并 Capability_Evidence SHALL 仅使用本地产物与恢复证据，不得再次调用 Provider。
17. BEFORE 同一 Verification_Scope 已有覆盖全部目标能力的有效 Capability_Evidence, THE 执行器 SHALL 保证最多一个可能计费的验证请求处于进行中；并发页面 SHALL 等待同一结果，成功后共享原子合并后的证据并放行，失败后共享同一失败结果，不得自行发起额外付费请求。
18. THE Config_Command SHALL 将 `degraded` 作为当前 Provider 调用或当前恢复上下文的操作结果；纯本地 `config status` 在没有当前失败上下文且本地配置完整、目标能力证据不足时 SHALL 返回 `configured_unverified`，不得从未定义的历史失败状态推断 `degraded`。
19. WHEN 用户运行不带 Route 的 `config status`、`config verify` 或安装后检查, THE Config_Command SHALL 使用 Default_Route `generate` 并在 `readiness_scope.route` 中显示；v1 `config verify` SHALL 只验证 `generate`，其他能力只能由真实执行业务请求时惰性验证。

### Requirement 7: 验证凭据与失效策略

**User Story:** 作为升级用户，我想复用仍然可信的验证结果，同时在关键配置变化后自动重新验证，这样既减少费用又避免错误就绪结论。

#### Acceptance Criteria

1. THE Verification_Receipt SHALL 记录 schema 版本、Provider、endpoint origin、model、credential version、runtime identity、adapter version、verification policy version、Verification_Fingerprint，以及按能力独立的 Capability_Evidence。
2. EACH Capability_Evidence SHALL 记录 capability、验证时间、过期时间、operation id、验证来源和产物摘要；THE Verification_Receipt SHALL NOT 记录密钥、鉴权 header、请求正文、完整响应正文、生成图片或用户材料。
3. WHEN Provider、endpoint、model、凭据版本、runtime adapter 或 verification policy 变化, THE Config_Command SHALL 将整份现有 receipt 判定为失效；THE Verification_Fingerprint SHALL NOT 包含验证结果或已验证能力。
4. WHEN 某项 Capability_Evidence 超过当前 Verification_Policy 的有效期, THE Config_Command SHALL 仅使该能力证据失效；目标 Route 仍由其全部 required capabilities 的有效证据集合决定是否 `ready`。
5. WHEN Skill 更新但 Verification_Fingerprint 未变化且目标 Route 所需 Capability_Evidence 仍有效, THE Post_Activation_Onboarding SHALL 复用证据，不重复发起付费 smoke。
6. WHEN 用户显式请求验证并确认可能产生费用, THE Config_Command SHALL 忽略仍有效的 `generate` Capability_Evidence 并重新执行 Provider_Smoke；该动作不得刷新其他能力证据。
7. WHERE 使用环境变量 Credential_Reference, THE Config_Command SHALL 以 Credential_Store 中设备本地受保护的随机 Fingerprint_Key 生成环境变量值的 HMAC `credential_version`；THE Verification_Receipt SHALL NOT 保存裸 API Key hash，且 Fingerprint_Key 丢失或变化 SHALL 使既有 receipt 失效。
8. WHEN 一次真实业务调用成功执行多个能力, THE 执行器 MAY 为这些实际执行的能力写入具有同一 operation id 的独立 Capability_Evidence；THE 执行器 SHALL NOT 为未实际执行的能力写证据。
9. WHEN 新增或刷新某项 Capability_Evidence, THE Config_Command 或业务执行器 SHALL 原子合并到同一 Provider receipt，并保留仍匹配当前 Verification_Fingerprint 且未过期的其他能力证据。
10. THE Verification_Policy SHALL 拥有每项能力的 TTL 和 policy version；v1 未被 Registry 覆盖时的默认 TTL SHALL 为能力成功后的 7 天，用户配置 SHALL NOT 任意延长 TTL。

### Requirement 8: 首次安装配置引导

**User Story:** 作为首次安装用户，我想在仍处于真实终端时完成图片服务配置，这样进入 Agent 宿主后可以立即生成 PPT。

#### Acceptance Criteria

1. WHEN Install_Transaction 成功, THE Post_Activation_Onboarding SHALL 解析 CLI_Path 并执行 `config status --route generate`，以 Default_Route 计算安装可用性。
2. IF Default_Route 的 External_Provider Config_Status 为 `ready`, THEN THE 安装器 SHALL 报告安装与该 readiness scope 均已就绪，且不重复要求密钥；THE 安装器 SHALL 保持 Host_Capability_State 为 `unknown`，不得让 Host_Provider 参与安装 `ready` 结论。
3. IF Config_Status 为 `configured_unverified`, THEN THE 安装器 SHALL 报告 `usable_unverified`，明确“配置完成，可以开始使用；首次生成图片时验证服务”，且 SHALL NOT 强制启动验证。
4. IF Execution_Eligibility 为 `blocked` 或 `retryable` 且存在交互终端, THEN THE Post_Activation_Onboarding SHALL 默认启动或明确提供立即进入 Config_Wizard 的单步选择。
5. WHEN 用户明确推迟尚未完成的配置, THE 安装器 SHALL 保留安装结果并报告 `installed_not_ready`、原因和准确的 `leo-ppt config` 命令。
6. IF Config_Wizard 失败、取消或执行资格仍为 `blocked` 或 `retryable`, THEN THE 安装器 SHALL NOT 回滚已经激活的 Skill，并 SHALL NOT 报告“可以生成 PPT”。
7. IF CLI_Path 无法解析, THEN THE 安装器 SHALL 返回稳定的 CLI 解析 Reason_Code 与 `run_cli` 类型 Primary_Action；该动作 SHALL 使用安装器已知的绝对 runtime manager 或 launcher 修复命令完成 runtime 修复或 CLI_Path 重新解析，不得引用或伪造尚未解析出的 CLI_Path。
8. THE Post_Activation_Onboarding SHALL 在输出中分别展示 Skill 安装状态、配置状态、真实验证状态和执行资格。

### Requirement 9: 更新后的配置检查

**User Story:** 作为升级用户，我想在更新后自动确认已有配置是否仍可用，这样升级不会静默破坏图片服务。

#### Acceptance Criteria

1. WHEN Skill 更新完成, THE Post_Activation_Onboarding SHALL 始终执行 Local_Configuration_Check。
2. WHEN 已有配置与 Default_Route 所需 Capability_Evidence 仍匹配且有效, THE Post_Activation_Onboarding SHALL 保留配置并报告该 readiness scope 为 `ready`，不得重新索要密钥。
3. WHEN Verification_Fingerprint 变化，或 Default_Route 所需 Capability_Evidence 缺失、过期或损坏但本地配置仍完整, THE Post_Activation_Onboarding SHALL 返回 `configured_unverified` 与 `usable_unverified`，说明下一次真实业务图片会重新验证；显式 `config verify` 只作为可选的 `generate` 付费验证动作而非阻断动作。
4. WHEN 更新后的纯本地检查发现配置为 `invalid`, THE Post_Activation_Onboarding SHALL 给出 `run_cli` 类型的 `config repair` Primary_Action，并保持 Skill 安装成功；THE 更新检查 SHALL NOT 从历史 Provider 失败推断 `degraded`。
5. IF 更新流程显式承接一个仍在恢复的当前 Provider 操作, THEN THE Post_Activation_Onboarding SHALL 原样传播该操作基于 Reason_Code 产生的 typed Primary_Action，不得把 `wait_and_retry` 或 `confirm_new_request` 统一覆盖成 `config repair`。
6. THE 更新流程 SHALL NOT 删除或覆盖 `LEO_PPT_HOME`、Credential_Store、Provider_Profile 或有效 Verification_Receipt。

### Requirement 10: 多通道凭据录入与非交互配置

**User Story:** 作为在本地机器安装、可能通过管道或 CI 进行非交互配置的用户，我想用环境变量或显式 stdin 完成凭据配置，而不被迫进入交互终端，也不担心密钥被误读或泄露。

#### Acceptance Criteria

1. THE Config_Command SHALL 支持三类 Credential_Input_Channel：交互终端的隐藏输入、既有环境变量引用、用户显式选择的 stdin 通道。
2. IF 不存在交互终端, THEN THE Config_Wizard SHALL NOT 调用隐藏输入，也 SHALL NOT 从普通 stdin 隐式读取密钥。
3. WHERE 目标 Provider 已存在环境变量凭据, THE Config_Command SHALL 直接将其视为有效 Credential_Reference，可据此判定为已配置且不再要求录入。
4. WHERE 用户显式选择 stdin 通道, THE Config_Wizard SHALL 从 stdin 读取一次密钥、写入 Credential_Store，且不回显、不记录、不写入 Config_File。
5. THE Config_Command SHALL NOT 以明文命令行参数接受密钥。
6. WHEN 安装收尾发现未配置且不存在交互终端, THE Post_Activation_Onboarding SHALL 以 `installed_not_ready` 完成，并提示可用的非交互通道（环境变量或显式 stdin）与在终端运行的准确 CLI_Path 命令，而不阻塞等待或误报 `ready`。
7. WHEN 输出终端命令指引, THE 指引 SHALL 针对当前 shell（PowerShell 或 POSIX）使用可执行且正确引用带空格路径的形式。
8. IF Config_File 保存 `environment-reference` 但当前进程中对应环境变量缺失或为空, THEN THE Config_Command SHALL 为该 Provider 返回 `not_configured`、`credential_environment_missing` 与 `blocked`，并推荐 `run_cli` 类型的 `config repair` 以改用当前宿主可见的环境变量或 Credential_Store；该缺失 SHALL NOT 被误报为 schema `invalid`，也不得阻断另一个兼容且可用的 Provider。

### Requirement 11: 宿主首次调用守卫与任务恢复

**User Story:** 作为在 Codex、Claude 或 Kiro 中开始生成 PPT 的用户，我想让 Skill 自动检查配置并在修复后继续原任务，这样不需要理解内部 setup 流程或重新提交材料。

#### Acceptance Criteria

1. BEFORE Agent 开始任何需要图片能力的 PPT Route, THE Host_Readiness_Guard SHALL 运行只读配置状态检查，并结合当前宿主的图片能力执行 setup。
2. IF Host_Provider 在当前宿主现场可用, THEN THE Host_Readiness_Guard SHALL 允许使用 Host_Provider，且不要求外部 API Key。
3. IF Host_Provider 不可用且 External_Provider 为 `ready` 或 `configured_unverified`, THEN THE Host_Readiness_Guard SHALL 允许继续；后者 SHALL 在首张真实业务图片请求中执行惰性验证。
4. IF Host_Provider 不可用且 External_Provider 为 `not_configured` 或 `invalid`, THEN THE Host_Readiness_Guard SHALL 暂停图片生成步骤并向用户只展示一个 Primary_Action 命令。
5. THE Host_Readiness_Guard SHALL NOT 请求用户在聊天中粘贴密钥，也不得读取、转发或代填明文密钥。
6. WHEN 用户完成终端配置, THE Host_Readiness_Guard SHALL 重新检查 config 与 setup 状态。
7. WHEN 复查的 Execution_Eligibility 为 `allowed`, THE Agent SHALL 从中断点恢复原 PPT 任务，并保留用户已提交的主题、材料、约束和已完成中间产物。
8. IF 惰性验证失败, THEN THE Agent SHALL 保留原任务上下文和全部有效中间产物，只暂停图片节点，执行 Primary_Action 后从该节点复查并恢复。
9. IF Plugin 或宿主没有可靠的 post-install hook, THEN THE Host_Readiness_Guard SHALL 作为强制首次使用兜底，不得假设安装阶段已经完成配置。

### Requirement 12: 宿主内置图片能力边界

**User Story:** 作为使用宿主内置图片能力的用户，我想避免被错误要求配置外部 Key，同时也不希望安装器凭猜测宣称宿主能力可用。

#### Acceptance Criteria

1. THE Post_Activation_Onboarding SHALL NOT 在宿主外部将 `builtin-imagegen` 推断为 `ready`。
2. THE Config_Command SHALL 将尚未现场确认的 Host_Provider 标记为 `host_check_required` 或等价非就绪状态。
3. ONLY WHEN 当前宿主的 setup 明确确认图片能力可用, THE Host_Readiness_Guard SHALL 将 Host_Provider 判定为 `ready`。
4. IF 宿主能力后来不可用, THEN THE Host_Readiness_Guard SHALL 降级到 `ready` 或 `configured_unverified` 的 External_Provider；若不存在，则返回配置 Primary_Action。
5. THE Host_Readiness_Guard SHALL 使用独立 Host_Capability_State 表达 Host_Provider；`host_check_required` 只作为 Provider-level Reason_Code，且 SHALL NOT 写成 External_Provider 的 Verification_State 或伪造 Verification_Receipt。

### Requirement 13: 幂等、取消与部分失败恢复

**User Story:** 作为重复运行配置或中途遇到故障的用户，我想安全续接而不是破坏已完成步骤，这样恢复操作可预测。

#### Acceptance Criteria

1. WHEN Config_Wizard 对已 ready 的 Provider 再次运行且用户未请求变更, THE Config_Wizard SHALL 直接报告当前状态，不重复索要密钥或发起 smoke。
2. WHEN 用户在任一步骤取消, THE Config_Wizard SHALL 保留取消前已经成功、原子写入的配置，并准确报告未完成步骤和 `config repair` 命令。
3. IF 密钥已保存但 Provider_Profile、Provider_Smoke 或首次真实业务图片验证失败, THEN THE Config_Command SHALL 保留密钥、任务上下文和有效中间产物并从失败步骤恢复，不得要求用户无条件重新录入或重启任务。
4. IF Provider_Profile 写入失败, THEN THE Config_Command SHALL NOT 破坏写入前的有效 Config_File。
5. IF Capability_Evidence 原子合并失败, THEN THE Config_Command SHALL NOT 返回当前 Route 的 `ready`，即使 Provider_Smoke 或真实业务图片已成功；已有业务图片 SHALL 保留，状态 SHALL 为 `configured_unverified`，并提供不重复调用 Provider 的本地证据持久化修复动作。
6. WHEN 用户运行 `config repair`, THE Config_Command SHALL 从当前 Reason_Code 对应的最早未完成步骤继续，并避免修改无关 Provider。
7. WHEN 用户运行 `config change`, THE Config_Command SHALL 在切换成功并验证前保留原 ready Provider 作为可恢复选择。

### Requirement 14: 跨平台凭据存储

**User Story:** 作为 macOS 或 Windows 用户，我想把密钥存入各自平台的受保护存储，这样凭据受操作系统用户边界保护。

#### Acceptance Criteria

1. WHERE 当前平台为 macOS, THE Config_Wizard SHALL 将密钥写入 macOS Keychain。
2. WHERE 当前平台为 Windows, THE Config_Wizard SHALL 使用当前用户 DPAPI 加密凭据，并确保凭据目录和文件 ACL 不向其他普通用户开放。
3. IF Credential_Store 不受支持, THEN THE Config_Wizard SHALL 返回 `credential_store_unsupported` 且不写入明文替代文件。
4. IF Credential_Store 被锁定、拒绝访问、blob 无效或 ACL 过宽, THEN THE Config_Wizard SHALL 返回对应 Reason_Code，且单次写入不得留下可被当作有效凭据的临时文件。
5. THE Config_Command SHALL 使用与当前受管 runtime 相同的 LEO_PPT_HOME 和当前操作系统用户上下文。

### Requirement 15: 隐私、日志与可观测性

**User Story:** 作为用户和维护者，我想获得足够的故障证据但不泄露密钥或业务材料，这样问题可诊断且安全。

#### Acceptance Criteria

1. THE Config_Command SHALL 为每次状态检查、配置步骤和验证步骤输出稳定 Reason_Code、阶段、结果和非敏感 evidence refs。
2. THE Config_Command SHALL NOT 在日志、异常、遥测、receipt、命令回显或诊断包中记录密钥、鉴权 header、完整请求正文或完整 Provider 响应。
3. THE Config_Command SHALL 对 endpoint 日志至少移除用户名、密码、查询串与片段，并不得记录用户在 PPT 任务中提交的材料。
4. WHEN Provider_Smoke 失败, THE Config_Command SHALL 保留足以区分鉴权失败、模型/路径错误、限流、服务端错误、网络错误、超时和产物校验失败的非敏感证据。
5. THE Config_Command SHALL 保证人类可读输出与 JSON 输出表达相同的 Config_Status、Reason_Code 和 Primary_Action。

### Requirement 16: Route 与 Provider 兼容性

**User Story:** 作为使用不同 PPT 流程的用户，我想让配置检查针对实际 Route 判断能力，这样不会出现 Provider 已配置但当前流程仍不可执行的假就绪。

#### Acceptance Criteria

1. THE Route_Capability_Matrix SHALL 是 checked-in runtime source 中的唯一 Route 基础能力真值，并由 setup、Config_Command 和业务执行器共同消费；v1 SHALL 定义 `generate -> {generate}`，`direct-editable -> {edit}`，`upgrade-full -> {edit}`，`upgrade-selected -> {edit}`。
2. WHEN 实际业务请求使用 mask 或独立额外参考图, THE 执行器 SHALL 在 Route 基础能力上分别增加 `mask` 或 `reference`，并以最终集合计算 Verification_Scope。
3. WHEN 用户或 Agent 指定 Route, THE Local_Configuration_Check SHALL 按该 Route 与当前任务的最终 `required_capabilities` 检查 Provider。
4. WHERE 用户、安装器或 Agent 未指定 Route, THE Config_Command SHALL 使用 Default_Route `generate`，并在 `readiness_scope.route` 中明确输出，不得按 Provider 隐式改变业务意图。
5. IF Provider 只满足部分能力, THEN THE Config_Command SHALL 列出可用 Route 与不可用 Route，并为目标 Route 返回非就绪状态。
6. THE Config_Command SHALL 支持 `openai-compatible` 参与 setup Provider 选择，且其状态、错误和验证行为与 Provider 列表保持一致。
7. THE Config_Command SHALL NOT 因一个非目标 Provider 配置损坏而阻止另一个已验证 Provider 执行兼容 Route。
8. THE Config_Command SHALL 明确输出目标 Route 的 `required_capabilities`、由当前有效 Capability_Evidence 派生的 `verified_capabilities` 和 `missing_capabilities`，并据此计算该 Route 的 Config_Status 与 Execution_Eligibility。
9. THE Config_Command、setup 和业务执行器 SHALL NOT 各自复制或扩展 Route 能力映射；任务级附加能力必须来自实际请求，而不是 Provider 的乐观静态声明。

### Requirement 17: 文档与帮助一致性

**User Story:** 作为首次使用者，我想在安装输出、CLI 帮助、README 和用户手册中看到一致的配置路径，这样可以从任一入口完成设置。

#### Acceptance Criteria

1. THE 安装输出、`leo-ppt config --help`、README、用户手册和故障排查文档 SHALL 统一推荐 `leo-ppt config`。
2. THE 用户文档 SHALL 分别说明首次安装、更新、首次宿主调用、中转站配置、非交互配置（环境变量/显式 stdin）、修改 Provider 和修复配置的路径。
3. THE 用户文档 SHALL 提供各 External_Provider 官方密钥获取入口、所需权限和最小验证可能产生接口费用的提示。
4. THE 用户文档 SHALL 明确禁止在 Agent 聊天、命令参数、项目配置或 issue 中粘贴 API Key。
5. THE 用户文档 SHALL 分别解释 `usable_unverified` 表示可以开始任务、首次图片会完成验证，以及 `installed_not_ready` 表示安装成功但当前仍不能执行需要图片能力的 PPT Route。
6. THE Reason_Code 文档 SHALL 覆盖本需求出现的所有稳定原因码，并为每个用户可修复原因提供唯一推荐动作。

### Requirement 18: 首次发布合同与回归边界

**User Story:** 作为项目负责人，我想在首次发布前只保留一套清晰的配置合同和入口，这样不会为未发布的开发期形态背负迁移与兼容成本。

#### Acceptance Criteria

1. THE Config_File SHALL 以本功能定义的 schema v1 作为首次正式发布的唯一公共配置合同。
2. THE 功能 SHALL NOT 为当前开发期 Config_File 形态、命令参数或底层命令提供自动迁移或向下兼容保证。
3. IF Config_Command 发现不符合目标 schema v1 的开发期 Config_File, THEN THE Config_Command SHALL 返回稳定的 `development_config_reset_required`，并由 `config repair` 在用户确认后重建目标配置；THE Config_Command SHALL NOT 猜测迁移旧字段。
4. WHEN 重建开发期 Config_File, THE Config_Command SHALL NOT 把 Credential_Store 中的密钥复制到 Config_File、日志或诊断输出；无法确认归属的开发期凭据 SHALL 保持不变，交由用户显式删除或覆盖。
5. THE 功能 SHALL 可删除或收敛仅服务开发期的重复配置入口、字段和命令，但 SHALL 保留统一入口所复用的必要内部能力及其测试覆盖。
6. THE 功能 SHALL NOT 修改 `.agents/skills/`、`.codex/` 或其他生成投影作为持久真值；宿主行为变更必须来自项目拥有的 Skill 源码或安装/投影流程。

### Requirement 19: Provider Registry 与验证策略

**User Story:** 作为用户和维护者，我想让所有外部 Provider 探测、能力、重试和费用边界来自同一份 fail-closed Registry，这样未知中转站不会因乐观默认产生错误就绪、重复计费或不安全探测。

#### Acceptance Criteria

1. THE runtime SHALL 将 Provider_Registry 作为 Provider 能力、adapter identity、Auth_Probe、模型发现、幂等、重试和 Verification_Policy 的唯一静态真值；setup、Config_Command 和业务执行器 SHALL 复用该真值，不得各自维护默认表。
2. THE Provider_Registry SHALL 为每个声明项区分 `supported`、`unsupported` 与 `unknown`，缺失声明 SHALL 等价于 `unknown`。
3. IF Auth_Probe 或模型发现策略为 `unknown`, THEN THE Config_Command SHALL 跳过自动探测，不得通过试调用推断免费性、安全性或能力。
4. IF 幂等语义或请求未被接受的证据为 `unknown`, THEN THE 执行器 SHALL NOT 对结果不确定的可能计费请求自动重试。
5. THE Provider_Registry 的静态 capability 声明 SHALL 只表示候选兼容性，不得单独产生 `ready`；真实 readiness SHALL 继续由当前 readiness scope 的全部 required capabilities 是否被匹配基础 Verification_Fingerprint 且未过期的 Capability_Evidence 覆盖，或由当前宿主现场能力覆盖来决定。
6. FOR 任意用户配置的 OpenAI-compatible endpoint, THE Provider_Registry SHALL 对 endpoint-specific Auth_Probe、模型发现和幂等能力默认使用 `unknown`，除非当前 adapter 与目标 endpoint 有可复核的明确声明。
7. WHEN Registry、adapter 或 Verification_Policy 的相关版本变化, THE Config_Command SHALL 重新计算 Verification_Fingerprint，并在不再匹配时把 receipt 标记为 stale。
8. THE Provider_Registry SHALL 是 checked-in runtime source；Config_File、安装器、Agent 宿主和用户输入 SHALL NOT 覆盖其安全声明。

## Scope Boundaries

### In Scope

- External_Provider 的首次配置、本地状态检查、显式真实图片 smoke、首次业务图片惰性验证、receipt 与修复流程。
- macOS arm64 与 Windows x64 的安装后 onboarding、凭据存储和终端指引。
- Codex、Claude、Kiro 等宿主的首次调用守卫和原任务恢复。
- 安装、更新、Plugin 无 post-install hook、非交互配置（环境变量/显式 stdin）和中转站场景。
- README、用户手册、CLI 帮助、故障排查和 Reason_Code 文档同步。
- Provider Registry、费用授权、能力级 readiness、single-flight 验证和 operation-local degraded 语义。

### Out of Scope

- 在 Agent 聊天中接收或托管用户密钥。
- 启动 localhost 配置服务、自动打开浏览器或通过网页录入密钥；浏览器配置属于二期候选，不进入当前主流程。
- 提供云端密钥托管、跨设备凭据同步或团队共享凭据。
- 为 Linux 新增明文凭据回退；不支持的安全存储必须明确失败。
- 以一次 Provider_Smoke 证明长期 SLA、图片审美质量或所有模型能力。
- 改变 PPT 内容策划、页面设计、可编辑重建和最终交付流程本身。
- 为尚未对外发布的开发期配置文件、命令或本地测试数据提供自动迁移和向下兼容。

## Success Criteria

1. 首次安装用户只需进入一个统一向导即可达到 External_Provider `configured_unverified` 并开始任务；如用户明确同意计费验证，则可在同一向导让 Default_Route `generate` 的 readiness scope 达到 `ready`，不需要手工组合底层命令。
2. 安装结果准确区分 `ready`、`usable_unverified` 与 `installed_not_ready`；`configured_unverified` 不被误报为阻断，任何可能计费的 smoke 均不得由默认回车或隐式流程触发。
3. Agent 宿主全流程不接触明文 API Key，配置完成后能够复查并恢复原 PPT 任务。
4. 现有有效凭据和档案在重装、更新及重复运行向导后保持不变；基础 Verification_Fingerprint 失效时整份旧 receipt 失效，单项 Capability_Evidence 过期时仅该能力失效，受影响的 readiness scope 回到 `configured_unverified`；`generate` 可由用户显式 smoke 或下一次真实 generate 请求重新验证，`edit`、`mask` 与 `reference` 只能由下一次实际执行对应能力的真实业务请求重新验证。
5. macOS Keychain 与 Windows DPAPI 路径均能完成隐藏录入、本地检查、显式 smoke、惰性验证、错误恢复和秘密扫描验证。
6. 多页并发时，同一 Verification_Scope 不会产生多个在途付费验证请求；`generate` 的成功证据不会让缺少对应 `edit`、`mask` 或 `reference` Capability_Evidence 的目标 Route 假就绪。
