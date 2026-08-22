# Leo PPT Generator Provider 配置流程

## 1. 产品决策与适用边界

当前版本以终端配置为唯一主通道，服务本地安装、开发者工作站、远程终端和 SSH 场景。配置文件的目标 schema、平台路径与字段说明见 [`config-file.md`](./config-file.md)。

- 普通用户唯一推荐入口：`leo-ppt config`
- 交互式密钥录入：真实 TTY 中使用隐藏输入（`getpass`）
- 非交互式密钥来源：既有环境变量引用，或用户显式指定 `--key-stdin`
- 宿主职责：检查状态、给出准确终端命令、等待用户完成、复查并恢复原 PPT 任务
- 禁止通道：明文 `--api-key`、URL 查询参数、普通 stdin 的隐式读取、Agent 聊天消息
- 当前版本不启动 localhost 配置服务，不自动打开浏览器，也不以网页承载密钥录入
- Provider 能力、免费探测、模型发现、幂等、重试和 capability evidence TTL 只来自 checked-in Provider Registry；缺失声明按 `unknown` fail closed
- 未指定 Route 时固定使用 Default_Route `generate`；Route 基础能力矩阵为 `generate -> generate`，其余三条 editable Route -> `edit`，mask/reference 只按实际任务追加

浏览器配置属于二期可选增强，只面向同时满足“纯 GUI、本地桌面会话、不使用终端”的少数用户。它不进入当前安装、配置、宿主守卫或恢复流程，也不能成为当前版本达到 `ready` 的依赖。

## 2. 端到端主流程

```text
用户运行安装或更新命令
        |
        v
+-----------------------------+
| Install_Transaction         |
| 下载 -> runtime -> doctor   |
| -> Skill 原子激活           |
+-----------------------------+
        |
        +-- 激活失败 -----------> 安装失败，按安装错误处理
        |
        v
+-----------------------------+
| 解析受管 CLI_Path           |
+-----------------------------+
        |
        +-- 解析失败 -----------> installed_not_ready + CLI 修复命令
        |
        v
+-----------------------------+
| leo-ppt config status       | 未指定 Route 时固定使用 generate；
| --route generate            | 只做本地检查，不调用外部接口
+-----------------------------+
        |
        +-- ready（Default_Route=generate 的 External_Provider 证据有效）
        |                    -> 安装/更新完成，立即可用
        |
        +-- configured_unverified -> usable_unverified，可立即开始任务
        |
        +-- blocked / retryable
              |
              +-- 有真实 TTY --> 立即配置（推荐）/稍后配置
              |                    +-- 立即 -> leo-ppt config
              |                    +-- 稍后 -> installed_not_ready
              |
              +-- 无真实 TTY --> 检查环境变量 Credential_Reference
                                   +-- 本地档案与引用完整
                                   |      -> usable_unverified
                                   +-- 不完整
                                          -> installed_not_ready
                                          -> 准确终端命令
                                          -> 环境变量与 --key-stdin 用法

进入 Codex / Claude / Kiro 执行 PPT 任务
        |
        v
+-----------------------------+
| Host_Readiness_Guard        |
| config status + host setup  |
+-----------------------------+
        |
        +-- Host_Provider 现场可用 ----------> 按当前宿主能力继续原 PPT 任务
        +-- 当前 Route ready External_Provider -> 继续原 PPT 任务
        +-- configured_unverified ----------> 继续到首张业务图片
        |                                      +-> single-flight 惰性验证成功
        |                                      |    -> 保留图片、写能力级 receipt、当前 Route ready
        |                                      +-> 失败 -> 保留上下文，在图片节点恢复
        +-- degraded ------------------------> 保留上下文，按 typed action 等待、确认或修复
        +-- blocked / invalid ---------------> 暂停图片节点
                                                +-> 只给一个终端命令
                                                +-> 保留任务上下文
                                                +-> 用户完成后复查
                                                    +-- allowed -> 恢复原任务
                                                    +-- blocked/retryable -> 新的唯一动作
```

主流程必须区分两个结论：

1. Skill 激活成功只代表 `installed`，不代表图片服务 `ready`。
2. `configured_unverified` 表示配置完整且可以开始任务；只有 `not_configured`、`invalid` 或暂时不可执行的 `degraded` 才报告 `installed_not_ready`。

## 3. 安装与更新收尾

### 3.1 安装后决策流

```text
Install_Transaction 成功
        |
        v
解析 CLI_Path
        |
        +-- 失败 -> cli_path_unresolved
        |           installation_readiness: installed_not_ready
        |           primary_action.kind: run_cli
        |           primary_action.command: 安装器已知的绝对 runtime manager/launcher 修复命令
        |           不引用或伪造尚未解析出的 CLI_Path
        |
        v
"<CLI_Path>" config status --json --route generate
        |
        +-- status=ready（Default_Route=generate）
        |      -> Skill=installed
        |      -> External Provider: generate Capability_Evidence 有效
        |      -> Installation_Readiness=ready
        |      -> Host_Capability_State 保持 unknown，不能参与安装结论
        |
        +-- status=configured_unverified
        |      -> Skill=installed
        |      -> Verification_State=not_run 或 stale
        |      -> Execution_Eligibility=allowed
        |      -> Installation_Readiness=usable_unverified
        |
        +-- execution_eligibility=blocked/retryable 且存在真实 TTY
        |      -> 默认选择：立即运行 "<CLI_Path>" config
        |      -> 用户可明确选择稍后
        |
        +-- execution_eligibility=blocked/retryable 且无真实 TTY
               -> 不等待输入，不隐式消费 stdin
               -> 输出 installed_not_ready + reason_code
               -> 输出按当前 shell 正确引用的 Primary_Action
```

安装器只能询问是否立即启动终端向导，不能自行收集或代理密钥。无 TTY 安装不会因为 Provider 尚未配置而失败，也不会假装配置已经完成。

### 3.2 更新后决策流

```text
Skill 更新与激活完成
        |
        v
始终执行 Default_Route=generate 的 Local_Configuration_Check
        |
        +-- Verification_Fingerprint 匹配且 generate Capability_Evidence 有效
        |      -> 复用证据 -> generate scope ready
        |      -> 不索要密钥，不重复付费 smoke
        |
        +-- generate Capability_Evidence 缺失、过期或因 fingerprint 变化失效，但本地配置完整
        |      -> configured_unverified / usable_unverified
        |      -> 说明首张真实业务图片会重新验证
        |      -> config verify 仅作为可选的 generate 付费动作
        |
        +-- invalid
               -> 保留 LEO_PPT_HOME、凭据、档案和旧 receipt
               -> Primary_Action: run_cli / config repair

纯本地更新检查不从历史 Provider 失败推断 `degraded`。若更新流程显式承接一个仍在恢复的当前 Provider 操作，则原样传播该操作已有的 `wait_and_retry`、`confirm_new_request` 或 `run_cli` action，不得统一覆盖为 `config repair`。
```

## 4. `leo-ppt config` 终端向导

### 4.1 向导总流程

```text
leo-ppt config
        |
        v
读取当前状态
        |
        +-- 当前 Provider 对 Default_Route=generate 已 ready 且未要求变更
        |      -> 幂等返回，不索要密钥，不重复 smoke
        +-- 已有环境变量凭据 或 宿主已现场确认 builtin
        |      -> 跳过 Provider 菜单与非必要提问
        |         直接 Local_Configuration_Check（零提问 happy path）
        |
        v
选择 Provider
        +-- OpenAI
        +-- OpenAI-compatible 中转站
        +-- AtlasCloud
        +-- 退出
        |
        v
解析 Credential_Input_Channel
        +-- 已有环境变量 -> 使用引用，不复制明文
        +-- 真实 TTY -> getpass -> Credential_Store
        +-- 显式 --key-stdin -> 读取一次 -> Credential_Store
        +-- 以上均无 -> credential_input_channel_unavailable
        |
        v
收集 Provider_Profile
        +-- OpenAI / AtlasCloud -> model 与非敏感档案
        +-- OpenAI-compatible -> endpoint_origin + model
        |
        v
Local_Configuration_Check
        +-- invalid -> 定位字段 -> 重输或安全退出
        |
        v
配置完成 -> configured_unverified / execution_eligibility=allowed
        |
        v
询问是否立即执行可能计费的最小真实图片请求（默认：否）
        +-- 未明确同意/跳过
        |      -> 不调用 Provider
        |      -> usable_unverified，可立即开始任务
        |      -> 首张真实业务图片承担惰性验证
        |
        +-- 明确输入“是”，或显式 config verify / --verify
               -> Provider_Smoke（v1 仅验证 generate）
               +-- 成功 -> 原子合并 generate Capability_Evidence
               |           -> Default_Route=generate ready
               +-- 失败 -> 不写成功证据 -> 保留配置 -> 错误分流

`config verify` 不使用合成 edit/mask/reference 输入，也不声称验证这些能力；它们只在首次真实业务请求实际执行对应操作后获得 Capability_Evidence。
```

### 4.2 密钥输入通道

```text
需要 Provider 凭据
        |
        +-- 指定环境变量存在且非空
        |      -> Credential_Reference=env:<NAME>
        |      -> 不把值写入 config.yaml、日志或 receipt
        |
        +-- 否，存在真实交互终端
        |      -> getpass
        |      +-- 空值 -> credential_empty，允许重试或退出
        |      +-- 非空 -> 写 Keychain / DPAPI
        |
        +-- 否，用户显式传入 --key-stdin
        |      -> 从 stdin 读取一次，不回显、不记录
        |      -> 写 Keychain / DPAPI
        |
        +-- 否
               -> credential_input_channel_unavailable
               -> 不读取普通 stdin
               -> 输出环境变量与 --key-stdin 的准确示例
```

安全规则：

- `--key-stdin` 必须由用户显式选择；管道存在不等于授权读取。
- CLI 不提供也不接受 `--api-key <明文>`。
- 已有凭据默认复用；覆盖前必须确认，覆盖后递增凭据代次并使旧 receipt 失效。
- stdin 读取失败、空输入或多余数据不能退回明文文件存储。
- Credential Store adapter 不得把 secret 放入当前进程或子进程 argv、命令回显或普通临时文件。
- Config_File 引用了 `env:<NAME>` 但当前进程中变量缺失或为空时，该 Provider 返回 `not_configured / credential_environment_missing / blocked`，默认动作是 `run_cli / config repair`；不得误报为 schema invalid，也不得阻断其他兼容 Provider。

### 4.3 OpenAI-compatible 中转站

```text
选择 openai-compatible
        |
        v
输入 endpoint_origin
        +-- 必须为 HTTPS origin
        +-- 禁止 username/password/query/fragment
        +-- 不合法 -> provider_profile_invalid:endpoint_origin
        |
        v
输入 model
        +-- trim 后不能为空
        +-- 不合法 -> provider_profile_invalid:model
        +-- registry 明确声明模型列表查询免费且无副作用时 -> 可校验 model，缺失即
        |    provider_profile_invalid:model（不发起付费请求）
        |
        v
解析独立 Credential_Reference
        +-- 禁止与 OpenAI 官方凭据身份混用
        |
        v
原子写非敏感 Provider_Profile
        +-- endpoint 或 model 变化 -> 旧 receipt stale
        v
Local_Configuration_Check -> configured_unverified -> 显式选择是否 Provider_Smoke
```

## 5. 状态模型与命令合同

### 5.1 分层状态

```text
Configuration_State
  not_configured       缺少目标 Route 所需凭据或档案
  locally_configured   本地 schema、档案、引用和兼容性完整
  invalid              配置不可解释、敏感字段违规或合同不兼容

Verification_State（针对当前 readiness scope）
  not_run              尚未获得覆盖全部 required capabilities 的证据，且没有 stale/failed 条件
  passed               全部 required capabilities 均有匹配且有效的 Capability_Evidence
  failed               当前真实验证操作失败
  stale                至少一项 required capability 的既有证据已过期或 fingerprint 变化

Config_Status（优先级从高到低）
  invalid              必须修复的本地合同错误
  not_configured       本地配置不完整且无现场 Host_Provider
  degraded             本地有效，当前外部调用或恢复上下文暂时失败/限流/超时
  ready                当前 Route 所需能力已由有效 Capability_Evidence 完整覆盖，或 Host_Provider 被宿主现场确认覆盖目标能力
  configured_unverified
                       本地完整、允许执行，但当前 readiness scope 的 required capabilities 尚未被有效 Capability_Evidence 完整覆盖

Host_Capability_State（独立于 External Provider verification）
  unknown              当前宿主尚未现场声明
  available            当前宿主明确声明目标能力可用
  unavailable          当前宿主明确声明目标能力不可用

Execution_Eligibility
  allowed              ready 或 configured_unverified
  retryable            degraded，可在修复或重试后恢复
  blocked              not_configured 或 invalid

Installation_Readiness
  ready                已安装且已真实验证
  usable_unverified    已安装、本地配置完整、允许开始任务
  installed_not_ready  已安装，但当前执行资格为 blocked 或 retryable
```

`config status` 的退出成功表示“状态检查执行成功”，并不表示 `status=ready`。自动化必须读取 `leo-ppt-config/v1` JSON 的 `status` 与 `execution_eligibility`。`config` 和 `repair` 达到 `configured_unverified` 或 `ready` 均为成功；显式 `verify` 只有达到 `ready` 才成功。

`degraded` 是当前 Provider 调用或当前恢复上下文的操作结果。纯本地 `config status` 没有当前失败上下文且当前 readiness scope 的能力证据不足时返回 `configured_unverified`，不得从未定义的历史失败记录推断 `degraded`。

### 5.2 命令职责

| 命令 | 是否交互 | 是否调用外部接口 | 结果 |
| --- | --- | --- | --- |
| `leo-ppt config` | 默认是 | 默认不调用；仅在用户明确同意时调用 | 配置后达到 configured_unverified；可选验证后让 Default_Route `generate` scope 达到 ready |
| `leo-ppt config status` | 否 | 否 | 只读状态、原因和唯一下一步 |
| `leo-ppt config verify` | 显式费用确认 | 是 | 忽略当前有效的 `generate` Capability_Evidence，重新执行 generate-only smoke |
| `leo-ppt config repair` | 按故障需要 | 默认否；显式同意验证时才调用 | 从最早未完成步骤续接 |
| `leo-ppt config change` | 是 | 默认否；显式同意验证时才调用 | 候选本地配置完整后切换；可选立即验证 |

机器可读输出至少包含：

```text
protocol: leo-ppt-config/v1
status
configuration_state
verification.status
execution_eligibility
installation_readiness
readiness_scope.route
readiness_scope.required_capabilities[]
readiness_scope.verified_capabilities[]
readiness_scope.missing_capabilities[]
reason_code
selected_provider
providers[]
evidence_refs[]
primary_action
```

`primary_action` 无动作时为 `null`；非空时 `kind` 只能是 `run_cli`、`start_task`、`resume_task`、`wait_and_retry` 或 `confirm_new_request`。只有 `kind=run_cli` 时才包含 `command`：配置、验证、修复或 Provider 切换动作使用绝对 `CLI_Path`；仅 `reason_code=cli_path_unresolved` 时使用安装器已知的绝对 runtime manager/launcher 修复命令，不得引用或伪造尚未解析出的 CLI_Path。所有命令均须按 POSIX shell 或 PowerShell 正确引用含空格路径；其他 kind 不包含 `command`。不得同时使用空对象或 `kind=none` 表达无动作。一个状态只给普通用户一个主动作，其他安全通道只能作为补充说明。

## 6. 本地检查、真实验证与错误分流

### 6.1 Local_Configuration_Check

`config status`、安装和更新收尾只执行无费用检查：

```text
config.yaml schema
  + Provider_Profile 合法性
  + Credential_Reference 可解析性（不输出明文）
  + selected_provider 稳定选择
  + Route / Provider 能力兼容性
  + 当前 Route required capabilities 与匹配基础 fingerprint、未过期的 Capability_Evidence 派生能力集合之间的子集检查
  + Verification_Receipt 基础 fingerprint 与逐能力证据新鲜度检查
  + 未知敏感字段扫描
        |
        v
返回所有 Provider 非敏感状态 + 当前 Provider + Primary_Action
```

若多个 Provider 可用但没有当前选择，返回 `provider_selection_required`，不得随机选择。一个非目标 Provider 损坏不得阻止另一个已验证 Provider 执行兼容 Route。

### 6.2 Provider_Smoke

```text
用户已看到费用提示并同意
        |
        v
Auth_Probe（仅 registry 对当前 adapter/endpoint 明确声明无费用、无实质副作用时运行）
        |
        +-- 凭据无效（401/403 类）-> 返回鉴权 Reason_Code，不发起付费图片请求
        |
        v
生成稳定 operation id
        |
        v
Provider Registry 对当前 adapter/endpoint 明确支持幂等语义时传递幂等键
        |
        v
向选定 endpoint/model 发起最小 generate 图片请求
        |
        v
验证 Provider 接受 -> 产物非空 -> 可读取 -> 格式受支持
        |
        +-- 瞬时失败（429/5xx/超时/网络）
        |      +-- Provider 支持幂等，或可证明尚未接收请求
        |      |      -> 复用 operation id，有界退避重试 N 次
        |      |      +-- 重试预算耗尽 -> degraded
        |      +-- Provider 不支持幂等且结果不确定
        |             -> 不自动重试
        |             -> provider_outcome_unknown / degraded
        |             -> 用户决定是否发起新的可能计费请求
        |
        +-- 全部通过
        |      -> 生成非敏感摘要
        |      -> 原子合并 generate Capability_Evidence
        |      -> Default_Route=generate ready
        |
        +-- 任一步失败
               -> 删除临时 smoke 产物
               -> 不写成功 Capability_Evidence
               -> 保留凭据和档案
               -> 返回 Reason_Code + Primary_Action
```

Provider_Smoke 在 v1 只验证 `generate`。Auth_Probe 成功只说明该探测端点接受当前凭据，不能写 Capability_Evidence、不能返回 `ready`，也不能替代图片能力验证。若 registry 没有明确能力声明，直接跳过 Auth_Probe。

### 6.3 首次业务图片惰性验证

```text
configured_unverified + 首张真实业务图片请求
        |
        v
按 Verification_Fingerprint + 规范化目标能力集合进入 single-flight gate
        +-- 已有同 scope 请求在途 -> 等待并共享其成功或失败结果
        +-- 无在途请求 -> 成为唯一验证 owner，生成稳定 operation id
        |
        v
复用 smoke 的验证包装器、错误分类和产物校验
        |
        +-- 图片生成并校验成功
        |      -> 保留图片作为业务交付产物
        |      -> 为实际执行的能力原子合并独立 Capability_Evidence
        |      -> 保留同 fingerprint 下仍有效的其他能力证据
        |      +-- 当前有效证据覆盖 Route/task required capabilities
        |      |      -> 当前 Route ready，放行所有等待页面
        |      +-- 仍缺少当前 Route 所需能力
        |      |      -> 保持 configured_unverified，不扩大证据范围
        |      +-- Capability_Evidence 原子合并失败
        |             -> 保留图片，不重复调用 Provider
        |             -> run lifecycle 保留非敏感恢复证据
        |             -> configured_unverified + 本地证据持久化修复动作
        |
        +-- 图片请求失败
               -> 不写入本次操作对应的成功 Capability_Evidence
               -> 保留主题、材料、大纲、逐页稿和已有中间产物
               -> 返回 Reason_Code + 唯一 Primary_Action
               -> 所有等待页面共享同一失败结果，不发起额外 Provider 请求
               -> 修复后从该图片节点恢复
```

### 6.4 失败分流

| 观测结果 | 状态 | 原因类别 | Primary_Action |
| --- | --- | --- | --- |
| 401 | `invalid` | 鉴权凭据无效 | `run_cli`：`config repair` 从凭据步骤续接 |
| 403 | `invalid` 或 `degraded` | 权限或临时策略拒绝 | `run_cli`：`config repair` 检查权限或切换 Provider |
| 404 | `invalid` | endpoint、路径或 model 不存在 | `run_cli`：`config repair` 回到档案步骤 |
| 429 | `degraded` | 限流或额度不足 | `wait_and_retry`；需要时再运行 Provider 切换命令 |
| 5xx | `degraded` | Provider 服务端错误 | `wait_and_retry` |
| 网络错误 | `degraded` | DNS/TLS/连接失败 | `run_cli`：`config repair` 检查 endpoint/网络 |
| 超时 | `degraded` | Provider 超时 | 仅在重试安全时 `wait_and_retry` |
| 结果未知且 Provider 无幂等保证 | `degraded` | 请求可能已被接受 | `confirm_new_request`；不自动重试 |
| 空产物 | `degraded` | 返回无图片 | `run_cli`：`config verify`；需要时再切换模型 |
| 不可读/格式不支持 | `degraded` | 产物校验失败 | `run_cli`：`config repair` 检查模型兼容性 |
| Capability_Evidence 原子合并失败 | `configured_unverified` | 验证证据持久化失败 | `run_cli`：`config repair` 只合并本地证据；保留业务图片且不得重复调用 Provider |
| 凭据存储失败 | `invalid` | Keychain/DPAPI/ACL 错误 | `run_cli`：`config repair`；不得明文降级 |

正式实现从 reason-code 目录取稳定枚举；不得把 Provider 原始响应或 HTTP 文案直接作为机器合同。

## 7. Verification_Receipt 生命周期

```text
Provider_Smoke 或真实业务图片成功
        |
        v
计算基础 Verification_Fingerprint
  - Provider / endpoint / model / credential version
  - adapter version / verification policy version
  - 不包含验证结果或已验证能力
        |
        v
为本次实际执行的每项能力生成独立 Capability_Evidence
  - capability / verified_at / expires_at
  - operation id / verification source
  - artifact digest / media type / size
        |
        v
原子合并到每 Provider 独立 receipt
  +-- fingerprint 不同 -> 旧 receipt 整体失效，不合并旧能力
  +-- fingerprint 相同 -> 保留其他仍有效能力，只新增或刷新本次能力
        |
        v
每次 status / 安装 / 更新按能力计算有效证据集合
        |
        +-- required capabilities 全部有有效证据 -> passed / 当前 Route ready
        +-- 只有部分能力有有效证据，缺失能力从未验证 -> not_run / configured_unverified
        +-- 至少一项 required capability 的既有证据过期或 fingerprint 变化
        |      -> stale / configured_unverified
        +-- 用户显式 verify 并确认费用 -> 只重新生成 generate 证据
```

v1 默认 Capability Evidence TTL 为成功后的 7 天，Registry 可按 Provider 或能力显式覆盖。receipt 不得包含密钥、鉴权 header、请求正文、完整响应或用户 PPT 材料。业务图片只保存非敏感摘要，图片本身继续由任务产物 owner 管理；smoke 临时图片才在校验后删除。环境变量凭据通过设备本地受保护 Fingerprint_Key 生成 HMAC `credential_version`；具体规则见 [`config-file.md`](./config-file.md)。

## 8. 宿主首次调用守卫与任务恢复

```text
用户在 Agent 中提交 PPT 任务
        |
        v
保存主题、材料、约束、Route、已确认内容与中间产物引用
        |
        v
Host_Readiness_Guard
  1. "<CLI_Path>" config status --json --route <route>
  2. 当前宿主 setup 现场检查 builtin-imagegen，得到独立 Host_Capability_State
        |
        +-- builtin-imagegen 现场可用且覆盖目标能力 -> 继续图片节点
        +-- 当前 Route ready External_Provider -> 继续图片节点
        +-- configured_unverified External_Provider
        |      -> 继续图片节点
        |      -> 首张真实业务图片按 §6.3 惰性验证
        |      +-- 成功 -> 当前 Route ready，继续任务
        |      +-- 失败 -> 保留上下文，停在图片节点
        +-- degraded（仅当前调用或恢复上下文）
        |      -> 保留任务上下文并暂停当前图片节点
        |      -> 原样执行 reason_code 对应的 wait_and_retry、confirm_new_request 或 run_cli
        +-- blocked / invalid
               -> 暂停在第一个需要图片能力的节点
               -> 不丢弃任务状态
               -> 不要求用户在聊天中粘贴 Key
               -> 只输出 run_cli 类型的 Primary_Action 终端命令
               -> 等待用户回复已完成配置
                        |
                        v
                  再次执行 status + setup
                        +-- execution_eligibility=allowed -> 从暂停节点恢复原任务
                        +-- blocked/retryable -> 输出新的唯一动作
```

宿主不能启动向导并代替用户录入密钥，也不能把聊天内容、工具参数或模型上下文变成凭据通道。没有可靠 post-install hook 的宿主，必须在首次需要图片能力时执行本守卫。

Host_Provider 只能由当前宿主现场判定。安装器和宿主外的 `config status` 将 Host_Capability_State 保持为 `unknown`，并可返回 Provider-level Reason_Code `host_check_required`；不能凭配置文件或宿主名称推断其可用，也不能把它写成 External Provider 的 Verification_State。

## 9. 取消、重入与修复

```text
向导任一步取消
  -> 保留此前已原子完成的凭据或档案
  -> 报告最后成功阶段与最早未完成阶段
  -> 返回 config repair 或 config verify

重复运行 config
  +-- 已 ready 且无 change 请求 -> 幂等返回，不做付费调用
  +-- configured_unverified 且无 verify 请求 -> 幂等返回，不做付费调用
  +-- 部分完成 -> 从 Reason_Code 对应步骤继续

config change
  -> 保留原 ready Provider
  -> 本地配置候选 Provider
  +-- 候选达到 configured_unverified -> 可切换并在首张业务图片验证
  +-- 用户明确同意 -> 可先执行 generate-only smoke；成功后仅候选 Provider 的 Default_Route=generate readiness scope 达到 ready，再切换
  +-- 候选失败 -> 原 ready Provider 仍可恢复
```

所有配置、档案和 receipt 写入必须使用权限受限的临时文件、完整校验与原子替换。失败的临时文件不能被后续状态检查当作有效配置。

## 10. 跨平台凭据与敏感数据边界

```text
TTY getpass / 显式 --key-stdin
        |
        | 仅进程内短暂明文
        v
+-----------------------------+
| Credential_Store Adapter    |
+-----------------------------+
        +-- macOS arm64 -> 当前用户 macOS Keychain
        +-- Windows x64 -> 当前用户 DPAPI blob + 严格 ACL

环境变量凭据
        -> config.yaml 只保存 env:<NAME> 引用
        -> 不复制值到 Credential_Store 或日志

允许持久化：
  config.yaml            schema 与非敏感 Provider_Profile
  Credential_Store       平台保护后的 secret
  Verification_Receipt   非敏感验证摘要

禁止流向：
  stdout / stderr / 日志 / 遥测 / 异常正文
  用户 CLI 参数与 shell 历史 / 当前进程或子进程 argv / URL / Agent 聊天与上下文
  普通临时文件 / Skill 目录 / 项目目录 / run 目录 / config.yaml / receipt
  smoke 的完整请求和响应 / 用户 PPT 材料
```

任何平台都不得在安全存储失败时回退为明文文件。

## 11. 用户可见命令路径

```text
leo-ppt config
leo-ppt config status
leo-ppt config verify
leo-ppt config repair
leo-ppt config change
```

实际安装输出和宿主提示必须使用绝对 `CLI_Path`。环境变量名称由正式 CLI 帮助输出。`--key-stdin` 只在用户显式传参时消费一次输入；无该参数时不得读取管道中的普通 stdin。

## 12. 二期可选增强：浏览器配置

二期可以单独评估浏览器配置，但必须重新证明目标用户规模、桌面会话检测、安全边界、跨平台回调、生命周期清理和维护收益。当前阶段：

- 不影响、不替代 `leo-ppt config` 的终端主合同。
- 不进入远程/SSH、CI、无桌面会话和 Agent 宿主恢复链路。
- 不作为安装成功、配置完成或 `ready` 的必要条件。
- 在独立需求、威胁模型和验证方案获批前，不实现 localhost 服务、自动打开浏览器、网页密钥录入或本地回调协议。

## 13. Requirements 逐项流程追踪

| Requirement | 流程覆盖 | 完成判定 |
| --- | --- | --- |
| R1 统一配置入口 | §4、§5.2 | 五个统一命令职责完整，底层能力只被编排 |
| R2 状态模型 | §5 | 配置、作用域验证、执行资格、安装可用性、精确 typed action enum、能力级 readiness、JSON 和退出语义已定义 |
| R3 密钥安全录入 | §4.2、§10 | getpass、环境变量、显式 stdin、禁止进程 argv 和其他秘密禁止流向均有分支 |
| R4 中转站 | §4.3 | endpoint、model、独立凭据与 receipt 失效已覆盖 |
| R5 本地配置检查 | §6.1 | `status` 无外部调用，检查项和多 Provider 选择已覆盖 |
| R6 真实验证 | §6.2-§6.4 | 默认拒绝费用同意、generate-only smoke、可跳过 smoke、single-flight 惰性验证、幂等边界、结果未知和失败恢复已覆盖 |
| R7 receipt | §7 | 基础 fingerprint、逐能力证据、独立 TTL、原子合并、更新复用和显式重验已覆盖 |
| R8 首次安装 | §3.1 | Default Route、External-only ready、CLI 解析、TTY 引导、usable_unverified 和推迟已覆盖 |
| R9 更新检查 | §3.2、§7 | 本地复查不推断 degraded，当前恢复上下文传播 typed action，证据复用与失效已覆盖 |
| R10 非交互配置 | §2、§4.2、§11 | 环境变量、缺失变量原因码、显式 stdin 和无 TTY 结束语义已覆盖 |
| R11 宿主守卫 | §8 | allowed 放行、惰性验证、阻断修复、复查和原任务恢复已覆盖 |
| R12 宿主图片能力 | §5.1、§8 | 独立 Host Capability State、仅现场确认、外部 Provider 降级路径已覆盖 |
| R13 幂等与恢复 | §6.2-§6.4、§9 | operation id、非幂等不重试、取消、重入、部分失败、repair 和 change 回退已覆盖 |
| R14 跨平台存储 | §10 | Keychain、DPAPI、ACL 和禁止明文回退已覆盖 |
| R15 隐私与可观测性 | §6.4、§10 | Reason_Code、非敏感证据和秘密禁止流向已覆盖 |
| R16 Route 兼容性 | §1、§6.1、§8 | Default Route、唯一 Route 能力矩阵、任务级附加能力、Provider 隔离和作用域 readiness 已覆盖 |
| R17 文档一致性 | §11 | 统一命令、三类录入通道与 shell 差异已形成基线 |
| R18 首次发布与回归 | §9、配置文件说明 §10 | 单一 schema v1、开发配置显式重建、不改生成投影已覆盖 |
| R19 Provider Registry | §1、§6.2、配置文件说明 §7.2 | fail-closed 探测、幂等、重试、能力与策略 owner 已覆盖 |

## 14. 流程终止条件

```text
成功终止
  - 安装/更新：Skill=installed 且 Installation_Readiness 明确
  - 配置：Config_Status=ready 或 configured_unverified，且 Execution_Eligibility=allowed
  - 宿主任务：allowed 即可继续；configured_unverified 在首张业务图片完成惰性验证

可恢复终止
  - installed_not_ready + reason_code + 唯一 Primary_Action
  - degraded / invalid + 已保留配置与任务上下文
  - 用户取消 + 已完成步骤 + repair/verify 命令

禁止终止状态
  - 仅因 Skill 激活成功就宣称可生成 PPT
  - 当前 readiness scope 的 required capabilities 未被有效 Capability_Evidence 完整覆盖、且无宿主现场能力覆盖时却返回 ready
  - 用一个能力的成功证据把未验证能力或其他 Route 标记为 ready
  - 未获用户明确肯定同意就发起付费 smoke
  - 同一 Verification Scope 在目标能力证据完整前并发发起多个可能计费请求
  - 把 configured_unverified 当作阻断状态
  - 真实业务图片成功后因 Capability_Evidence 原子合并失败而删除图片或重复计费
  - 配置失败后删除用户已有凭据或档案
  - 要求用户在 Agent 聊天中提交密钥
  - 无 --key-stdin 时隐式读取普通 stdin
  - 依赖浏览器或 localhost 服务完成当前版本配置
```
