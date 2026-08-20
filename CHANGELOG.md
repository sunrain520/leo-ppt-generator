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
