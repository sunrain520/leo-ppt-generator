# 首次使用

本页只供 Agent 执行首次准备；不要把内部步骤逐条转述给普通用户。用户主路径始终是
“提交材料和目标 → 必要确认 → 获得经验证 PPTX”。

## 自动准备

1. 从宿主提供的当前 `SKILL.md` 绝对路径解析 Skill root，不从 cwd、仓库名或 PATH
   猜测。
2. macOS/POSIX 调用 `<Skill root>/scripts/leo-bootstrap.sh`；Windows PowerShell 调用
   `& "<Skill root>\scripts\leo-bootstrap.ps1"`。launcher 的默认动作包含 runtime
   ensure，并返回 `leo-ppt-bootstrap/v1`。
3. 只从成功结果读取绝对 `cli_reference`，不得再调用 `print-cli` 或从 PATH 猜测。
4. 使用该 CLI 运行 `setup --route <route> --host-imagegen <三态> --json`。任务需要
   mask 时增加 `--require-mask`；editable 阶段实际需要在线文字 hints 时才增加
   `--ocr-requirement editable_text_hints`。
5. 每个非 ready 结果只执行 `primary_action`；保留原任务上下文，动作通过后重新运行
   setup。不得把 `details.alternatives` 同时变成多个用户步骤。

launcher 或 setup blocked 时，向用户说明一个 reason code 和唯一下一步；不要输出
Python、venv、runtime identity、内部目录或多条诊断命令，除非用户明确要求高级诊断。

## 宿主与 Provider

- 合格的已配置外部 Provider 优先于宿主 `builtin-imagegen`；没有合格外部 Provider
  时，宿主明确声明 available 才能作为兜底；unknown 先核实，不能推测为 available。
- 统一配置入口是 `leo-ppt config`。读取 `config status --json --route <route>`：
  `configured_unverified` 表示本地配置完整、`execution_eligibility=allowed`、
  `installation_readiness=usable_unverified`，允许开始任务，首张真实业务图片承担
  惰性验证；`ready` 只表示当前 Route 所需能力已被有效 evidence 或宿主现场能力完整
  覆盖。`not_configured`/`invalid` 暂停图片节点，只给一个 `run_cli` Primary_Action
  终端命令。
- 宿主不得代替用户录入密钥，也不得把聊天内容、工具参数或模型上下文变成凭据通道。
  用户必须在本地终端运行返回的命令；完成后复查 `config status`，`allowed` 时从原
  节点恢复任务。
- 首次配置或缺少 Provider profile 时运行 `config`；指定 Provider 使用
  `config provider configure --provider <provider>`；已有 profile 的切换使用
  `config provider select --provider <provider>`。凭据只通过
  `config credential set/status/remove` 管理。不得向普通用户生成历史 `auth`、顶层
  `provider configure` 或 `config change`。
- `config reset --confirm` 只用于用户明确要求重建非敏感配置；它保留系统凭据，不得由
  Agent 根据普通配置失败自动执行。
- 选择 `openai-compatible` 时，先用 HTTPS API base URL 与模型名配置 profile；任意
  用户配置的 endpoint 默认不自动 probe、不查询模型列表、不幂等重试。配置完成后，
  单一合格 Provider 自动选中；多个合格 Provider 按 priority 选择，最高优先级并列时
  才要求补充配置。用户拒绝外部服务时停止，不要求配置。
- 环境中后来出现新 secret 不改变已冻结 run。切换图片 Provider 或 generation method
  后必须重新生成并确认样张。
- OCR 不参与图片 Provider 选择。图片式 generate 不询问 PaddleOCR；editable 阶段仅把
  它作为可选增强，缺失时说明使用本地 `builtin-ink`，不把它变成阻断项。

## 安全凭据动作

用户必须在本地交互式终端执行，不能在聊天、命令参数或 pipe 中传 secret：

- macOS/POSIX：`"<bootstrap 返回的 cli_reference>" config`
- Windows PowerShell：`& "<bootstrap 返回的 cli_reference>" config`

向导默认不发起付费验证；只有用户在真实 TTY 中明确同意时，`config verify --yes` 才执行
generate-only smoke（默认“否”）。已存在凭据时，只有用户确认覆盖后才写入新值。
完成后由 Agent 运行 `config status --json` 并回到原任务。状态输出只允许引用和
`available|missing`，不得读取、显示或记录 secret value。

OS store 保护边界不包括已取得同一用户会话权限的恶意进程。疑似账户或本机会话失陷
时停止执行，撤销服务商凭据并删除本地引用，不声称 Keychain/DPAPI 仍能提供保护。

## 必要确认上限

首次流程最多询问两个真正改变结果的问题：任务/route 必要信息，以及 Provider 或样张
确认。用户要求跳过样张时仍不能跳过；这是生成一致性与最终验收合同，不是 setup 障碍。
