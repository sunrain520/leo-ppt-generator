# 版本兼容性声明

- Runtime package：`leo-ppt-generator-runtime 0.1.x`。
- Plugin manifest：`leo-ppt-generator 0.1.x`；standalone 与 Plugin 必须来自同一
  canonical Skill tree hash。
- Python：声明 `>=3.12,<3.13`。
- 目标安装平台：macOS arm64/x86_64 与 Windows 10/11 x64；可复用兼容系统 Python，
  也可由固定 bootstrap 工件安装私有 Python 3.12，不修改系统 PATH。
- Machine protocol：`leo-ppt-machine/v1`；version、update、setup、bootstrap、credential 和 release
  另有各自 v1 协议；未知 protocol/route/step fail closed。
- Run schema、PageArtifact、Delivery、backend config：均为 schema version 1；
  更高版本拒绝读取，不做猜测式降级。
- 活动 run 固定创建时 runtime identity；新 runtime 不声明兼容时，必须由旧
  immutable runtime 恢复。被活动 run 引用的 runtime 不允许删除。
- 依赖来源边界：bootstrap 阶段的 uv 与私有 Python 由 `runtime/bootstrap-lock.json`
  固定版本、URL 与 SHA-256；但运行时依赖是安装期用 `pip install --constraint`
  按 `runtime/constraints/*.txt` 解析安装，当前只固定版本、未启用 `--require-hashes`，
  因此首次安装（或缺少本地 wheel 缓存时）需要访问 PyPI。启用 hash 级固定需先用
  `pip-compile --generate-hashes` 逐平台重生成 constraints。

配置与验证兼容性同样按协议边界计算：

- 普通用户稳定入口是 `leo-ppt config` 命令组；`status`、`provider`、`credential`、`verify` 与 `repair`
  的 JSON 输出使用 `leo-ppt-config/v1`。未知 protocol、route、能力或 Provider policy
  均 fail closed，不按历史本地配置或静态 Provider 声明猜测可用性。
- `config status` 是本地只读检查，不访问 Provider。`ready` 只覆盖当前
  route/readiness scope 已有有效 Capability Evidence 的能力，或当前宿主现场确认的 Host
  Provider；一个 `generate` receipt 不能推导 `edit`、`mask` 或 `reference`。
- `configured_unverified` 表示本地配置完整且允许开始任务，`installation_readiness` 为
  `usable_unverified`；只有执行资格为 `blocked` 或 `retryable` 时才是
  `installed_not_ready`。安装、升级、默认回车、超时、取消和宿主调用都不是付费 smoke
  的同意。

当前实测矩阵：

| 环境 | 当前证据 | 可声明边界 |
| --- | --- | --- |
| macOS 26.5.1 arm64 | standalone 与 Codex Plugin 各独立冷安装 20/20；私有 runtime、四 route、Keychain 生命周期；Codex 0.149.0 全新会话显式与自然语言触发 | 当前 macOS 机器上的本地机制、两渠道重复安装稳定性和新会话发现已验证 |
| macOS x86_64 (Intel) | 固定 `macos-x64` uv artifact、`darwin-x86_64` 约束锁、bootstrap/install 平台门与 Keychain store 已就绪；CI 在 Intel runner 执行真实 clean install 与 `config status` 冒烟 | 完整安装与 Keychain 生命周期待 Intel runner receipt 关闭 |
| Windows 10/11 x64 | PowerShell 7.6.2 控制流在 macOS 兼容执行；26 个固定依赖可解析 Windows x64 wheel；DPAPI adapter 有确定性测试；CI 在 Windows runner 执行真实 clean install 与 `config status` 冒烟 | 安装器以 Windows x64 为目标，DPAPI add/status/remove、ACL/身份和完整安装仍待真机关闭 |

正式 release 的 `platform-smoke` CI job 在 macOS arm64、macOS Intel 与 Windows x64 runner
执行真实 clean install、bootstrap 与 `config status` 冒烟；Windows 仍需 DPAPI
add/status/remove、ACL/身份和四 route 黑盒门禁。其他 Codex 版本、Python minor、
Windows on ARM、Linux、PowerPoint 桌面版本和在线 Provider 组合在取得对应 receipt 前均
属于未验证兼容范围。一个平台或宿主版本的结果不能补偿另一个平台或版本未运行。
