# Leo PPT Generator

## 1. 安装

Leo PPT Generator 面向 macOS arm64 与 Windows 10/11 x64；不需要管理员权限，也不要求预装 Python。请选择 **一种** 安装方式，不要同时安装重复副本，也不要同时保留 Plugin 与 standalone Skill。各平台与宿主的现场验证边界见[兼容性说明](docs/compatibility.md)。

远程命令以已公开的仓库和 release tag 为准；任一 URL 返回 404 时停止重试，按[故障处理](docs/troubleshooting.md)确认发布状态与唯一恢复动作。

### 方式 A：Codex Plugin（推荐）

macOS 和 Windows PowerShell 使用相同命令：

```text
codex plugin marketplace add sunrain520/leo-ppt-generator --ref main
codex plugin add leo-ppt-generator@leo-ppt-generator
```

这是一次复制、连续执行的两条命令。生产环境建议将 `main` 换为发布 tag。宿主若明确提供兼容的 Plugins marketplace 界面，也可在界面中选择 `Leo PPT Generator`；没有该入口时使用上面的 Codex CLI。安装后重新启动宿主或开启下一轮对话。

### 方式 B：standalone Skill

在 Codex 中发送：

> 请使用 `skill-installer` 从以下地址安装：  
> https://github.com/sunrain520/leo-ppt-generator/tree/main/skills/leo-ppt-generator

或在终端一键安装。

macOS：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1 | iex
```

安装器会解析兼容解释器或创建私有 Python 3.12 runtime，完成本地 route 检查后再原子激活。macOS standalone 安装还会在 `~/.local/bin` 创建稳定的 `leo-ppt` 用户命令，使 `leo-ppt config` 在 runtime 升级后仍自动指向当前版本；安装器不会改写系统 Python 或系统 PATH，若该目录不在 PATH 会给出明确提示。安装器不会读取 API Key。固定版本、通用 Agent 目录、升级和卸载见[用户教程](docs/user-guide.md)。

**安装成功不等于图片服务已经就绪。** 安装或更新后的本地检查会把状态分开说明：

- `ready`：当前 route 所需能力已有匹配的真实证据，或由当前宿主现场确认；
- `configured_unverified`：本地配置完整、可以开始任务；第一次真实业务图片会完成惰性验证；
- `installed_not_ready`：当前图片能力尚不能执行；遵循输出中的唯一首选动作即可。

安装后不需要手工拼接初始化命令。首次调用时，Skill 会自动准备 runtime、检查当前宿主能力并给出明确结果；若需要终端操作，Agent 只会给出一条准确的本地命令。不要因为状态不是 `ready` 而反复安装或重复配置。

安装后的稳定命令入口：

```bash
leo-ppt version
leo-ppt update --check
leo-ppt config
leo-ppt config status --route generate
```

`version` 查看当前版本；`update` 检查或原子更新安装；`rollback` 回到上一健康 runtime；
`config` 负责 Provider、凭据和验证。更新不会删除配置、Keychain/DPAPI 凭据或用户 run。

## 2. 第一次生成 PPT

在新对话直接提交材料和目标，例如：

> 使用 `$leo-ppt-generator` 把这份季度复盘做成 12 页、面向管理层的 PPT，先确认大纲和样张。

Agent 会自动完成 runtime 初始化、能力检查、流程选择和恢复判断。普通用户不需要运行初始化命令、不需要编辑配置文件，也不需要手写 backend JSON。

标准流程是：提交材料和受众目标 → 确认大纲与完整逐页内容 → 确认视觉方向和图片能力 → 批准一页样张 → 生成整套 → 逐页检查并交付 PPTX。切换图片服务、模型或主要风格后必须重新确认样张。

图片能力按当前现场状态决定：

- 宿主明确提供图片生成能力时，优先使用它，无需外部密钥；
- 外部 Provider 已配置但未验证时，可以继续到首张业务图片；成功后该 route 升级为 `ready`；
- 宿主能力为 `unknown` 时，系统不会猜测为可用，而会给出一个确认或配置动作；
- 首张图片验证失败时，会保留主题、材料、大纲、逐页稿和已完成产物；修复后从图片节点恢复，不要求重新开始。

四种交付流程：

- `generate`：文章、报告、笔记或大纲生成图片式 PPTX。
- `direct-editable`：图片、PDF 或用户确认可信的 PPTX 重建为对象级可编辑 PPTX。
- `upgrade-full`：把已完成的图片式演示文稿整套升级为可编辑版本。
- `upgrade-selected`：只升级指定页，其他页保留图片。

## 3. 密钥：按需配置，不要一次配齐

| 档位 | 何时使用 | 用户动作 |
| --- | --- | --- |
| 零密钥 | 当前宿主明确提供图片生成能力 | 无；Agent 自动优先使用 |
| 一个图片密钥 | 宿主图片能力不可用 | 官方 OpenAI、OpenAI-compatible 中转站与 AtlasCloud 三选一 |
| 可选 OCR | 可编辑转换实际需要在线文字识别增强 | 可选 PaddleOCR；缺失时使用本地 `builtin-ink` |

获取入口：

- OpenAI：[创建 API Key](https://platform.openai.com/api-keys)；[计费设置](https://platform.openai.com/settings/organization/billing/overview)
- OpenAI-compatible 中转站：准备 HTTPS API Base URL、该站实际支持的图片模型名和 API Key
- AtlasCloud：[注册或登录](https://www.atlascloud.ai/)；[模型列表](https://www.atlascloud.ai/zh/models)
- PaddleOCR：[申请 Access Token](https://aistudio.baidu.com/account/accessToken)

普通用户的配置路径是 `leo-ppt config` 命令组，而不是手动组合底层 `auth`、顶层
`provider` 或 backend 命令。`config provider configure/select/list/remove` 管 Provider，
`config credential set/status/remove` 管凭据引用，`config status` 只检查本地状态，
`config repair` 按当前原因恢复。`config verify --yes` 才表示对本次可能计费验证的明确同意；
若当前 runtime 没有可用的 smoke executor，命令会停止而不会伪造 `ready`。

可能计费的 Provider smoke 只会在你**明确同意**时执行。默认回车、超时、取消、安装、更新和宿主调用均不构成同意；跳过 smoke 是成功的配置结果，首次真实业务图片会在同一安全边界内惰性验证。

密钥只可通过真实 TTY 的隐藏输入、已存在的环境变量引用，或你显式选择的 `--key-stdin` 通道提供。密钥会保存到 macOS Keychain 或 Windows 当前用户 DPAPI 保护的存储；不会写入项目、Skill、普通配置、run、日志或聊天。**不要**把密钥粘贴到聊天、命令行参数、URL 查询参数，或让普通 stdin 被隐式读取。

环境变量 `OPENAI_API_KEY`、`OPENAI_COMPATIBLE_API_KEY`、`ATLASCLOUD_API_KEY`、`PADDLE_OCR_TOKEN` 仍是无持久化兼容入口，但不是普通用户首选路径。服务商地区、权限、额度与价格以各服务商当前页面为准。

## 4. 质量与证据边界

流程不会因为 PPTX“能打开”或 `config status` 成功退出就声明完成。`ready` 只覆盖当前 route 所需、已有有效证据的能力；一个 `generate` 证据不自动证明 `edit`、`mask` 或 `reference`。

图片式生成必须确认大纲、完整逐页内容、风格、图片 Provider 和一个样张。最终产物分别关闭：

- 内容事实与叙事；
- 逐页文字、图表、对比度、遮挡和可读性；
- 页数、页序、尺寸、notes、媒体引用和 hash；
- 真实 Provider/OCR、PowerPoint 桌面和人工视觉验收。

安装、本地配置、真实 Provider/OCR、PowerPoint 与人工验收是彼此独立的证据层。离线测试或结构验证不能替代真实服务、桌面客户端和人工判断；未执行项必须明确标为 `not-run`。

## 5. 帮助

- [完整用户教程](docs/user-guide.md)
- [端到端逻辑流程](docs/skill-workflow.md)
- [故障处理](docs/troubleshooting.md)
- [兼容性](docs/compatibility.md)
- [已知限制](docs/limitations.md)
- [测试方案与证据分层](docs/testing.md)

## 许可证

本项目使用 [MIT License](LICENSE)。
