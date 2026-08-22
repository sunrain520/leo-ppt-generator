# 图片式 PPT 工作流

## 读取顺序

1. 冻结内容合同：主题、受众、使用场景、演讲时长、行动目标、页数、素材来源、
   必须出现的事实与不可杜撰项。来源不足的数字、引用、客户名、结论或因果关系标记为
   `unknown` 并向用户确认，不得为了页面完整而补写。
2. 输出大纲并等待确认。
3. 输出完整逐页内容稿并等待确认。每页只承担一个可复述任务，并标记页面角色
   （开场、问题、证据、解释、方案、行动或收束）、核心结论、事实来源、讲述衔接和
   预计用时；总时长必须与内容密度相容。
4. 提供 2–3 个具体视觉方向，确认一个。
5. 按 `backend-selection.md` 确认固定 backend。
6. 生成恰好一个代表性样张，等待确认。
7. 把已确认内容写入 run 的冻结输入，调用顶层
   `"$LEO_PPT" image prepare <run> --slides <slides.json>`；这一步创建唯一
   `image-deck/slide_jobs.json` canonical state。vendor prompt 工具只能作为
   无状态能力被 bridge 调用，不直接拥有 run 真值。
8. 多页时按 `prompts/slide-worker.md` 派发 worker，并为每次执行使用顶层 run lease。
9. worker 返回后调用顶层 `"$LEO_PPT" image record <run>`；失败保留在同一
   canonical state。聊天回复不改变状态，取消后的迟到 lease 会被拒绝。
10. 对每页分别关闭文字准确性、可读性/对比度、遮挡/截断、required asset、
    图表数据/单位/标签/排序和样张风格继承；任一失败都阻止该页 accepted，其他检查
    通过不能补偿。
11. 用 `"$LEO_PPT" run status <run> --json` 和 `"$LEO_PPT" image assemble <run>`
    确认全部页 recorded 后组装。缺页不得进入组装。
12. 重新打开 PPTX，核对页数、notes、结构和交付类型。最终任一 slide 图片 hash
    变化后，必须创建新的 artifact revision，重新组装、渲染并复验整套 PPTX；旧验证
    不得沿用。

最终 slide 图片必须来自确认的图片 backend。不得使用 Pillow、SVG、HTML、
canvas 或本地绘图生成“近似替代页”。required asset 无法正确进入页面时应
blocked，而不是省略后继续。

样张批准后，所有 slide job 继承同一 `sample_generation_method` 和 backend。
backend 切换需要用户重新确认并使旧 job fingerprint 失效。

## 五层非补偿质量门

- **内容事实：** 逐条对照来源与不可杜撰项；事实不明即阻断，不用视觉效果掩盖。
- **叙事结构：** 大纲有主线，每页只有一个任务，前后页能解释“为何此刻出现”。
- **视觉呈现：** 核心文字准确可读、对比充分、无截断遮挡，required asset 与图表真值
  完整，整套继承已批准样张而非逐页换风格。关键信息不得只靠颜色区分，必须同时有
  文字、标签、形状或位置等第二种线索；投屏距离下不可读的字号或低对比内容必须失败。
- **PPTX 结构：** 页数、页序、尺寸、notes、媒体引用和交付 hash 一致。
- **现场验收：** 自动检查只证明确定性合同；真实 provider、PowerPoint 桌面打开、
  投屏可读性与人工审美必须分别实际执行和记录，未执行时写 `not-run`。

## 确定性工具映射

- prompt/state：顶层 `image prepare`、`image record`、`run status`；
- provider：`image generate|generate-batch|edit`；
- 图片处理：`remove-chroma-key`；
- 组装：`assemble`，包括页序、压缩和 speaker notes。

图片式交付的公开状态入口统一使用顶层 `leo-ppt`；固定上游 bridge 仅承担无状态
prompt/provider/格式能力。旧上游的
`codex_ppt_runtime.py bootstrap|config|doctor` 由当前 Skill 的
`runtime_manager.py ensure|doctor|print-cli` 与 backend contract 替代，不能创建
第二套 runtime 或配置入口。
