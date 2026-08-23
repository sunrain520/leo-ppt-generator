# Leo PPT Generator 用户教程

## 1. 安装 Skill 与首次验证

### 1.1 选择一种简单安装方式

安装器面向 macOS arm64/x86_64 与 Windows 10/11 x64，不需要管理员权限或预装 Python。Plugin 与 standalone Skill 二选一，不要同时保留重复副本；各平台现场验证状态见[兼容性说明](compatibility.md)。

远程安装以已公开的仓库和 release tag 为准。仓库、Skill 路径或脚本 URL 返回 404 表示该 revision 尚未公开可安装；停止重试并查看[故障处理](troubleshooting.md)。

方式一（推荐），安装 Codex Plugin：

```text
codex plugin marketplace add sunrain520/leo-ppt-generator --ref main
codex plugin add leo-ppt-generator@leo-ppt-generator
```

把两行作为一次安装连续执行。生产使用时将 `main` 换为固定 release tag。安装后开启新对话。宿主若明确提供兼容的 Plugins marketplace 界面，也可在界面中选择 `Leo PPT Generator`；没有该入口时使用上面的 Codex CLI。

方式二，安装 standalone Skill。在 Codex 中发送下面这句话：

> 请使用 `skill-installer` 从以下地址安装：  
> https://github.com/sunrain520/leo-ppt-generator/tree/main/skills/leo-ppt-generator

`skill-installer` 会安装到 `$CODEX_HOME/skills/leo-ppt-generator`；未设置 `CODEX_HOME` 时默认为 `~/.codex/skills/leo-ppt-generator`。同名目录已经存在时会拒绝覆盖。安装成功后开启下一轮 Codex 对话，首次使用会自动初始化 runtime。

不要对同一目标并发运行多个安装器；安装器会让竞争者 fail closed。Bash 进程被强制终止后，下一次可能报告 `.leo-ppt-generator.install.lock`；先确认没有活动安装进程，再只移除错误信息给出的精确锁目录，不能递归清理整个 Skill 父目录。

方式三，在终端一键安装 standalone Skill。

macOS arm64：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash
```

Windows 10/11 x64（PowerShell）：

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1 | iex
```

脚本自动完成平台检查、兼容解释器解析或私有 Python 3.12 安装、runtime 初始化、四条 route 本地检查和原子安装，不需要 `sudo`。它不会读取或保存 API key。macOS standalone 安装同时在 `${LEO_PPT_BIN_DIR:-$HOME/.local/bin}` 创建稳定的 `leo-ppt` 用户命令；该命令每次解析当前受管 runtime，因此升级后仍可直接运行 `leo-ppt config`。安装器不会改写系统 PATH；若命令目录尚未在 PATH，安装结果会输出需要加入 shell 配置的一行。希望先审阅脚本再执行时：

```bash
curl -fsSLO https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh
less install.sh
bash install.sh
```

Windows 用户可先下载、查看再执行：

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1 -OutFile install.ps1
Get-Content .\install.ps1
.\install.ps1
```

安装到通用 Agent Skill 发现目录：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash -s -- --agents
```

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1))) -Agents
```

该目标为 `$HOME/.agents/skills/leo-ppt-generator`。不要同时保留 Codex 目录和通用目录两份副本。固定版本时，将两处占位符替换为同一个 release tag 或 commit：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/<commit-or-tag>/install.sh \
  | bash -s -- --ref <commit-or-tag>
```

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/<commit-or-tag>/install.ps1 -OutFile install.ps1
.\install.ps1 -Ref <commit-or-tag>
```

使用 `main` 获得最新版本；生产环境推荐固定版本。若已 checkout 本仓库，在仓库根目录 macOS 运行 `bash install.sh`，Windows 运行 `.\install.ps1`，即可使用本地 bundle。安装后重新启动 Codex，或至少开启下一轮对话，确认只出现一个 `leo-ppt-generator`。

### 1.2 安装后的状态与自动引导

安装或更新成功表示 Skill 已激活，**不表示**图片服务已经真实可用。普通用户只需在新对话提出 PPT 任务：

> 使用 `$leo-ppt-generator` 把这份材料做成 12 页、面向管理层的 PPT，先确认大纲和样张。

Agent 会调用当前平台 launcher、解析受管 CLI 路径，并执行只读本地检查。macOS standalone 用户可直接使用安装器创建的短命令；Agent、Plugin 与自动化仍应使用 launcher 返回的准确绝对路径：

```bash
leo-ppt config status --route generate --json
```

```powershell
& "<cli_reference>" config status --route generate --json
```

`config status` 不会调用 Provider，也不会产生费用；其成功退出只表示检查完成，自动化还必须读取 `status` 与 `execution_eligibility`。主要结果如下：

| 结果 | 含义 | 下一步 |
| --- | --- | --- |
| `ready` | 当前 route 所需能力已有有效真实证据，或当前宿主已现场确认能力 | 可以继续任务 |
| `configured_unverified` | 本地配置完整，真实能力尚未被当前 scope 证明 | 可以继续；首张真实业务图片惰性验证 |
| `installed_not_ready` | 当前 route 为 `blocked` 或 `retryable` | 只执行输出中的一个 `primary_action` |
| 宿主能力 `unknown` | 宿主没有现场声明可用或不可用 | 不会被猜测为可用；按提示确认或配置 |

若不存在真实 TTY，安装与宿主守卫不会等待输入，也不会隐式读取 stdin。它会给出一个可执行的终端动作，或说明环境变量引用与显式 `--key-stdin` 通道。不要重复安装来解决配置状态。

只有高级诊断才需手动运行 launcher：

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/leo-ppt-generator/scripts/leo-bootstrap.sh"
```

```powershell
& "$env:USERPROFILE\.codex\skills\leo-ppt-generator\scripts\leo-bootstrap.ps1"
```

`setup --route ...`、完整 JSON 报告和 runtime identity 用于支持与自动化诊断，不是普通用户的首次配置步骤。它们不能替代真实 Provider、OCR、PowerPoint、worker 或人工验收的现场证据。

### 1.3 从材料到 PPTX

普通用户在同一对话中按以下顺序推进：

1. 提交文章、报告、笔记、图片、PDF 或已确认来源可信的演示文稿，并说明受众、页数、场景和期望风格。Agent 会从内置与参考风格库（139 种整页风格 + 117 份模板规范，按视觉风格/论证模式/结构布局/品牌身份/图片渲染/信息图类型等轴正交组织）中推荐风格，选定后经确定性注入进入生成流程。
2. 审阅大纲和完整逐页内容稿；事实、数字、引用或表达不正确时先修改内容，不进入制图。
3. 确认视觉方向和图片服务。宿主图片能力已明确可用时无需密钥；否则选择官方 OpenAI、OpenAI-compatible 中转站或 AtlasCloud。外部 Provider 处于 `configured_unverified` 时可继续进入图片节点。
4. 审阅一页样张。只有明确批准后才生成整套；更换图片服务、模型或主要风格时重新确认样张。
5. 审阅最终 PPTX。图片式交付检查逐页可读性；可编辑交付还要检查对象、字体、主题边界和重开保存。未执行的真实服务、PowerPoint 或人工验收保持 `not-run`。

第一次真实业务图片会承担未验证 Provider 的惰性验证。同一验证 scope 同时请求多页时，系统只允许一个可能计费请求在途；其他页面共享结果。验证失败只暂停图片节点，保留主题、材料、大纲、逐页稿和已完成中间产物；完成唯一恢复动作后，Agent 会复查并从中断点恢复。

自然语言示例：

> 使用 `$leo-ppt-generator` 把附件中的年度复盘做成 12 页管理层汇报。保留关键数字，风格简洁专业，先给我大纲和完整逐页内容，再出一页样张确认。

## 2. 按需密钥与高级可选配置

### 2.1 普通用户：使用统一 config 命令组

普通用户的唯一推荐配置入口是 `leo-ppt config` 命令组。macOS standalone 安装后直接使用短命令；Agent、Plugin、Windows 或自动化使用安装器、launcher 或 `primary_action` 提供的准确 `<cli_reference>`。无需也不应手动拼接 `auth`、`provider` 与 backend 命令。

| 命令 | 用途 | 是否可能调用图片服务 |
| --- | --- | --- |
| `config` | 首次配置或继续未完成配置的交互向导 | 默认否 |
| `config status` | 只读检查当前 route、配置引用与证据新鲜度 | 否 |
| `config provider list/configure/select/remove` | 查看、配置、切换或删除 Provider profile | 默认否 |
| `config credential status/set/remove` | 查看或维护安全凭据引用 | 默认否 |
| `config verify --yes` | 由用户显式请求的真实图片验证 | 是，可能计费 |
| `config repair` | 按当前稳定 reason code 从最早未完成步骤恢复 | 默认否 |
| `config reset --confirm` | 重建非敏感 Provider 配置并失效 receipt；保留系统凭据 | 否 |

常用安全检查：

```bash
leo-ppt config status --route generate --json
```

```powershell
& "<cli_reference>" config status --route generate --json
```

配置完成后的 `configured_unverified` 是成功而非失败：它对应 `execution_eligibility=allowed` 与 `installation_readiness=usable_unverified`，可以开始任务。只有当前 route 的全部 required capabilities 都由有效 Capability_Evidence 覆盖，或宿主现场确认能力，才是 `ready`。`generate` 的证据不会自动覆盖 `edit`、`mask` 或 `reference`。

`config verify` 是一次独立、明确的可能计费操作。向导默认“否”；默认回车、超时、取消、安装、更新和宿主调用都不构成同意。跳过 verify 会保留完整配置，并让首张真实业务图片进行惰性验证：

```bash
leo-ppt config verify --route generate --yes --json
```

```powershell
& "<cli_reference>" config verify --route generate --yes --json
```

### 2.2 Provider、凭据与安全输入

当宿主没有可用图片能力时，OpenAI、OpenAI-compatible 中转站与 AtlasCloud 只需选择一个；PaddleOCR 只在可编辑路线确实需要在线文字识别增强时才配置，不是图片式生成前置条件。

- OpenAI：[创建 API Key](https://platform.openai.com/api-keys)；[计费设置](https://platform.openai.com/settings/organization/billing/overview)。
- OpenAI-compatible 中转站：使用服务商提供的 HTTPS API Base URL、图片模型名和独立 API Key；只支持聊天补全的中转站不能用于图片生成。
- AtlasCloud：[注册或登录](https://www.atlascloud.ai/)；[模型列表](https://www.atlascloud.ai/zh/models)。
- PaddleOCR：[申请 Access Token](https://aistudio.baidu.com/account/accessToken)。

凭据可用的安全通道只有三种：真实 TTY 的隐藏输入、已存在的环境变量引用，或用户显式选择的 `--key-stdin`。TTY 输入写入 macOS Keychain 或 Windows 当前用户 DPAPI 保护的存储；环境变量只保存例如 `env:OPENAI_API_KEY` 的引用，不复制值。

非交互自动化必须显式声明输入通道，例如：

```bash
printf '%s\n' "$PROVIDER_KEY" | leo-ppt config credential set --provider openai --key-stdin
```

普通 pipe 不会被隐式读取；没有 `--key-stdin` 时，非 TTY 输入返回
`credential_tty_required` 或 `credential_input_channel_unavailable`。

不接受聊天、命令参数或 pipe 传入密钥：禁止把密钥发送到聊天、使用明文 `--api-key`、URL 查询参数，或让普通 stdin 被隐式读取。密钥不得写入 `config.yaml`、项目、Skill 目录、run、receipt、stdout、stderr 或日志。环境变量仍兼容：`OPENAI_API_KEY`、`OPENAI_COMPATIBLE_API_KEY`、`ATLASCLOUD_API_KEY` 与 `PADDLE_OCR_TOKEN`。

配置、验证或首次业务图片失败时，保留现有凭据、档案、用户材料和已完成产物。执行输出中的唯一 `primary_action`，然后重新运行 `config status` 或返回原对话恢复；不要无条件删除密钥、重装 Skill 或重新提交材料。

### 2.3 OpenAI-compatible 中转站与高级自动化

中转站的 endpoint 必须是 HTTPS origin，且不能包含用户名、密码、查询参数或片段；模型名不能为空。更改 endpoint、模型或凭据版本会让旧 evidence 失效并回到 `configured_unverified`，但不阻止首张真实业务图片承担惰性验证。

普通用户直接运行统一命令，不需要手写底层档案：

```bash
leo-ppt config provider configure --provider openai-compatible
```

```powershell
& "<cli_reference>" config provider configure --provider openai-compatible
```

`auth add/status/remove`、顶层 `provider configure` 与 `config change` 仅作为兼容入口保留；
新文档、Agent 和 `primary_action` 不再生成这些命令。

### 2.4 版本、更新与回滚

```bash
leo-ppt version
leo-ppt version --json
leo-ppt update --check
leo-ppt update --dry-run --version v1.2.3
leo-ppt update --yes --version v1.2.3
leo-ppt rollback
```

`update --check` 和 `--dry-run` 只读；真正更新必须显式传入 `--yes`。更新复用安装器的
下载、验证、stage、route smoke 和原子激活流程，并保留配置、凭据、receipt 与 run。
`rollback` 默认选择 current metadata 中记录的上一健康 runtime，也可由高级用户传入
`--identity`。Skill 内容更新后需重新启动宿主或开启新对话。

### 2.5 高级用户：非敏感运行参数

普通用户无需创建配置文件。只有需要调整并发、空间上限或超时时，才创建 `${LEO_PPT_HOME}/config.yaml`：

```yaml
schema_version: 1
max_concurrent_workers: 5
max_run_bytes: 10737418240
timeouts:
  worker_page_seconds: 600
  backend_api_seconds: 60
  backend_api_retries: 3
```

优先级为命令显式非敏感选项、允许的环境变量、`config.yaml`、默认值。`LEO_PPT_MAX_WORKERS` 范围为 1–16。不要在 YAML 或命令行写 API key。Provider Profile、Credential_Reference、Capability_Evidence 与 Verification_Receipt 都只能保存非敏感资料；receipt 不保存密钥、完整请求、完整响应、验证图片或用户材料。

## 3. Backend Contract（高级自动化与审计）

普通用户不应手写 JSON，也不需要在开始任务前创建 backend contract。Agent 会在已确认的配置、route 与样张边界内处理它。仅当你需要可复现的自动化或审计时，使用准确 CLI 生成并校验非敏感合同：

```bash
"$LEO_PPT" backend create \
  --provider openai --mode generate --output ./backend.json
"$LEO_PPT" backend validate ./backend.json
```

`backend validate` 先验证完整合同，再单独返回 `credential_reference_status=available|missing|host_check_required`。`valid` 不等于真实 Provider 已调用；必须结合当前 route 的 config report、Capability_Evidence 与 `execution_eligibility` 判断是否可执行。需要审计时，生成的内容等价于以下 v1 合同：

```json
{
  "schema_version": 1,
  "backend_kind": "openai-compatible",
  "provider": "openai",
  "model": "gpt-image-2",
  "mode": "generate",
  "credential_source": "environment-reference",
  "credential_ref": "env:OPENAI_API_KEY",
  "selection_source": "user-confirmed",
  "capabilities": {
    "generate": true,
    "edit": true,
    "mask": true,
    "max_reference_images": 16,
    "execution_owner": "runtime"
  }
}
```

可编辑 route 使用 `--mode edit`。内置宿主图片能力使用 `--provider builtin-imagegen`，中转站使用 `--provider openai-compatible`，AtlasCloud 使用 `--provider atlascloud`。目标已存在时命令 fail closed；只有明确替换配置才传 `--overwrite`。样张批准后 backend 冻结；凭据失效时只能恢复同一 backend，切换 backend 必须创建新 run 并重新确认样张。

## 4. 创建 Run（高级操作）

开始 run 前，先确认当前 route 的配置或宿主能力为 `allowed`。`configured_unverified` 可以创建并推进 run；它会在首张真实业务图片处完成验证。`not_configured`、`invalid` 或 `degraded` 则先执行唯一 `primary_action`，不要通过手写 backend JSON 绕过守卫。

```bash
LEO_PPT="<bootstrap 返回的 cli_reference>"
"$LEO_PPT" run create \
  --route generate \
  --input ./content.md \
  --output ./runs/demo \
  --backend-contract ./backend.json \
  --idempotency-key demo-v1
```

四个 route：

- `generate`：Markdown/正文生成图片式 PPTX。
- `direct-editable`：图片/PDF/可信 PPTX 直接重建。
- `upgrade-full`：整套升级。
- `upgrade-selected`：指定页升级。

PPTX 输入必须由用户确认来源可信并传 `--office-trusted`；宏、嵌入对象、外部关系、远程模板和损坏包仍会 fail closed。来源不明时先转成 PDF 或逐页图片。

## 5. 推进与查看状态

```bash
"$LEO_PPT" run status ./runs/demo --json
"$LEO_PPT" run diagnose ./runs/demo --json
```

只按 `status`、`reason_code`、`next_action`、`progress`、`artifact_refs` 和 `evidence_refs` 推进，不解析自由文本 `message`。当配置是 `configured_unverified` 时，图片节点会通过同一验证包装器写入能力级 evidence；当 Provider 返回鉴权、限流、网络、超时、空产物或不确定结果时，保留 run 并给出一次恢复或确认动作，不能把失败误写为 `ready`。

图片式路径的确定性命令：

```bash
"$LEO_PPT" image prepare ./runs/demo
"$LEO_PPT" image record ./runs/demo \
  --slide slide_01 --agent-id worker-1 --result ./slide_01.png \
  --expected-state-hash '<status 返回的 hash>'
"$LEO_PPT" image assemble ./runs/demo
```

可编辑路径：

```bash
"$LEO_PPT" editable prepare ./runs/demo
"$LEO_PPT" editable next ./runs/demo --json
"$LEO_PPT" editable dispatch ./runs/demo \
  --page page_001 --agent-id worker-1 --prompt-file ./page-001-prompt.md
"$LEO_PPT" editable record ./runs/demo --page page_001 --agent-id worker-1
"$LEO_PPT" editable finalize ./runs/demo
```

`editable dispatch` 只能在宿主真实派发成功后记录绑定。指定页升级最终运行：

```bash
"$LEO_PPT" upgrade finalize ./runs/demo
```

默认任何选中页失败都会拒绝交付。只有用户已看到当前失败集合并明确接受时，才使用 `--allow-partial`，交付类型必须声明为 `partial-hybrid`。

## 6. 恢复、取消与清理

图片服务失败不会清除主题、材料、大纲、逐页稿、既有图片或 run。先按 reason code 执行一个 `config repair`、`wait_and_retry` 或 `confirm_new_request` 动作；配置或网络恢复后，重新检查状态并从图片节点恢复。对于不支持可证明幂等语义的 Provider，如果请求结果不确定，系统不会自动重试可能计费请求。

响应丢失时先查询原 operation：

```bash
"$LEO_PPT" run operation ./runs/demo --id '<operation-id>' --json
"$LEO_PPT" run retry ./runs/demo --from-failed-pages
"$LEO_PPT" run cancel ./runs/demo --wait-workers
```

只有 `safe_to_retry=true` 才能自动重试，并复用同一 idempotency key。cancel 是终态，不可自动重试。真实业务图片成功但 evidence 写入失败时，保留图片并仅修复本地 receipt 持久化；不得再次调用 Provider。

清理必须先 dry-run，再应用完全相同的 preview：

```bash
"$LEO_PPT" run cleanup ./runs/demo --scope temp --dry-run
"$LEO_PPT" run cleanup ./runs/demo --scope temp --apply
```

`input` 只能在 terminal run 且无 active worker 时删除；删除不可恢复，并使该 run 不能重新 prepare。`image-deck/`、`editable/` 和 `final/` 不在默认清理范围。

## 7. 交付验收

完成后逐项检查：

1. `status=completed`，且 route 与 delivery type 一致；这只表示产物阶段完成。
2. `final/deck.pptx` hash 与交付 manifest 一致。
3. `final/validation-summary.json` 为 passed。
4. partial-hybrid 同时存在 `final/failure-report.json`，失败页保持 image。
5. 页数、页序、尺寸、notes、source hash 和 validation refs 正确。
6. `logs/run.log`、`events.ndjson`、`reports/timing.json` 不含正文或凭据。
7. 分别记录真实 Provider、OCR、Office viewer、PowerPoint 桌面和人工视觉结果；未执行项明确写 `not-run`，不能用 fixture 替代。

`ready`、Provider smoke、业务图片 receipt 与 `config status` 都不能替代最终交付验收。它们仅证明各自 scope 内的状态或能力；PowerPoint 桌面和人工视觉结果仍需独立记录。

完成组装后先查看 `delivery_readiness`。`acceptance_pending` 表示 PPTX 已生成、但 `visual_render` 或 `manual_visual_acceptance` 尚未闭环，必须继续执行下方 evidence 命令；只有 `delivery_readiness.status=accepted` 且 `next_action.kind=none` 才是用户可接受的收尾状态。`artifact_invalid` 必须先修复交付结构，不能补人工 receipt 绕过。

三类证据通过独立命令写入，不能由 worker manifest 自签：

```bash
"$LEO_PPT" evidence provenance ./runs/demo --receipt ./provider-page-001.json
"$LEO_PPT" evidence visual ./runs/demo --receipt ./visual-render.json
"$LEO_PPT" evidence accept ./runs/demo --receipt ./manual-acceptance.json
```

provider receipt 至少包含 `page_id`、`provider`、`model`、`prompt_sha256`、`input_sha256` 和 canonical `artifact_sha256`。visual receipt 必须绑定最终 `pptx_sha256`、renderer/version、连续逐页 render path/hash 以及 font/contrast/occlusion 结论。人工 receipt 必须绑定同一 PPTX hash、reviewer、PowerPoint/其他客户端版本和逐页 `accepted` 决策。任何 secret、缺页、拒绝页或旧 PPTX hash 都会阻断。

常见错误及恢复动作见[故障处理](troubleshooting.md)；稳定机器原因码见 Skill 内 `references/reason-codes.md`。

## 8. 升级 Skill

一键安装用户可直接升级：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash -s -- --upgrade
```

Windows PowerShell：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1))) -Upgrade
```

安装器会先在临时目录验证新副本。只有 `ensure` 和四条 route 的本地机制 `doctor` 全部成功，才把旧 Skill 移到带时间戳的备份目录并激活新版本；初始化失败时现有 Skill 保持不变。固定版本升级时，macOS 传 `--ref <commit-or-tag>`，Windows 传 `-Ref <commit-or-tag>`。使用通用发现目录时再加 `--agents` 或 `-Agents`。

每次升级后都会重新进行 `config status` 的本地检查。若 Provider、endpoint、模型、凭据版本、adapter 或验证策略未变化，且当前 route 的 evidence 仍有效，可直接复用，不会重复索要密钥或启动付费 smoke。若本地配置仍完整但证据过期、损坏或 fingerprint 改变，状态回到 `configured_unverified` / `usable_unverified`；下一次真实业务图片会验证，`config verify` 只是可选的明确付费操作。

升级不得删除或覆盖 `LEO_PPT_HOME`、Credential Store、Provider Profile、有效 receipt、active run 或交付物。通过 `skill-installer` 安装的用户，应先记录当前 revision，把旧 Skill 移出发现目录并保留备份，再让 Codex 安装固定的新 revision；该工具遇到同名目录会拒绝覆盖。完成后重新启动 Codex 或进入下一轮对话，确认只发现一个 `leo-ppt-generator`。

## 9. 卸载 Skill

先移出发现目录并重新启动宿主，这只停止 Skill 发现，不自动删除 `LEO_PPT_HOME`、OS 凭据、Provider Profile、receipt、run、交付文件或受管 runtime。确认不再需要旧版本后再处理备份。任何清理都必须是独立、精确且可预览的动作，不能把卸载当作配置或凭据修复手段。

runtime 清理是独立且受保护的操作。先保留至少一个健康 current runtime；若要删除非 current identity，必须提供真实 runs 根目录：

```bash
python "<Skill root>/scripts/runtime_manager.py" remove \
  --identity '要删除的非 current runtime identity' \
  --runs-root '/绝对路径/到/runs'
```

存在引用该 identity 的 active run 时命令会拒绝；current identity 也不能直接删除，必须先 `rollback --identity <保留的健康 identity>`。`remove` 将精确 runtime 移入 quarantine，而不是递归删除宽泛目录。run 和最终 PPTX 不自动删除。

## 10. 隐私与数据边界

- `config.yaml`、backend contract 与 run 只保存非敏感 Credential_Reference，例如 `env:OPENAI_API_KEY`；不得把凭据值写入 YAML、命令历史、run、receipt、日志或交付报告。
- 交互式密钥使用隐藏输入；非交互只接受既有环境变量引用或显式 `--key-stdin`。不接受聊天、明文命令参数、URL 查询参数或普通 stdin 的隐式读取。
- 在线图片 Provider 和 OCR 只接收完成当前任务所需的 task-local 页面图片、prompt、mask 与引用素材；可能计费的 smoke 必须由当前用户明确同意，不会把授权持久化为未来调用的默认同意。
- `logs/run.log`、`events.ndjson`、`reports/timing.json`、config report 与 receipt 只记录 allowlist 字段、hash、reason code、状态与耗时，不记录密钥、鉴权 header、完整请求/响应或用户正文。
- 输入、失败尝试与中间产物默认保留以支持恢复。清理必须先 dry-run，再对相同 fingerprint 应用；`input` 清理不可恢复且只允许 terminal run。
- Provider、OCR、Office viewer、PowerPoint 桌面和人工视觉验证逐项记录；没有真实 receipt 时保持 `not-run`，不得用离线 fixture 冒充现场结果。
