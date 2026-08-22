# Leo PPT Generator 用户教程

普通用户只需完成四步：选择一种安装方式、开启新对话、提交材料与 PPT 目标、按提示
确认大纲和样张。只有当前宿主没有图片生成能力时，才需要在本地终端安全配置一个图片
服务密钥。后文的 CLI、backend contract 和 run 命令均为高级诊断或自动化接口，不是
首次使用前置条件。

## 1. 安装 Skill 与首次验证

### 1.1 选择一种简单安装方式

安装器面向 macOS arm64 与 Windows 10/11 x64，不需要管理员权限或预装 Python。
Plugin 与 standalone Skill 二选一，不要同时保留重复副本；各平台现场验证状态见
[兼容性说明](compatibility.md)。

远程安装以已公开的仓库和 release tag 为准。仓库、Skill 路径或脚本 URL 返回 404
表示该 revision 尚未公开可安装；停止重试并查看[故障处理](troubleshooting.md)。

方式一（推荐），安装 Codex Plugin：

```text
codex plugin marketplace add sunrain520/leo-ppt-generator --ref main
codex plugin add leo-ppt-generator@leo-ppt-generator
```

把两行作为一次安装连续执行。生产使用把 `main` 换成固定 release tag。安装后开启
新对话。宿主若明确提供兼容的 Plugins marketplace 界面，也可在界面中选择
`Leo PPT Generator`；没有该入口时使用上面的 Codex CLI。

方式二，安装 standalone Skill。在 Codex 中发送下面这句话：

> 请使用 `skill-installer` 从以下地址安装：  
> https://github.com/sunrain520/leo-ppt-generator/tree/main/skills/leo-ppt-generator

`skill-installer` 会安装到 `$CODEX_HOME/skills/leo-ppt-generator`；未设置
`CODEX_HOME` 时默认为 `~/.codex/skills/leo-ppt-generator`。同名目录已经存在时会
拒绝覆盖。安装成功后开启下一轮 Codex 对话，首次使用会自动初始化 runtime。

不要对同一目标并发运行多个安装器；安装器会让竞争者 fail closed。Bash 进程若被
强制终止，下一次可能报告 `.leo-ppt-generator.install.lock`；先确认没有活动安装进程，
再只移除错误信息给出的精确锁目录，不能递归清理整个 Skill 父目录。

方式三，在终端一键安装 standalone Skill。

macOS arm64：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash
```

Windows 10/11 x64（PowerShell）：

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1 | iex
```

脚本自动完成平台检查、兼容解释器解析或私有 Python 3.12 安装、runtime 初始化、四条
route 验证和原子安装，不需要 `sudo`。它不会读取或保存 API key。希望先审阅脚本再
执行时：

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

该目标为 `$HOME/.agents/skills/leo-ppt-generator`。不要同时保留 Codex 目录和通用
目录两份副本。固定版本时，把两处占位符替换为同一个 release tag 或 commit：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/<commit-or-tag>/install.sh \
  | bash -s -- --ref <commit-or-tag>
```

```powershell
irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/<commit-or-tag>/install.ps1 -OutFile install.ps1
.\install.ps1 -Ref <commit-or-tag>
```

使用 `main` 获得最新版本；生产环境推荐固定版本。若已 checkout 本仓库，在仓库根目录
macOS 运行 `bash install.sh`，Windows 运行 `.\install.ps1`，即可使用本地 bundle。
安装后重新启动 Codex，或至少开启下一轮对话，确认只出现一个
`leo-ppt-generator`。

### 1.2 自动初始化与高级验证

普通用户在新对话直接说：

> 使用 `$leo-ppt-generator` 把这份材料做成 12 页、面向管理层的 PPT，先确认大纲和样张。

Agent 会自动调用当前平台 launcher、读取受管 CLI 路径并运行 setup。非 ready 结果只给
一个首选恢复动作。自动初始化会复用兼容的 Python 3.12，或在 Leo 私有目录准备隔离
runtime；不会修改系统 Python、系统 PATH，也不会读取图片服务密钥。只有高级诊断时才
手动运行 launcher：

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/leo-ppt-generator/scripts/leo-bootstrap.sh"
```

```powershell
& "$env:USERPROFILE\.codex\skills\leo-ppt-generator\scripts\leo-bootstrap.ps1"
```

成功 JSON 中的 `cli_reference` 是当前准确 CLI。继续用该绝对路径运行
`setup --route generate --host-imagegen <available|unavailable|unknown> --json`；不要从
PATH 猜测。`ready` 只证明本地机制与当前选择可开始，不证明真实 Provider、OCR、
PowerPoint、worker 或人工验收已通过。

当前 Codex 0.149.0/macOS 已验证两种全新会话发现方式：显式写
`$leo-ppt-generator`，或直接说“把这篇文章生成高质量 PPTX”。若新会话未识别，先按
[故障处理](troubleshooting.md)确认只有一个可发现副本；不要通过重复安装碰运气。

### 1.3 从材料到 PPTX

普通用户在同一对话中按以下顺序推进：

1. 提交文章、报告、笔记、图片、PDF 或已确认来源可信的演示文稿，并说明受众、页数、
   场景和期望风格。
2. 审阅大纲和完整逐页内容稿；事实、数字、引用或表达不正确时先修改内容，不进入制图。
3. 确认视觉方向和图片服务。宿主图片能力已明确可用时无需密钥；否则 OpenAI 与
   AtlasCloud 二选一。
4. 审阅一页样张。只有明确批准后才生成整套；更换图片服务、模型或主要风格时重新确认
   样张。
5. 审阅最终 PPTX。图片式交付检查逐页可读性；可编辑交付还要检查对象、字体、主题边界
   和重开保存。未执行的真实服务、PowerPoint 或人工验收保持 `not-run`。

自然语言示例：

> 使用 `$leo-ppt-generator` 把附件中的年度复盘做成 12 页管理层汇报。保留关键数字，风格简洁专业，先给我大纲和完整逐页内容，再出一页样张确认。

## 2. 按需密钥与高级可选配置

### 2.1 普通用户：仅在提示时配置一个密钥

若 setup 返回 `image_provider_configuration_required`，表示当前宿主没有可调用的图片
生成能力。OpenAI 与 AtlasCloud 只需选择一个：

- OpenAI：[创建 API Key](https://platform.openai.com/api-keys)；
  [计费设置](https://platform.openai.com/settings/organization/billing/overview)。
- AtlasCloud：[注册或登录](https://www.atlascloud.ai/)；
  [模型列表](https://www.atlascloud.ai/zh/models)。
- PaddleOCR：[申请 Access Token](https://aistudio.baidu.com/account/accessToken)。它只在
  可编辑路线确实需要在线文字识别增强时配置，不是图片式生成前置条件。

Agent 会给出带准确 `<cli_reference>` 的一条命令。必须在本地交互式终端执行，不要把
密钥发到聊天：

```bash
"<cli_reference>" auth add --provider openai
```

```powershell
& "<cli_reference>" auth add --provider openai
```

选择 AtlasCloud 时只把 provider 改为 `atlascloud`。命令会隐藏输入；macOS 写入
Keychain，Windows 写入当前用户 DPAPI 保护的存储。配置后回到原对话继续，不必重装
Skill。需要查看或删除时使用 `auth status --provider <provider> --json` 或
`auth remove --provider <provider>`，这些命令都不会显示密钥值。

### 2.2 高级用户：非敏感运行参数

普通用户无需创建配置文件。只有需要调整并发、空间上限或超时时，才创建
`${LEO_PPT_HOME}/config.yaml`：

```yaml
schema_version: 1
max_concurrent_workers: 4
max_run_bytes: 10737418240
timeouts:
  worker_page_seconds: 600
  backend_api_seconds: 60
  backend_api_retries: 3
```

优先级为命令显式非敏感选项、允许的环境变量、`config.yaml`、默认值。
`LEO_PPT_MAX_WORKERS` 范围为 1–16。不要在 YAML 或命令行写 API key。

不要把凭据写入 YAML。第 2.1 节的命令只在交互式终端隐藏读取；不接受聊天、命令参数或 pipe。
`auth status --provider openai --json` 只返回 `available|missing` 与非敏感
reference。环境变量仍作为无持久化兼容入口，优先级高于 OS store；日志不会记录值、
长度、前后缀或 hash。

## 3. Backend Contract

每个 run 需要一个完整、非敏感且经用户确认的 backend contract。普通用户不应手写
JSON；用第 1.2 节取得的准确 CLI 生成并校验：

```bash
"$LEO_PPT" backend create \
  --provider openai --mode generate --output ./backend.json
"$LEO_PPT" backend validate ./backend.json
```

`backend validate` 先验证完整合同，再单独返回
`credential_reference_status=available|missing|host_check_required`。`valid` 不等于真实
provider 已调用；`missing` 时按 `next_action` 注入允许的环境引用后重试。需要审计时，
生成的内容等价于以下 v1 合同：

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

可编辑 route 使用 `--mode edit`。内置宿主图片能力使用
`--provider builtin-imagegen`，AtlasCloud 使用 `--provider atlascloud`。目标已存在时
命令 fail closed；只有明确替换配置才传 `--overwrite`。样张批准后 backend 冻结；凭据失效时只能恢复同一
backend，切换 backend 必须创建新 run 并重新确认样张。

## 4. 创建 Run

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

PPTX 输入必须由用户确认来源可信并传 `--office-trusted`；宏、嵌入对象、外部关系、
远程模板和损坏包仍会 fail closed。来源不明时先转成 PDF 或逐页图片。

## 5. 推进与查看状态

```bash
"$LEO_PPT" run status ./runs/demo --json
"$LEO_PPT" run diagnose ./runs/demo --json
```

只按 `status`、`reason_code`、`next_action`、`progress`、`artifact_refs` 和
`evidence_refs` 推进，不解析自由文本 `message`。多页 `request_worker_dispatch`
要求当前用户授权、当前会话能力、容量和真实派发成功；CLI 不会模拟 Agent worker。

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

默认任何选中页失败都会拒绝交付。只有用户已看到当前失败集合并明确接受时，才使用
`--allow-partial`，交付类型必须声明为 `partial-hybrid`。

## 6. 恢复、取消与清理

响应丢失时先查询原 operation：

```bash
"$LEO_PPT" run operation ./runs/demo --id '<operation-id>' --json
"$LEO_PPT" run retry ./runs/demo --from-failed-pages
"$LEO_PPT" run cancel ./runs/demo --wait-workers
```

只有 `safe_to_retry=true` 才能自动重试，并复用同一 idempotency key。cancel 是终态，
不可自动重试。清理必须先 dry-run，再应用完全相同的 preview：

```bash
"$LEO_PPT" run cleanup ./runs/demo --scope temp --dry-run
"$LEO_PPT" run cleanup ./runs/demo --scope temp --apply
```

`input` 只能在 terminal run 且无 active worker 时删除；删除不可恢复，并使该 run
不能重新 prepare。`image-deck/`、`editable/` 和 `final/` 不在默认清理范围。

## 7. 交付验收

完成后逐项检查：

1. `status=completed`，且 route 与 delivery type 一致；这只表示产物阶段完成。
2. `final/deck.pptx` hash 与交付 manifest 一致。
3. `final/validation-summary.json` 为 passed。
4. partial-hybrid 同时存在 `final/failure-report.json`，失败页保持 image。
5. 页数、页序、尺寸、notes、source hash 和 validation refs 正确。
6. `logs/run.log`、`events.ndjson`、`reports/timing.json` 不含正文或凭据。
7. 分别记录真实 provider、OCR、Office viewer、PowerPoint 桌面和人工视觉结果；
   未执行项明确写 `not-run`，不能用 fixture 替代。

完成组装后先查看 `delivery_readiness`。`acceptance_pending` 表示 PPTX 已生成、但
`visual_render` 或 `manual_visual_acceptance` 尚未闭环，必须继续执行下方 evidence
命令；只有 `delivery_readiness.status=accepted` 且 `next_action.kind=none` 才是用户
可接受的收尾状态。`artifact_invalid` 必须先修复交付结构，不能补人工 receipt 绕过。

三类证据通过独立命令写入，不能由 worker manifest 自签：

```bash
"$LEO_PPT" evidence provenance ./runs/demo --receipt ./provider-page-001.json
"$LEO_PPT" evidence visual ./runs/demo --receipt ./visual-render.json
"$LEO_PPT" evidence accept ./runs/demo --receipt ./manual-acceptance.json
```

provider receipt 至少包含 `page_id`、`provider`、`model`、`prompt_sha256`、
`input_sha256` 和 canonical `artifact_sha256`。visual receipt 必须绑定最终
`pptx_sha256`、renderer/version、连续逐页 render path/hash 以及 font/contrast/
occlusion 结论。人工 receipt 必须绑定同一 PPTX hash、reviewer、PowerPoint/其他
客户端版本和逐页 `accepted` 决策。任何 secret、缺页、拒绝页或旧 PPTX hash 都会阻断。

常见错误及恢复动作见[故障处理](troubleshooting.md)；稳定机器原因码见 Skill 内
`references/reason-codes.md`。

## 8. 升级 Skill

一键安装用户可直接升级：

```bash
curl -fsSL https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.sh | bash -s -- --upgrade
```

Windows PowerShell：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sunrain520/leo-ppt-generator/main/install.ps1))) -Upgrade
```

安装器会先在临时目录验证新副本。只有 `ensure` 和四条 route 的本地机制 `doctor` 全部成功，
才把旧 Skill 移到带时间戳的备份目录并激活新版本；初始化失败时现有 Skill 保持不变。
固定版本升级时，macOS 传 `--ref <commit-or-tag>`，Windows 传
`-Ref <commit-or-tag>`。使用通用发现目录时再加 `--agents` 或 `-Agents`。

通过 `skill-installer` 安装的用户，应先记录当前 revision，把旧 Skill 移出发现目录并
保留备份，再让 Codex 安装固定的新 revision；该工具遇到同名目录会拒绝覆盖。完成后
重新启动 Codex 或进入下一轮对话，确认只发现一个 `leo-ppt-generator`，必要时按
第 1.2 节执行高级验证。

远程安装以实际 tag/commit 为准；本地验收只证明本地 bundle。生产使用应固定版本，
不要仅凭 `main` 的名称推断安装内容没有变化。

## 9. 卸载 Skill

先移出发现目录并重新启动宿主，这只停止 Skill 发现，不自动删除 run、交付文件或受管
runtime。确认不再需要旧版本后再处理备份。

runtime 清理是独立且受保护的操作。先保留至少一个健康 current runtime；若要删除非
current identity，必须提供真实 runs 根目录：

```bash
python "<Skill root>/scripts/runtime_manager.py" remove \
  --identity '要删除的非 current runtime identity' \
  --runs-root '/绝对路径/到/runs'
```

存在引用该 identity 的 active run 时命令会拒绝；current identity 也不能直接删除，
必须先 `rollback --identity <保留的健康 identity>`。`remove` 将精确 runtime 移入
quarantine，而不是递归删除宽泛目录。run 和最终 PPTX 不自动删除。

## 10. 隐私与数据边界

- backend contract 只保存 `credential_ref`，例如 `env:OPENAI_API_KEY`；不得把凭据值
  写入 YAML、命令历史、run、日志或交付报告。
- 在线图片 provider 和 OCR 只接收完成当前任务所需的 task-local 页面图片、prompt、
  mask 与引用素材；未取得对应授权时保持 blocked 或使用明确允许的离线能力。
- `logs/run.log`、`events.ndjson` 和 `reports/timing.json` 只记录 allowlist 字段、hash、
  reason code、状态与耗时，不记录正文或完整环境。
- 输入、失败尝试与中间产物默认保留以支持恢复。清理必须先 dry-run，再对相同
  fingerprint 应用；`input` 清理不可恢复且只允许 terminal run。
- provider、OCR、Office viewer、PowerPoint 桌面和人工视觉验证逐项记录；没有真实
  receipt 时保持 `not-run`，不得用离线 fixture 冒充现场结果。
