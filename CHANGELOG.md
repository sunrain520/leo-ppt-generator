# Changelog

- 记录格式：`- v版本号 YYYY-MM-DD HH:MM:SS 作者: 变更摘要 [(user-visible)]`
- 说明：
  - `v版本号` 使用本次变更对应的发布版本
  - 日期时间必须使用 `YYYY-MM-DD HH:MM:SS`
  - `作者` 填写提交人或变更责任人
  - `变更摘要` 使用中文，简明说明本次改动
  - 用户可感知的变更在末尾追加 `(user-visible)`

- v1.15.1 2026-08-20 16:21:57 leokuang: 使用 spec-first 初始化项目
- v1.15.1 2026-08-20 20:09:21 leokuang: 重构 PPT 编排方案为复用优先版本（002），前置逐文件上游 disposition ledger，收缩 Schema 至 2 个、测试至约 28 个、状态机制降为单机规格，SSIM 视觉回归推迟到 v2；原方案 001 标记 superseded
- v1.15.1 2026-08-20 20:23:52 leokuang: 修复 002 方案 3 处可验证性缺口：KTD7 添加 factory.py 攻击后果说明（credential 泄露与内容披露），U5 明确 soffice 沙箱执行层与 degraded fallback 策略，U1 新增 disposition 变更审计测试
- v1.15.1 2026-08-20 20:53:55 leokuang: 修复 002 方案 6 处执行风险：测试规模修正为约 45（含完整套件说明）、verbatim 复用证据统一要求 fixture 一致性、R59 视觉验收明确 v1 为结构合同+代表性抽查、G4 增加图片版 QA 内容定义（标题/数字/素材）、任务文件权限保护（0700/0600 + 安全临时文件）、worker 环境变量隔离（allowlist + 关闭继承 FD）
