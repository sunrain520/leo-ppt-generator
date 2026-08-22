# 故障处理

先看失败结果中的 `reason_code` 和 `primary_action`。每次只执行一个首选动作，验证条件
通过后回到原任务；不要同时尝试多套命令，也不要删除整个 Skill、runtime home 或 run。

## 安装与发现

| 现象或原因码 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| 新安装后找不到 Skill/Plugin | 重新启动宿主或开启新对话 | 只发现一个 `leo-ppt-generator` |
| GitHub 仓库、安装脚本或 Skill URL 返回 404 | 停止重试，改用维护者已发布的固定 tag；若尚无 tag，等待公开发布 | 仓库、tag 与三个安装 URL 均可匿名访问 |
| 高级隔离测试显式设置的 `CODEX_HOME` 不存在 | 先创建该精确目录，再重跑同一 Plugin 命令 | Codex CLI 能加载隔离配置且不读取日常用户目录 |
| 同名目录、双发现目录或可发现 backup | 把旧副本移出发现目录并保留备份 | 默认目录和通用目录合计只有一个活动副本 |
| `bootstrap_platform_unsupported` | 切换到 macOS arm64 或 Windows 10/11 x64 | launcher 平台检查通过 |
| `bootstrap_download_failed` | 检查网络/代理后重跑同一 launcher | 固定工件完整下载并通过 SHA-256 |
| `bootstrap_artifact_hash_mismatch` | 停止执行并重新安装可信发布版本 | 下载 hash 与 bundle manifest 一致 |
| `bootstrap_home_unwritable` | 把 `LEO_PPT_HOME` 设为当前用户可写目录 | bootstrap 可创建私有 stage/runtime |
| `bootstrap_lock_timeout` | 确认没有活动安装后处理错误中给出的精确锁 | 同一 home 只有一个 bootstrap writer |

安装或升级失败不会删除当前健康版本。不要手工修改 `current.json`，不要递归清理 Skill
父目录。需要回滚时使用安装器保留的隐藏备份或受管 runtime rollback。

安装完成后的最小发现验证是在新对话中发送：

> 使用 `$leo-ppt-generator` 把这篇文章生成 8 页 PPT，先给大纲和样张。

也可直接说“把这篇文章生成高质量 PPTX”验证自然语言触发。若两种方式都未识别，只执行
表格中的“重新启动宿主或开启新对话”，再确认发现目录中只有一个同名 Skill；不要重复
安装多个副本。

## 宿主与 Provider

| 原因码 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| `host_image_capability_unknown` | 由当前宿主明确声明 available 或 unavailable | setup 不再返回 unknown |
| `image_provider_configuration_required` | 在本地终端为 OpenAI 或 AtlasCloud 二选一执行 `auth add` | 所选 Provider 状态为 available |
| `provider_confirmation_required` | 明确确认 setup 返回的唯一可用 Provider | `selected_provider` 与用户选择一致 |
| `provider_choice_required` | 在可用候选中选择一个 | 不按环境中偶然存在的密钥静默选择 |
| `provider_capability_required` | 选择满足 mask/reference 要求的候选 | Provider capability 覆盖 `route_capabilities` |
| `provider_field_smoke_required` | 用冻结合同执行一次真实 smoke | receipt 绑定 Provider、model 和产物 hash |

PaddleOCR 缺失不会阻断图片式生成。只有 editable 阶段实际需要在线文字 hints 时才配置；
否则保持本地 `builtin-ink`。

处理 `image_provider_configuration_required` 时，从 setup 结果复制准确的
`cli_reference`，然后在本地交互式终端只执行其中一个：

```bash
"<cli_reference>" auth add --provider openai
```

```powershell
& "<cli_reference>" auth add --provider openai
```

选择 AtlasCloud 时把 provider 改为 `atlascloud`。不要把密钥放进聊天、命令参数、
重定向或 pipe；隐藏输入成功后回到原任务，不需要重装 Skill。

## 凭据

| 原因码 | 唯一首选动作 | 通过条件 |
| --- | --- | --- |
| `credential_tty_required` | 在本地交互式终端重新执行命令 | 隐藏输入启动，不从聊天/参数/pipe 读取 |
| `credential_overwrite_confirmation_required` | 核对 Provider 后显式加 `--overwrite` | OS store 中只有该 Provider 的新引用 |
| `credential_store_locked` | 解锁 Keychain/当前用户凭据服务 | `auth status` 返回 available 或 missing |
| `credential_store_acl_too_broad` | 收窄 Windows 凭据目录和 blob ACL | 仅当前用户可访问后重新验证 |
| `credential_blob_invalid` | 删除损坏引用并在当前 Windows 用户下重建 | DPAPI 解密和 Provider status 通过 |
| `credential_reference_unavailable` | 恢复同一冻结 Provider 的凭据 | 不切换 run，不重新使用旧 receipt |

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
和失败时间；不要附带正文、完整环境、Keychain/DPAPI blob 或任何 secret。
