# Editable CLI Helper

本文件是对象级可编辑能力的命令手册。所有命令都通过当前受管 runtime 的唯一入口
执行。先从 Skill 安装目录解析绝对路径：

```bash
LEO_PPT="$(python "$SKILL_DIR/scripts/runtime_manager.py" print-cli)"
```

后续命令一律使用：

```bash
"$LEO_PPT" upstream editable-ppt -- <command> [args...]
```

不得安装或调用旧 `editppt`。完整参数以
`"$LEO_PPT" upstream editable-ppt -- <command> --help` 的当前输出为准。工作流策略位于
`SKILL.md`，对象决策位于 `page-decision-tree.md`，字段合同位于
`manifest-schema.md`。

## 命令树

```text
prepare
run next|status|backend|dispatch|record|reset|hints|finalize
page hints|build|contact-sheet|validate
image generate|edit|import|process-sheet
formula render-latex
```

`setup` 已由 `runtime_manager.py ensure` 替代；`config` 已由每个 run 的
`backend-contract-v1` 替代。不要向旧配置面写入凭据。

## 准备与推进

```bash
"$LEO_PPT" upstream editable-ppt -- prepare input.png
"$LEO_PPT" upstream editable-ppt -- prepare input.pdf
"$LEO_PPT" upstream editable-ppt -- prepare input.png --image-backend builtin-imagegen
"$LEO_PPT" upstream editable-ppt -- run next <run> --json
"$LEO_PPT" upstream editable-ppt -- run status <run>
```

`prepare` 规范化单图、多图、PDF 或通过顶层安全 preflight 的可信 PPTX，生成
`deck_manifest.json`、`page_jobs.json`、`notes_manifest.json`、逐页 `source.png`、
`page_request.json` 和文字 hints。在线 OCR 需要网络时，只上传当前转换任务所需页面，
并按宿主规则取得授权；无 token 时使用离线几何检测，不能声称已识别文字内容。

`run next` 的稳定阶段包括：单页本 Agent claim、多页 worker 派发、等待、配置 backend
和 finalize。多页必须先由宿主真实创建 worker，不能用本地循环伪装派发。

## Worker Prompt 与状态

先用 Skill 自带脚本生成 prompt：

```bash
python "$SKILL_DIR/scripts/build-page-worker-prompt.py" <run> \
  --page page_001 \
  --cli "$LEO_PPT" \
  --out <absolute-run-dir>/pages/page_001/worker-prompt.md
```

真实 worker 创建成功后记录 dispatch：

```bash
"$LEO_PPT" upstream editable-ppt -- run dispatch <run> \
  --page page_001 --agent-id <worker-id> \
  --prompt-file <absolute-run-dir>/pages/page_001/worker-prompt.md
```

恰好一页且顶层合同允许当前 Agent 执行时，使用同一 prompt 并增加 `--local`。完成后：

```bash
"$LEO_PPT" upstream editable-ppt -- run record <run> \
  --page page_001 --agent-id <worker-id>
"$LEO_PPT" upstream editable-ppt -- run reset <run> \
  --page page_001 --agent-id <worker-id> --confirm-lost
"$LEO_PPT" upstream editable-ppt -- run finalize <run>
```

只有 worker 已终止、用户取消或重复可达性检查证明丢失时才能 `reset --confirm-lost`。
`record` 要求全部页面产物存在，且 `validation.json` 顶层 `passed: true`；失败页不能
登记为完成。finalize 只读取已登记页面的 `manifest.json`，按原页序重建整套 PPTX。

## 页面构建与验证

```bash
"$LEO_PPT" upstream editable-ppt -- page hints pages/page_001
"$LEO_PPT" upstream editable-ppt -- page build pages/page_001
"$LEO_PPT" upstream editable-ppt -- page contact-sheet pages/page_001
"$LEO_PPT" upstream editable-ppt -- page validate pages/page_001
"$LEO_PPT" upstream editable-ppt -- run hints <run>
```

`page build` 从权威 `manifest.json` 生成 `page.pptx` 和 `preview.png`；不得用另一套
页面脚本绕开 manifest。`contact-sheet` 生成原图与预览对照，`page validate` 执行与
`run record` 相同的 manifest 合同检查。最终返回前必须修复所有 error；warning
能否接受由 `page-decision-tree.md` 决定。

## 图片生成、编辑与资产登记

生成和编辑只作为 `page_request.json.image_backend.fallback_policy` 明确允许的
fallback；多个页面内图片任务串行执行：

```bash
"$LEO_PPT" upstream editable-ppt -- image generate \
  --prompt-file prompt.txt \
  --out pages/page_001/assets/support.png

"$LEO_PPT" upstream editable-ppt -- image edit \
  --image pages/page_001/source.png \
  --prompt-file clean-base.prompt.txt \
  --out pages/page_001/assets/clean-base.png
```

常用受控参数包括 `--model`、`--size`、`--quality`、`--force`、`--dry-run`、
`--timeout`，编辑还支持 `--mask`。不要扫描“最新文件”；只能使用当次工具明确返回的
结果路径。

选中结果后登记 provenance，再处理稀疏色键资产表：

```bash
"$LEO_PPT" upstream editable-ppt -- image import pages/page_001 \
  --job-id icon-sheet \
  --source-image <absolute-generated-path> \
  --dest assets/icon-sheet.png \
  --role asset_sheet \
  --backend <actual-backend>

"$LEO_PPT" upstream editable-ppt -- image process-sheet pages/page_001 \
  --job-id icon-sheet \
  --asset-sheet-source assets/icon-sheet.png \
  --assets-dir assets/icons
```

`--backend` 必须记录真实生产者；只有与 backend contract 相符时才可记录
`--fallback-reason`。色键、背景/前景拆分和重新生成规则见
`page-decision-tree.md`。

## 公式

```bash
"$LEO_PPT" upstream editable-ppt -- formula render-latex pages/page_001 \
  --tex "\\sum_{i \\in N} p_{ij}x_{ij} \\ge a_j u_j" \
  --out assets/formula_001.svg \
  --box 100,120,360,80 \
  --id formula_001 \
  --fragment assets/formula_001.fragment.json
```

Agent 负责忠实转录 LaTeX；CLI 只负责渲染并输出 manifest fragment。公式图像仍须
具备源像素坐标、provenance 和页面视觉复核。
