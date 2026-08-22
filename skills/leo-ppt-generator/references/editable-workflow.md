# 可编辑 PPT 工作流

## 读取顺序

1. 图片/PDF 直接进入输入规范化；Office 输入先做可信确认与 fail-closed
   preflight。
2. 顶层调用 `"$LEO_PPT" editable prepare <run> [--pages <list>]`；它会通过固定 bridge
   调用 bundle 内的输入规范化器。PPTX 的可信确认和 `--office-trusted` 已在
   `run create` 冻结，bridge 仍会在上游解析器前拒绝宏、嵌入对象和 external
   relationship；旧 `.ppt` 一律先转 PDF。prepare 生成 deck manifest、page
   jobs、notes manifest、逐页 source、request 与 text hints。
3. 读取 `manifest-schema.md` 与 `page-decision-tree.md`。
4. 反复调用 `"$LEO_PPT" editable next <run> --json`。
   恰好一页时，CLI 明确允许后由当前 Agent claim local；多页必须派发真实
   worker。
5. 每个 page worker 只写自己的 page 目录，并按
   `prompts/page-worker.md` 产出 manifest、PPTX、preview、validation 与
   result。
6. 使用 `scripts/build-page-worker-prompt.py` 生成每页 prompt；真实派发后调用
   `"$LEO_PPT" editable dispatch`。parent 在 worker 返回后调用
   `"$LEO_PPT" editable record`；validation 未通过不得 record。
7. 全部目标页 recorded 后调用 `"$LEO_PPT" editable finalize <run>`，并由 manifest
   重新构建最终 deck。
8. 核对页数、页序、notes、media relationship、asset hash、required text 和
   full-slide-raster-overlay 禁止项。
9. 对每页逐项检查字体可用性与替代记录、CJK/Latin 字号、文字溢出、对象遮挡、
   前景/背景对比、画布边界、图表数据/单位/标签/排序、对象级可编辑性。任何 error
   都阻止 record/finalize，不能用其他绿色项补偿。

`manifest.json` 是对象级页面的构建权威；`PageArtifact` 只用于跨能力交接，
不能替代 manifest。worker 失败后先诊断并改变条件，再 reset 和重新派发。

## 可编辑交付质量门

- 正文、标题、图表文字必须是可选中的原生文本；字体缺失时记录明确替代字体并重新
  测量，不得仅靠缩到不可读来消除 overflow。
- 文本框、图片、图形、表格和公式不得互相遮挡或越出画布；预览近似通过不代表
  PowerPoint 排版一定通过。
- 关键信息不得只靠颜色表达；状态、系列和风险等级同时使用文字、标签、形状、线型或
  位置等第二种线索。字体替代后还要重新检查对比、投屏字号和长文本换行。
- 图表必须保留真实数值、单位、标签、图例和排序语义；无法从来源确认时标记失败，
  不得绘制“看起来合理”的数据。
- 整页 source 截图、整页 clean base 或覆盖全画布的栅格对象不能作为 editable
  交付伪装，即使上方叠加少量文本框也必须失败。
- 自动 validator 证明 manifest、对象与结构合同；字体替代后的视觉效果、桌面打开、
  动画/特殊效果和人工等价性必须另行实际验收，未执行不得声称通过。

## 完整能力入口

统一前缀为 `"$LEO_PPT" upstream editable-ppt --`：

- `prepare`：图片、PDF、可信 Office 规范化、notes 与 text hints；
- `run next|status|backend|dispatch|record|reset|hints|finalize`：完整领域状态；
- `page hints|build|contact-sheet|validate`：逐页确定性工具；
- `image generate|edit|import|process-sheet`：图片后端、provenance、去背与拆图；
- `formula render-latex`：高保真公式资产与 manifest fragment；
- `doctor`：固定上游诊断兼容面；顶层 readiness 仍以当前 runtime manager 为准；
- `config|setup`：已适配为 replaced 说明。正常流程使用当前 runtime manager 和
  run-level backend contract；任何 `--api-key`、`--paddle-ocr-token` 或
  `--import-codex-ppt` 写入请求都会被拒绝。
