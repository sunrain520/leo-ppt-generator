# Leo PPT Generator

面向 Codex 与兼容 Agent 宿主的一站式 PPT Skill。提交文章、报告、图片、PDF 或可信
演示文稿后，它会选择合适流程，生成图片式、对象级可编辑或混合 PPTX，并保留结构、
渲染和人工验收的独立证据。

## 1. 安装

安装器面向 macOS arm64 与 Windows 10/11 x64，不需要管理员权限，也不要求预装
Python。任选一种方式，不要同时安装重复副本；各平台当前实测边界见
[兼容性说明](docs/compatibility.md)。

远程命令以已公开的仓库和 release tag 为准；任一 URL 返回 404 时停止重试，按
[故障处理](docs/troubleshooting.md)确认发布状态。

### 方式 A：Codex Plugin（推荐）

macOS 和 Windows PowerShell 使用相同命令：

```text
codex plugin marketplace add sunrain520/leo-ppt-generator --ref main
codex plugin add leo-ppt-generator@leo-ppt-generator
```

这是一次复制、连续执行的两条命令。生产环境建议把 `main` 换成发布 tag。宿主若明确
提供兼容的 Plugins marketplace 界面，也可在界面中选择 `Leo PPT Generator` 安装；
没有该入口时使用上面的 Codex CLI。安装后开启新对话。

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

安装器自动解析兼容解释器或创建私有 Python 3.12 runtime，验证四条流程后再原子激活。
它不会修改系统 Python、系统 PATH，也不会读取 API Key。安装完成后重新启动宿主或开启
新对话。固定版本、通用 Agent 目录、升级和卸载见[用户教程](docs/user-guide.md)。

安装后不需要再执行初始化命令。首次调用时，Skill 会自动准备私有 runtime、检查当前
宿主能力并返回一个明确结果；若失败，只给一个首选恢复动作。当前 Codex 0.149.0/macOS
已经过全新会话的显式和自然语言触发验证，其他版本与 Windows 的现场边界见
[兼容性说明](docs/compatibility.md)。

## 2. 第一次生成 PPT

在新对话直接提交材料和目标，例如：

> 使用 `$leo-ppt-generator` 把这份季度复盘做成 12 页、面向管理层的 PPT，先确认大纲和样张。

Agent 会自动完成 runtime 初始化、能力检查、流程选择和恢复判断。普通用户不需要运行
初始化命令、不需要编辑配置文件，也不需要手写 backend JSON。

标准流程是：提交材料和受众目标 → 确认大纲与完整逐页内容 → 确认视觉方向和图片能力
→ 批准一页样张 → 生成整套 → 逐页检查并交付 PPTX。切换图片服务后必须重新确认样张。

四种交付流程：

- `generate`：文章、报告、笔记或大纲生成图片式 PPTX。
- `direct-editable`：图片、PDF 或用户确认可信的 PPTX 重建为对象级可编辑 PPTX。
- `upgrade-full`：把已完成的图片式演示文稿整套升级为可编辑版本。
- `upgrade-selected`：只升级指定页，其他页保留图片。

## 3. 密钥：按需配置，不要一次配齐

| 档位 | 何时使用 | 用户动作 |
| --- | --- | --- |
| 零密钥 | 当前宿主明确提供图片生成能力 | 无；Agent 自动优先使用 |
| 一个图片密钥 | 宿主图片能力不可用 | OpenAI 与 AtlasCloud 二选一 |
| 可选 OCR | 可编辑转换实际需要在线文字识别增强 | 可选 PaddleOCR；缺失时使用本地 `builtin-ink` |

获取入口：

- OpenAI：[创建 API Key](https://platform.openai.com/api-keys)；[计费设置](https://platform.openai.com/settings/organization/billing/overview)
- AtlasCloud：[注册或登录](https://www.atlascloud.ai/)；[模型列表](https://www.atlascloud.ai/zh/models)
- PaddleOCR：[申请 Access Token](https://aistudio.baidu.com/account/accessToken)

需要凭据时，setup 会返回 `image_provider_configuration_required`，Agent 只会给出
一条包含准确 CLI 路径、在本地交互式终端执行的 `auth add` 命令。OpenAI 与
AtlasCloud 只需二选一。密钥通过隐藏输入写入 macOS Keychain 或 Windows 当前用户
DPAPI；不会写入项目、Skill、普通配置、run、日志或聊天。不要把密钥粘贴到聊天、
命令参数或 pipe 中。

环境变量 `OPENAI_API_KEY`、`ATLASCLOUD_API_KEY`、`PADDLE_OCR_TOKEN` 仍是无持久化
兼容入口，但不是普通用户首选路径。服务商地区、权限、额度与价格以各服务商当前页面
为准。

## 4. 质量与证据边界

流程不会因为 PPTX “能打开”就声明完成。图片式生成必须确认大纲、完整逐页内容、风格、
图片 Provider 和一个样张；切换 Provider 后必须重新确认样张。最终产物分别关闭：

- 内容事实与叙事；
- 逐页文字、图表、对比度、遮挡和可读性；
- 页数、页序、尺寸、notes、媒体引用和 hash；
- 真实 Provider/OCR、PowerPoint 桌面和人工视觉验收。

离线测试或结构验证不能替代真实服务、桌面客户端和人工判断。未执行项必须明确标为
`not-run`。

## 5. 帮助与开发

- [完整用户教程](docs/user-guide.md)
- [故障处理](docs/troubleshooting.md)
- [兼容性](docs/compatibility.md)
- [已知限制](docs/limitations.md)
- [测试方案与证据分层](docs/testing.md)

开发者可运行：

```bash
python scripts/build_release.py --output dist
python scripts/validate_release.py dist/release-manifest.json
```

构建器从唯一 canonical Skill tree 生成 standalone 与 Plugin 两个归档；验证器要求两者
tree hash 完全一致，并核对版本、许可证与 bootstrap 校验和。

## 许可证

本项目使用 [MIT License](LICENSE)。
