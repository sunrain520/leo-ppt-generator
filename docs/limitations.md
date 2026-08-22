# 已知限制

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
