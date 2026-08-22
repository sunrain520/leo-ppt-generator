# 已知限制

## 配置、验证与凭据边界

- `config status` 只证明本地配置、凭据引用、当前 route 与 receipt 的可解释性，不调用
  Provider，也不证明网络、账户权限、模型、图片质量或费用状态。
- `configured_unverified` 表示本地配置完整且可开始任务；首张真实业务图片才会在当前
  Verification Scope 内惰性验证。`ready` 仅覆盖已有有效 Capability Evidence 的当前
  route/能力，或当前宿主现场确认的 Host Provider；`generate` 的证据不能外推到
  `edit`、`mask`、`reference` 或其他 Provider/模型。
- 付费 `config verify --yes` 在 v1 仅验证 `generate`，且只在用户对当前操作明确同意后执行；
  当前 runtime 未接入真实 smoke executor 时会返回 `provider_smoke_executor_unavailable`，
  不会把本地状态复查伪装成真实验证。
  默认回车、超时、取消、安装、更新和宿主调用均不构成同意；跳过 smoke 不应阻断开始任务。
- 同一 Verification Scope 在尚无有效证据时最多允许一个可能计费请求在途。该机制降低
  并发重复验证风险，但不承诺外部 Provider 的长期 SLA、价格、配额、幂等或结果可恢复性；
  Registry 未明确声明的策略一律为 `unknown` 并 fail closed。
- 真实业务图片成功但 Capability Evidence 原子写入失败时，图片和任务上下文会保留，当前
  route 仍不能声明 `ready`；恢复只能重试本地 receipt 持久化，不能再次调用 Provider。
- 密钥只能来自真实 TTY 隐藏输入、既有环境变量引用或用户显式 `--key-stdin`。平台安全
  存储失败时不会降级为明文文件；本项目也不支持在聊天、命令参数、URL、普通 stdin 或
  项目配置中提交密钥。

## PowerPoint 主题与母版语义

editable 路线提供的是视觉重建与对象级可编辑交付，不承诺保留输入 PPTX 的主题、母版、
版式继承、主题色绑定或新建页继承关系。输出会使用 runtime 的固定基础 theme/master；
品牌色、字体和 logo 仅作为页面对象或视觉约束重建。若用户要求模板语义保留，必须在
交付前单独确认该能力不在当前支持范围。

- 当前验证环境没有 `OPENAI_API_KEY`、AtlasCloud key 或其他获准图片 provider
  凭据，因此未运行真实图片生成 smoke。
- 当前 Codex 会话没有暴露可调用的内置图片生成工具，因此零密钥真实生成未运行；
  setup 会诚实返回 `image_provider_configuration_required`，而不是把未知或不可用能力
  当作 ready。
- 当前环境没有 `PADDLE_OCR_TOKEN`；只验证 `builtin-ink` 离线几何检测，不能
  读取图片文字内容。
- 当前环境安装了 LibreOffice 26.2.5.2，并完成可信 PPTX 转 PDF；
  `sandbox-exec deny network` 下完成 PPTX 归一化与离线 OCR，但 LibreOffice
  自身在该 sandbox 中未产出转换文件，因此不把两项证据合并为“viewer 无网络”。
- 当前机器没有 Microsoft PowerPoint，因此没有 PowerPoint 桌面打开/逐页检查
  receipt。
- 结构验证、对象存在和 page mode 正确不等于人工视觉等价；人工视觉验收仍需
  发布候选 PPTX 与 Owner。
- 多页真实执行仍依赖当前 Agent 宿主提供已授权、可调用且容量足够的 worker；
  runtime 不模拟 scheduler。
- macOS Keychain 和 Windows 当前用户 DPAPI 防止凭据被普通文件、项目、日志或发布包
  明文保存，但不承诺抵御已取得同一用户会话权限的恶意进程。账户或会话疑似失陷时
  必须撤销服务商密钥并删除本地引用。
- Plugin 与 standalone 的本地包结构已验证一致；进入公共 Plugins Directory 仍需要
  独立提交、审核和发布，仓库 marketplace 不等于已进入公共目录。
- Windows PowerShell 控制流、依赖 wheel 解析和 DPAPI adapter 测试不能替代 Windows
  10/11 x64 真机上的 NTFS、进程锁、当前用户 ACL、DPAPI 身份和完整安装证据。
