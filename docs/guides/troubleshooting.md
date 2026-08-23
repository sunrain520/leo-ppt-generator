# 故障处理

先看本次结果中的 `reason_code` 和 `primary_action`。普通用户每次只执行一个首选动作，
完成后回到原任务；不要并行尝试多套命令，也不要删除整个 Skill、`LEO_PPT_HOME`、runtime
home、凭据或 run。

## 先做无费用检查

由安装器或 launcher 返回的绝对 `cli_reference` 是唯一可信 CLI 路径。下列命令中的
`<CLI>` 代表该路径；不要从 PATH、当前仓库或旧教程猜测 `leo-ppt` 的位置。

```bash
"<CLI>" config status --route generate --json
```

`config status` 只检查本地配置、凭据引用、Provider 档案、当前 route 能力和 receipt
新鲜度，不调用 Provider，也不产生费用。根据结果仅走一条路径：

| 状态 | 含义 | 唯一首选动作 |
| --- | --- | --- |
| `ready` | 当前 route 所需能力已有有效证据，或当前宿主已现场确认 Host Provider | 开始或恢复原 PPT 任务 |
| `configured_unverified` | 本地配置完整，`execution_eligibility=allowed`、`installation_readiness=usable_unverified` | 开始原任务；首张真实业务图片会惰性验证 |
| `not_configured`、`invalid` | 当前 route 缺少安全凭据、非敏感档案或有效配置 | 执行结果的 `primary_action`，通常是 `config` 或 `config repair` |
| `degraded` | 当前 Provider 调用或恢复上下文可重试，但本地配置未必损坏 | 仅执行 `wait_and_retry`、`confirm_new_request` 或 `run_cli` 类型的 `primary_action` |

`config status` 的成功退出仅表示检查完成；自动化必须读取 `leo-ppt-config/v1` 的
`status`、`execution_eligibility` 和 `readiness_scope`，不能只看 exit code。纯本地检查在
配置完整但缺少证据时应返回 `configured_unverified`，不会从历史失败猜测 `degraded`。

## 安装与发现

| 现象或原因码 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| 新安装后找不到 Skill/Plugin | 重新启动宿主或开启新对话 | 只发现一个 `leo-ppt-generator` |
| GitHub 仓库、安装脚本或 Skill URL 返回 404 | 停止重试，改用维护者已发布的固定 tag；若尚无 tag，等待公开发布 | 仓库、tag 与三个安装 URL 均可匿名访问 |
| 高级隔离测试显式设置的 `CODEX_HOME` 不存在 | 先创建该精确目录，再重跑同一 Plugin 命令 | Codex CLI 能加载隔离配置且不读取日常用户目录 |
| 同名目录、双发现目录或可发现 backup | 把旧副本移出发现目录并保留备份 | 默认目录和通用目录合计只有一个活动副本 |
| `bootstrap_platform_unsupported` | 切换到 macOS arm64/x86_64 或 Windows 10/11 x64 | launcher 平台检查通过 |
| `bootstrap_download_failed` | 检查网络/代理后重跑同一 launcher | 固定工件完整下载并通过 SHA-256 |
| `bootstrap_artifact_hash_mismatch` | 停止执行并重新安装可信发布版本 | 下载 hash 与 bundle manifest 一致 |
| `bootstrap_home_unwritable` | 把 `LEO_PPT_HOME` 设为当前用户可写目录 | bootstrap 可创建私有 stage/runtime |
| `bootstrap_lock_timeout` | 确认没有活动安装后处理错误中给出的精确锁 | 同一 home 只有一个 bootstrap writer |
| 不确定当前版本 | 运行 `"<CLI>" version` | 输出 package/runtime 与 config/setup schema 版本 |
| 检查更新 | 运行 `"<CLI>" update --check` | 返回 `leo-ppt-update/v1`，不修改安装 |
| 更新前预览 | 运行 `"<CLI>" update --dry-run --version <tag>` | 展示当前/目标版本且不激活 |
| 执行更新 | 审阅后运行 `"<CLI>" update --yes --version <tag>` | 新 Skill 完成 stage、验证和原子激活 |
| 新版本异常 | 运行 `"<CLI>" rollback` | current 切回上一健康 runtime |

安装或升级失败不会删除当前健康版本。不要手工修改 `current.json`，不要递归清理 Skill
父目录。需要回滚时使用安装器保留的隐藏备份或受管 runtime rollback。

安装完成后的最小发现验证是在新对话中发送：

> 使用 `$leo-ppt-generator` 把这篇文章生成 8 页 PPT，先给大纲和样张。

也可直接说“把这篇文章生成高质量 PPTX”验证自然语言触发。若两种方式都未识别，只执行
表格中的“重新启动宿主或开启新对话”，再确认发现目录中只有一个同名 Skill；不要重复
安装多个副本。

## Provider 与配置恢复

| 原因码或现象 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| `host_image_capability_unknown` | 由当前宿主明确声明 `available` 或 `unavailable` | setup 不再返回 `unknown` |
| `image_provider_configuration_required`、`provider_selection_required` | 在本地交互式终端运行 `"<CLI>" config` | 当前 Provider 已选定且本地检查完整 |
| `openai_compatible_configuration_required` | 运行 `"<CLI>" config` 并选择 OpenAI-compatible | HTTPS endpoint、模型和独立凭据引用有效 |
| `provider_capability_required` | 用 `config provider select` 选择覆盖当前 `--route` 所需能力的 Provider | `readiness_scope.missing_capabilities` 为空，或允许惰性验证 |
| `provider_field_smoke_required` | 仅在已决定为这一次操作付费时运行 `"<CLI>" config verify --route generate --yes` | `generate` receipt 绑定当前 Provider、模型与能力 |
| 真实业务图片成功但 receipt 写入失败 | 执行结果给出的 `config repair` | 只用本地图片与 run 恢复证据写回 receipt，不再次调用 Provider |
| `provider_outcome_unknown` | 由用户明确决定是否发起新请求 | 未获得幂等保证时不自动重试可能计费的调用 |

配置向导的首选入口为：

```bash
"<CLI>" config
```

`config verify --yes` 是一次独立的、当前操作范围内的可能计费 smoke 同意。默认回车、超时、
取消、安装、升级和宿主调用均不是同意。跳过 smoke 不代表取消配置：当本地配置完整时，
结果应为 `configured_unverified`，任务可以进入图片节点；同一 Verification Scope 的首张
真实业务图片通过 single-flight 惰性验证，其他并发页面共享该结果。

需要改 Provider 或非敏感档案时使用：

```bash
"<CLI>" config provider select --provider openai
"<CLI>" config provider select --provider openai-compatible
"<CLI>" config provider select --provider atlascloud
```

OpenAI-compatible 中转站必须使用不含用户名、密码、查询参数或 fragment 的 HTTPS origin，
并配置独立模型和凭据引用。Registry 未明确声明 endpoint-specific 探测、模型发现、幂等
或重试策略时均为 `unknown`，不会通过试调用猜测可用性。

`auth add/status/remove`、顶层 `provider configure` 与 `config change` 只保留为兼容入口；
它们不是普通用户的恢复主路径。使用这些入口时也必须遵守本节相同的凭据边界和
`primary_action`，不要把多个候选修复方案同时展示给用户。

PaddleOCR 缺失不会阻断图片式生成。只有 editable 阶段实际需要在线文字 hints 时才配置；
否则保持本地 `builtin-ink`。

## 凭据与非交互配置

| 原因码 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| `credential_tty_required`、`credential_input_channel_unavailable` | 在本地 TTY 运行 `"<CLI>" config`，或使用既有环境变量引用/用户显式 `--key-stdin` | 密钥仅经允许通道生成非敏感 Credential Reference |
| `credential_environment_missing` | 执行结果的 `config repair`，恢复当前进程可见的环境变量或 OS store 引用 | 目标 Provider 的引用可解析 |
| `credential_overwrite_confirmation_required` | 核对 Provider 后显式确认覆盖 | OS store 中只有该 Provider 的新引用，旧 receipt 失效 |
| `credential_store_locked` | 解锁 Keychain/当前用户凭据服务 | 配置检查能读取 `available` 或 `missing` 状态 |
| `credential_store_acl_too_broad` | 收窄 Windows 凭据目录和 blob ACL | 仅当前用户可访问后重新检查 |
| `credential_blob_invalid` | 在当前 Windows 用户下通过 `config repair` 重建损坏引用 | DPAPI 解密和 Provider status 通过 |
| `credential_reference_unavailable` | 恢复同一冻结 Provider 的凭据 | 不切换既有 run，不复用旧 receipt |
| 只需重建非敏感配置 | 运行 `"<CLI>" config reset --confirm` | Provider profile 和 receipt 已重建，Keychain/DPAPI 凭据保持不变 |

允许的密钥通道只有真实 TTY 的隐藏输入、既有环境变量引用，以及用户**显式**选择的
`--key-stdin`。禁止在聊天、明文参数、URL 参数、普通 stdin 的隐式读取、重定向或
未确认的 pipe 中传递密钥。`config.yaml`、项目目录、run、receipt、日志和 issue 都不能
保存原始密钥、长度、前后缀或裸 hash。

怀疑服务商账户或当前用户会话失陷时，停止执行，先在服务商撤销密钥，再删除本地引用。
Keychain/DPAPI 不承诺抵御已取得同一用户会话权限的恶意进程。

## Run 与交付

- 响应丢失：先查 `run operation` 或 `run status`，不要换 idempotency key 重建。
- 页面失败：只在 `safe_to_retry=true` 时用同一 run 重试失败页。
- Provider 切换：创建新确认并重新做样张；旧样张不能沿用。
- 最终图片变化：创建新 artifact revision，重新组装、渲染和验收 PPTX。
- `acceptance_pending`：补真实渲染和人工 receipt；结构通过不能替代。
- `artifact_invalid`：先修复结构/hash，不得用人工 receipt 绕过。
- 清理：先 dry-run，再对完全相同 fingerprint apply；input 清理仅限 terminal run 且不可恢复。

仍无法恢复时，保存非敏感的 `reason_code`、route、stage、runtime identity、manifest/hash
和失败时间；不要附带正文、完整环境、Keychain/DPAPI blob、Provider 原始响应或任何
secret。
