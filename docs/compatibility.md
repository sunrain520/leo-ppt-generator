# 版本兼容性声明

- Runtime package：`leo-ppt-generator-runtime 0.1.x`。
- Plugin manifest：`leo-ppt-generator 0.1.x`；standalone 与 Plugin 必须来自同一
  canonical Skill tree hash。
- Python：声明 `>=3.12,<3.13`。
- 目标安装平台：macOS arm64 与 Windows 10/11 x64；可复用兼容系统 Python，也可由
  固定 bootstrap 工件安装私有 Python 3.12，不修改系统 PATH。
- Machine protocol：`leo-ppt-machine/v1`；setup、bootstrap、credential 和 release
  另有各自 v1 协议；未知 protocol/route/step fail closed。
- Run schema、PageArtifact、Delivery、backend config：均为 schema version 1；
  更高版本拒绝读取，不做猜测式降级。
- 活动 run 固定创建时 runtime identity；新 runtime 不声明兼容时，必须由旧
  immutable runtime 恢复。被活动 run 引用的 runtime 不允许删除。

当前实测矩阵：

| 环境 | 当前证据 | 可声明边界 |
| --- | --- | --- |
| macOS 26.5.1 arm64 | standalone 与 Codex Plugin 各独立冷安装 20/20；私有 runtime、四 route、Keychain 生命周期；Codex 0.149.0 全新会话显式与自然语言触发 | 当前 macOS 机器上的本地机制、两渠道重复安装稳定性和新会话发现已验证 |
| Windows 10/11 x64 | PowerShell 7.6.2 控制流在 macOS 兼容执行；26 个固定依赖可解析 Windows x64 wheel；DPAPI adapter 有确定性测试 | 安装器以 Windows x64 为目标，但 Windows NTFS、进程、ACL、DPAPI 身份和完整安装仍待真机关闭 |

正式 release 仍应在 Windows x64 runner 执行真实 clean install、DPAPI add/status/remove、
ACL/身份和四 route 黑盒门禁。其他 Codex 版本、Python minor、Windows on ARM、
macOS Intel、Linux、PowerPoint 桌面版本和在线 Provider 组合在取得对应 receipt 前均
属于未验证兼容范围。一个平台或宿主版本的结果不能补偿另一个平台或版本未运行。
