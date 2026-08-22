# 两个上游全功能集成审计（2026-08-21）

## 结论

本审计按“源文件完整、顶层可达、合同未弱化、存在直接证明”四个条件逐项核对，
不以文件总数或抽样测试代替功能集成。当前固定源为：

- `codex-ppt-skill@f2ed80372f65bb05fe62dd07979b239a17ac065d`
- `image-to-editable-ppt-skill@fb869763127fd31ba7288d905671ffc4ea542f60`

源码层共核对 43 个上游 Python 文件：codex-ppt 15 个、editable 28 个。43 个
全部有 vendored 映射；其中 37 个逐字节相同，6 个是已登记、已测试且可对固定上游
重放的增强（`slide_run_state.py`、`assemble_ppt.py`、`deck_run_state.py` 与
`validate_pptx.py`、`remove_chroma_key.py`、`_input_normalization.py`）。bundle 另有 3 个 package
`__init__.py`，因此 vendor lock 记录 46 个 Python 文件。

语义层共核对 60 个能力映射：47 个直接集成、10 个增强、2 个适配、1 个替代。
这些映射引用 42 个唯一 pytest node id；测试复用被显式披露，不把 60 次执行描述为
60 个独立 Judge。每项都有当前顶层入口或明确替代入口。机器可读权威为
`skills/leo-ppt-generator/upstream-capabilities.yaml`，一致性测试为
`tests/upstream/test_feature_inventory.py`。

## 判定口径

- `integrated`：保留上游语义，并能从唯一 Skill/CLI 工作流到达。
- `enhanced`：保留上游语义，同时增加安全、跨阶段或交付能力。
- `adapted`：因单一 Skill/runtime/config 边界改变入口，但用户能力保留。
- `replaced`：旧安装/runtime 管理能力由当前受管 runtime 等价替代。
- 只有源码被复制但没有入口或 proof 的条目不得标为已集成。

## 逐项功能账本

| ID | 上游 | 功能 | 处置 | 当前 owner/入口 | 直接 proof |
| --- | --- | --- | --- | --- | --- |
| C01 | codex-ppt | 需求理解与页数边界 | integrated | `SKILL.md` | `tests/skill-evals/test_skill_contract.py` |
| C02 | codex-ppt | 大纲确认门禁 | integrated | `references/image-deck-workflow.md` | `tests/skill-evals/test_skill_contract.py` |
| C03 | codex-ppt | 完整逐页内容确认 | enhanced | `SKILL.md` | `tests/skill-evals/test_skill_contract.py` |
| C04 | codex-ppt | 视觉方向确认 | integrated | `references/style-library.md` | `tests/upstream/test_capability_behaviors.py` |
| C05 | codex-ppt | 12 套内置风格 | integrated | `references/styles` | `tests/upstream/test_feature_inventory.py` |
| C06 | codex-ppt | 用户自定义风格保存与优先级 | adapted | `references/style-library.md` | `tests/upstream/test_capability_behaviors.py` |
| C07 | codex-ppt | 图片 backend 确认与冻结 | integrated | `references/backend-selection.md` | `tests/unit/test_backend_contract.py` |
| C08 | codex-ppt | 单页样张批准与 generation method 继承 | integrated | `references/image-deck-workflow.md` | `tests/skill-evals/test_skill_contract.py` |
| C09 | codex-ppt | required asset 严格映射 | integrated | `references/image-deck-workflow.md` | `tests/integration/test_upstream_bridge.py` |
| C10 | codex-ppt | 逐页 prompt 生成 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| C11 | codex-ppt | worker dispatch 与并发槽 | integrated | `prompts/slide-worker.md` | `tests/integration/test_upstream_bridge.py` |
| C12 | codex-ppt | dispatch 状态记录 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| C13 | codex-ppt | 结果记录与 backend provenance 校验 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| C14 | codex-ppt | blocker 记录 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| C15 | codex-ppt | run status 与缺页拒绝 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/unit/test_adapters.py` |
| C16 | codex-ppt | OpenAI-compatible 图片生成 | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/image_gen.py` | `tests/upstream/test_capability_behaviors.py` |
| C17 | codex-ppt | AtlasCloud generate/edit provider | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/image_providers/atlascloud.py` | `tests/upstream/test_capability_behaviors.py` |
| C18 | codex-ppt | generate-batch | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/image_gen.py` | `tests/upstream/test_capability_behaviors.py` |
| C19 | codex-ppt | 图片编辑与多参考图 | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/image_gen.py` | `tests/upstream/test_capability_behaviors.py` |
| C20 | codex-ppt | chroma-key 去背 | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/remove_chroma_key.py` | `tests/upstream/test_capability_behaviors.py` |
| C21 | codex-ppt | PPTX 组装 | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/assemble_ppt.py` | `tests/e2e/test_offline_routes.py` |
| C22 | codex-ppt | speaker notes 写入 | integrated | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/assemble_ppt.py` | `tests/upstream/test_capability_behaviors.py` |
| C23 | codex-ppt | runtime bootstrap/config/doctor | replaced | `scripts/runtime_manager.py` | `tests/integration/test_runtime_manager.py` |
| C24 | codex-ppt | 最终报告与限制声明 | integrated | `SKILL.md` | `tests/upstream/test_capability_behaviors.py` |
| C25 | codex-ppt | 默认无损与比例保持组装 | enhanced | `runtime/src/leo_ppt_generator/_vendor/codex_ppt/assemble_ppt.py` | `tests/upstream/test_capability_behaviors.py::test_image_deck_assembly_preserves_source_ratio_by_default` |
| E01 | image-to-editable-ppt | 单图与多图输入规范化 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_stable_workflow_commands.py` |
| E02 | image-to-editable-ppt | PDF 栅格化与页序 | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/_input_normalization.py` | `tests/upstream/test_capability_behaviors.py` |
| E03 | image-to-editable-ppt | PPTX 栅格化与 notes 提取 | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/_input_normalization.py` | `tests/upstream/test_capability_behaviors.py` |
| E04 | image-to-editable-ppt | Office 信任与 active/external fail-closed | enhanced | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| E05 | image-to-editable-ppt | prepare deck/page manifests | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/prepare_deck_run.py` | `tests/integration/test_stable_workflow_commands.py` |
| E06 | image-to-editable-ppt | 离线 builtin-ink hints | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/text_hints.py` | `tests/upstream/test_capability_behaviors.py` |
| E07 | image-to-editable-ppt | PaddleOCR-VL hints | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/paddle_text_hints.py` | `tests/upstream/test_capability_behaviors.py` |
| E08 | image-to-editable-ppt | run next/status 与并发槽 | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/unit/test_adapters.py` |
| E09 | image-to-editable-ppt | 单页 local claim | integrated | `references/editable-workflow.md` | `tests/unit/test_adapters.py` |
| E10 | image-to-editable-ppt | 多页真实 worker 门禁 | integrated | `prompts/page-worker.md` | `tests/unit/test_adapters.py` |
| E11 | image-to-editable-ppt | worker prompt 构建 | integrated | `scripts/build-page-worker-prompt.py` | `tests/integration/test_upstream_bridge.py` |
| E12 | image-to-editable-ppt | dispatch 活跃 lease | integrated | `runtime/src/leo_ppt_generator/upstream_bridge.py` | `tests/integration/test_stable_workflow_commands.py` |
| E13 | image-to-editable-ppt | page record 与顶层 passed 校验 | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/record_page_result.py` | `tests/unit/test_adapters.py` |
| E14 | image-to-editable-ppt | lost worker reset | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/reset_page_job.py` | `tests/integration/test_stable_workflow_commands.py` |
| E15 | image-to-editable-ppt | run-level backend contract | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/configure_image_backend.py` | `tests/unit/test_backend_contract.py` |
| E16 | image-to-editable-ppt | Codex OAuth/OpenAI-compatible generate/edit | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/image_gen.py` | `tests/upstream/test_capability_behaviors.py` |
| E17 | image-to-editable-ppt | 图片 import 与 provenance | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/record_imagegen_result.py` | `tests/upstream/test_capability_behaviors.py` |
| E18 | image-to-editable-ppt | asset sheet 去背与拆分 | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/process_asset_sheet.py` | `tests/upstream/test_capability_behaviors.py` |
| E19 | image-to-editable-ppt | 背景/前景/原生对象决策树 | integrated | `references/page-decision-tree.md` | `tests/upstream/test_capability_behaviors.py` |
| E20 | image-to-editable-ppt | manifest schema 与对象 provenance | integrated | `references/manifest-schema.md` | `tests/unit/test_schemas.py` |
| E21 | image-to-editable-ppt | manifest 构建 page.pptx/preview | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/build_pptx_from_manifest.py` | `tests/unit/test_adapters.py` |
| E22 | image-to-editable-ppt | page contact sheet | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/make_page_contact_sheet.py` | `tests/upstream/test_capability_behaviors.py` |
| E23 | image-to-editable-ppt | page/deck structural validation | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/validate_pptx.py` | `tests/e2e/test_offline_routes.py` |
| E24 | image-to-editable-ppt | LaTeX 公式渲染与 fragment | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/formula_renderer.py` | `tests/upstream/test_capability_behaviors.py` |
| E25 | image-to-editable-ppt | manifest 权威全 deck finalize | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/finalize_deck_run.py` | `tests/integration/test_stable_workflow_commands.py` |
| E26 | image-to-editable-ppt | speaker notes hash 保留 | integrated | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/build_pptx_from_manifest.py` | `tests/upstream/test_capability_behaviors.py` |
| E27 | image-to-editable-ppt | 原子状态与并发锁 | enhanced | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/deck_run_state.py` | `tests/boundary/test_vendor_state.py` |
| E28 | image-to-editable-ppt | setup/config/doctor 兼容面 | adapted | `scripts/runtime_manager.py` + `config/backend_contract.py` + `upstream_bridge.py` | `tests/integration/test_upstream_bridge.py` |
| E29 | image-to-editable-ppt | full editable 交付 | integrated | `runtime/src/leo_ppt_generator/editable/adapter.py` | `tests/e2e/test_offline_routes.py` |
| E30 | image-to-editable-ppt | selected-page PageArtifact 交接 | enhanced | `runtime/src/leo_ppt_generator/contracts.py` | `tests/unit/test_hybrid_assembler.py` |
| E31 | image-to-editable-ppt | 已确认公式清单静默遗漏保护 | enhanced | `runtime/src/leo_ppt_generator/_vendor/editable_ppt/editppt/runtime/validate_pptx.py` | `tests/upstream/test_capability_behaviors.py::test_confirmed_source_formula_inventory_cannot_be_omitted` |
| X01 | combined | image deck 整套升级 editable | enhanced | `SKILL.md` | `tests/e2e/test_offline_routes.py` |
| X02 | combined | selected-page hybrid | enhanced | `runtime/src/leo_ppt_generator/hybrid/assembler.py` | `tests/unit/test_hybrid_assembler.py` |
| X03 | combined | partial-hybrid 显式确认 | enhanced | `runtime/src/leo_ppt_generator/hybrid/assembler.py` | `tests/unit/test_hybrid_assembler.py` |
| X04 | combined | 单一 runtime/CLI/Skill | enhanced | `scripts/runtime_manager.py` | `tests/integration/test_runtime_manager.py` |

## 文件级完整性

| 上游 | 核对范围 | 结果 |
| --- | --- | --- |
| codex-ppt | `skills/codex-ppt/scripts/**/*.py` | 15/15 有映射；12 个 exact，3 个登记 patch |
| editable | `skills/image-to-editable-ppt/cli/editppt/**/*.py` | 28/28 有映射；25 个 exact，3 个登记 patch |
| codex worker prompt | `prompts/slide-worker.md` | 保留上游合同并适配唯一 `leo-ppt` CLI |
| editable worker prompt | `prompts/page-worker.md` | 保留上游合同并适配唯一 `leo-ppt` CLI |
| editable manifest schema | `references/manifest-schema.md` | 保留字段合同并适配唯一 CLI 示例 |
| codex 内置风格 | `references/*.md` | 12/12 byte-identical |
| editable prompt builder | `scripts/build-page-worker-prompt.py` | 已适配唯一 CLI，并有真实产物测试 |
| 两套旧 runtime/CLI | bootstrap/config/install | 不要求外部安装；由受管 runtime 和 bridge 替代 |

## 当前源仓库的脏改动边界

`codex-ppt-skill` 当前工作树另有文档改动和未跟踪
`docs/execution-flow.md`。该文档明确把 `content_approval.json` 描述为“建议
优化、当前尚未实现”，不是当前上游运行功能。本顶层 Skill 已保留更严格的完整逐页
内容确认门禁，但本审计没有把该提案伪报成已存在的确定性上游状态机。

`image-to-editable-ppt-skill` 的 HEAD 与固定 commit 一致；当前另有治理文件改动及未跟踪
`skills/image-to-editable-ppt/cli/uv.lock`，本审计只从 `git archive HEAD` 构造 clean
export 运行原生回归，不把工作树残留混入固定版本证据。

## 已执行的直接验证

- bridge 完整入口与真实 codex prompt/asset/dispatch/result/blocker/status 流程：
  `tests/integration/test_upstream_bridge.py`。
- 43 个源 Python 文件逐个 hash 对照、6 个补丁自动枚举与重放、12 份 exact style
  asset 对照、60 个能力 owner/proof 检查：
  `tests/upstream/test_feature_inventory.py`。
- 60 条 `proof_case` 按账本顺序逐条执行，本轮结果 `60 passed / 0 failed`，对应
  42 个唯一 proof case；高复用 proof 的上限为 6 个映射。
- 当前仓库全套行为、边界、e2e 与覆盖率测试：`247 passed`，coverage `87.53%`。
- editable 固定上游原生 82-test 回归，以及 codex clean-export fixture。
- required release pytest 从临时 clean copy 构建 wheel，以绝对 wheel 路径安装，并完成
  四 route 与 replay 黑盒验证。

## Claim ceiling

本审计证明源码、入口、合同和离线/fixture 行为已集成；它不能替代需要外部环境的
现场结果。真实图片 provider、在线 PaddleOCR、Microsoft PowerPoint 桌面和人工
视觉等价仍必须分别报告，未运行时不得外推为通过。
