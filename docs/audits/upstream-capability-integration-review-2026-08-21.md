# 两个上游能力集成正式审查报告

审查日期：2026-08-21  
被审项目：`leo-ppt-generator`  
上游基线：`codex-ppt-skill@f2ed80372f65bb05fe62dd07979b239a17ac065d`、`image-to-editable-ppt-skill@fb869763127fd31ba7288d905671ffc4ea542f60`

## 1. 最终结论

**修复后 verdict：`confirmed-complete`（固定上游、源码、确定性行为与离线编排范围）/ `field-not-proven`（真实 provider、在线 OCR、PowerPoint 与人工视觉范围）。**

43 个上游 Python 文件全部存在映射，最终快照中 37 个逐字节一致、6 个为可重放受控增强；60 个能力映射逐项执行全部通过，对应 42 个唯一 proof case；当前仓库 247 项测试全绿、coverage 87.53%；固定 editable 上游 82 项原生回归全绿；U0 clean-export 隔离 7 项全绿；required release pytest 已从临时 clean copy 构建 wheel，以绝对 wheel 路径安装并完成四条 route 与 replay。

初审发现的账本漏项、组装能力混记、旧报告漂移、补丁 replay 缺口和 wheel 自动化缺口已经逐项关闭。仍不能把该结论外推为现场质量完整：真实图片 provider、在线 OCR、Microsoft PowerPoint、真实多页 worker 和人工视觉验收没有运行，不能由 fixture 补偿。

按六态口径，本轮总体判定如下：

| 层次 | 判定 | 说明 |
| --- | --- | --- |
| 上游 Python 源文件覆盖 | `confirmed-complete` | 15 + 28 = 43 个上游 Python 文件全部映射 |
| 逐字节/受控差异治理 | `confirmed-complete` | 6 个差异文件均由 metadata 自动枚举，补丁可对固定上游 apply-check；低频依赖提示与 `.ppt` DPI 分支也有直接回归 |
| 已登记 60 项能力 | `confirmed-complete` | 60/60 映射逐项执行通过，披露 42 个唯一 proof case |
| 能力账本自身完整性 | `confirmed-complete`（当前独立基线） | C21 保留组装；新增 C25 组装保真与 E31 公式遗漏保护 |
| 四 route 离线闭环 | `confirmed-complete`（wheel fixture） | `generate`、`direct-editable`、`upgrade-full`、`upgrade-selected` 通过 |
| 最终 wheel 黑盒闭环 | `confirmed-complete`（required pytest） | clean copy 构建、绝对 wheel 安装、四 route + replay 已固化 |
| 真实 provider/OCR/PowerPoint/人工质量 | `not-proven` | 缺少不可替代现场证据 |

## 2. 初审发现与修复处置

### P1-01 能力账本漏记真实增强能力

`skills/leo-ppt-generator/_vendor/editable_ppt/editppt/runtime/validate_pptx.py` 已通过 `patches/0004-editable-expected-formula-inventory.patch` 增加 `expected_formula_inventory` 强制校验：source-side 已确认公式若未进入 worker 的 `formula_inventory`，validator 必须报错。对应测试 `test_confirmed_source_formula_inventory_cannot_be_omitted` 本轮通过。

初审时 `upstream-capabilities.yaml` 的 58 项中没有任何条目引用该能力或该测试。账本内的 E24 只覆盖“LaTeX 公式渲染与 fragment”，无法代表“已确认公式不得静默遗漏”。两者成功条件和失败条件不同，不能合并。

- **影响：** 58 项全部绿色仍无法证明当前完整能力集合全部登记；新增增强可能绕过逐能力发布门。
- **最强反方：** 该能力是当前项目新增增强，不属于两个上游原生能力，因此不必进入“上游能力账本”。
- **反方边界：** 如果账本只声称“原生上游能力”，反方成立；但当前账本同时收录 C03、E04、E27 和 X01-X04 等增强/编排能力，并声称覆盖“两个上游全功能集成”，因此不能选择性排除 E31。
- **修复状态：** `resolved`。新增 E31 并绑定专属 proof；60/60 逐项执行通过。
- **最小修复 owner：** `upstream-capabilities.yaml` 与 `test_feature_inventory.py` 的能力治理 owner。

### P1-02 既有审计报告与最终源码数量矛盾

初审时 `docs/upstream-feature-integration-audit-2026-08-21.md` 声称 43 个文件中“41 exact + 2 durability patch”，并在文件表中写 codex 14 exact/1 patch、editable 27 exact/1 patch。

最终源文件比对结果实际为：

- codex-ppt：15 个文件，13 exact + 2 patched（`slide_run_state.py`、`assemble_ppt.py`）；
- editable：28 个文件，26 exact + 2 patched（`deck_run_state.py`、`validate_pptx.py`）；
- 合计：39 exact + 4 patched。

- **影响：** 审计报告无法再作为当前快照的文件完整性证明，且掩盖两个新增强的治理责任。
- **最强反方：** 报告可能绑定的是补丁新增前的早期快照。
- **反方边界：** 报告没有不可变 source hash 来区分该早期快照，却使用当前同一天的最终性语言；读者会自然把它当作当前结论。
- **修复状态：** `resolved`。报告已更新为 39 exact + 4 patched，并披露 60 mappings / 42 unique proof cases。
- **最小修复 owner：** `docs/upstream-feature-integration-audit-2026-08-21.md` producer。

### P1-03 补丁自动治理只覆盖一半

初审时 `upstreams.yaml` 已登记 0001-0004 四个补丁，但自动测试只列出 0001 和 0002，README 也仍写“两个补丁”。修复过程中进一步发现 0003 使用无行号占位 hunk，实际上不是合法 unified diff；现已按固定上游与 vendor 的真实差异重建。

- **影响：** 0003/0004 日后可能对新 pin 失效，而现有 required test 仍然绿色；补丁目录说明会误导维护者。
- **最强反方：** vendor hash 测试已经 allowlist 四个差异文件，可以发现未登记 drift。
- **反方边界：** hash allowlist 只证明当前 vendor 与本地上游不同且名字获准，不证明补丁文件能从固定上游重放得到该差异。
- **修复状态：** `resolved`。测试从 `upstreams.yaml` 自动枚举全部四个补丁，四个 apply-check 均通过，README 同步四项职责和聚焦 proof。
- **最小修复 owner：** `tests/upstream/test_feature_inventory.py` 与 `patches/README.md`。

### P2-01 最终 wheel 四 route 通过，但 required test 没有固化该证明

初审时 `tests/release/test_installed_routes.py` 安装 runtime 源目录而不是构建产物；`test_wheel_release.py` 只检查 wheel inventory 和 entry point。

修复后 installed-route fixture 复用 clean-copy wheel builder，安装临时构建 wheel 的绝对路径，并使用不继承 system site packages 的隔离 venv，再运行四条 route 与 replay；该 required pytest 本轮通过。

- **影响：** 当前 wheel 已由本轮现场证明可运行，但该证明没有进入 required 自动门；未来 wheel 回归仍可能在 CI 中漏检。
- **最强反方：** pip 从源码目录构建的 wheel 与独立 `python -m build` 产物来自同一 source，风险很低。
- **反方边界：** 两次构建的环境、artifact identity 和输入树可能不同；发布验证要求证明最终交付物，而不是证明可重新构建。
- **修复状态：** `resolved`。artifact 与持续治理均由 required pytest 约束；临时构建物不使用仓库 `dist/` 旧 artifact。
- **最小修复 owner：** release test owner；让 fixture 接受并安装本轮构建 wheel 的绝对路径。

### P2-02 C21 的处置类别和 proof 绑定不准确

C21 初审时把基础组装和保真增强合并成“图片压缩与 PPTX 组装”。实际 `assemble_ppt.py` 已通过 0003 改为默认不做有损压缩，并引入 `contain/crop/stretch` 比例策略；两类行为具有不同成功与失败条件。

- **影响：** 账本不能精确说明“继承了什么、改变了什么、由什么直接证明”。
- **修复状态：** `resolved`。C21 只保留基础 PPTX 组装及 e2e proof；新增 C25，以 `enhanced` 和专属比例 proof 表达默认无损与比例保持。

### P2-03 映射执行次数不等于独立 Judge 数

修复前 58 个条目只引用 40 个唯一 proof case；修复后 60 个映射引用 42 个唯一 proof case。最大复用仍为一个 bridge 测试同时证明 C09-C14 六项能力。

复用本身不是错误，一个高质量场景可以同时验证多个相邻行为。但“逐项执行”只能证明映射命令分别运行，不能证明 Judge 的断言彼此独立。治理测试现同时冻结 60 条映射、42 个唯一 proof case 和最大复用数 6；报告不再把映射数包装成独立 Judge 数。

- **修复状态：** `resolved`。

## 3. 独立能力基线结果

本轮没有把旧账本作为基线来源，而是从两个上游的入口、文档、prompt、CLI、源码、测试和失败合同重新归纳。基线分为四组：

1. **codex-ppt 创作域：** 需求与页数、大纲/风格/backend/样张门禁、required assets、逐页 prompt、worker 隔离、dispatch/result/blocker/status、OpenAI-compatible/Atlas/generate-batch/edit/chroma、notes、PPTX 组装、最终报告与自定义风格。
2. **editable 重建域：** 图片/PDF/PPTX 规范化、Office 信任、OCR hints、worker/local claim、lease/reset、backend contract、图片/资产/formula 工具、page decision、manifest、page build/contact sheet/validate/finalize、notes、原子状态与运行管理。
3. **当前项目组合域：** 单一 Skill/CLI、run index、完整升级、选择性 hybrid、部分失败保留、partial confirmation 和 runtime manager。
4. **当前增强域：** 完整内容确认、Office fail-closed、状态原子性、图片组装保真、confirmed formula omission prevention。

修复后账本以 C25 和 E31 分别补齐图片组装保真、confirmed formula omission prevention，最终形成 60 个可追溯映射。该数量不是“源码功能总数”的数学真值，而是按当前可观察成功/失败条件原子化后的治理集合。

## 4. 源文件与补丁账本

| 上游范围 | 上游文件 | exact | patched | 结论 |
| --- | ---: | ---: | ---: | --- |
| `codex-ppt/scripts/**/*.py` | 15 | 12 | 3 | 全部映射 |
| `image-to-editable-ppt/cli/editppt/**/*.py` | 28 | 25 | 3 | 全部映射 |
| 合计 | 43 | 37 | 6 | 源文件覆盖与差异治理完整 |

六个差异文件均在 allowlist、vendor lock 和补丁目录中存在，required test 从 metadata 自动枚举并 apply-check 通过。bundle 额外包含 3 个 package `__init__.py`，vendor lock 共 46 个文件，`sync_upstreams.py --check` 返回 passed。

12 个 codex 内置风格文件逐字节匹配。Skill、docs、prompts 和 editable references 采用 merged/adapted 方式，不能通过 byte equality 判断，主要依赖合同 anchor 与行为测试。

## 5. 行为与跨阶段验证

| 验证 | 本轮结果 | 证据上限 |
| --- | --- | --- |
| 当前仓库完整 pytest | 247 passed，coverage 87.53% | 确定性代码、fixture 与发布合同 |
| 60 项账本逐条 proof | 60 passed / 0 failed | 60 个映射；42 个唯一 proof case |
| editable 固定上游回归 | 82/82 OK | 固定 commit 原生行为 |
| U0 clean export | 7/7 passed，无 skip | 同进程 import、资源、状态隔离、Office 和 worker gate |
| vendor sync | 46 files，passed | 当前 vendor lock/metadata 存在性与 hash |
| Skill quick validation | valid | 结构/发现面，不证明模型行为 |
| runtime build | sdist + wheel built | 构建成功 |
| installed built-wheel route | 1 required pytest case，四 route + replay 通过 | clean copy 构建与绝对 wheel 安装后的离线 fixture 闭环 |
| 图片比例与公式 omission 聚焦测试 | 均通过 | 两项当前增强的确定性行为 |

跨阶段确认包括：image delivery 作为 upgrade baseline；full/selected route 消费冻结页序、图片和 notes；editable 失败不破坏 image delivery；hybrid 保留页面 mode/order/notes；partial confirmation 绑定当前失败集合。上述结论来自 fixture，不外推到真实图片模型或人工视觉质量。

## 6. PPTX 质量分层

| 维度 | 状态 | 说明 |
| --- | --- | --- |
| OOXML/PPTX 可解析 | `confirmed-complete`（fixture） | python-pptx、validator 和 upstream builder 测试通过 |
| 图片式 PPT 页序/比例/notes | `confirmed-complete`（fixture） | notes 与默认比例保持有直接 proof |
| editable manifest 对象构建 | `confirmed-complete`（fixture） | 文本、形状、图片对象及 structural validation 有测试 |
| 禁止整页 raster 冒充 editable | `confirmed-complete`（合同 + fixture） | manifest/page decision 与 adapter 验证覆盖；未做 PowerPoint 人工检查 |
| 视觉相似、字体替换、遮挡 | `not-proven` | 无本轮独立人工验收 receipt |
| 公式保真 | `equivalent-adaptation`（确定性） | LaTeX fragment 与 omission gate 有测试；真实复杂公式现场未验 |
| theme/master 继承 | `intentional-exclusion` | 文档明确只承诺视觉重建与对象级可编辑，不保留输入模板语义 |
| Microsoft PowerPoint 桌面 | `not-proven` | 当前应用缺失 |

## 7. 现场证据与脱敏

本轮仅探测能力存在性，没有读取或输出凭据值：`OPENAI_API_KEY`、`ATLASCLOUD_API_KEY`、`PADDLE_OCR_TOKEN` 均为 absent；Microsoft PowerPoint 不存在；`soffice` 存在。本轮没有真实 provider、在线 OCR、PowerPoint 桌面或人工视觉验收。

所有新 evidence 均未保存令牌、认证文件原文、环境变量值、完整请求头或原始外部日志。无法安全输出的外部诊断在未来只能记录脱敏 reason code、退出状态、artifact hash 和 receipt metadata。

## 8. 最强支持论证与最强反方

### 支持“已经完整集成”的最强论证

两个固定上游 commit 与 metadata 一致；43 个上游 Python 文件全部映射；所有已知 vendor drift 均有可重放补丁；60 项映射逐项全绿；editable 原生回归、当前全套测试、U0 隔离和 wheel 四 route 全部通过。若“完整”限定为固定版本的确定性能力和离线编排机制，当前证据足以判定完整。

### 反对“已经完整集成”的最强论证

即使确定性门全部绿色，真实 provider、在线 OCR、PowerPoint、真实多页 worker 和人工视觉仍没有证据。若把“完整”解释为用户现场可用性或视觉等价，继续宣称无保留完整仍会越过证据上限。

### 真正分歧与裁决

分歧不在源码是否大量复用，而在“完整”的证据门槛。按本次 C 口径，独立基线、逐项映射、直接 proof、跨阶段 proof 均为非补偿门；这些确定性门现已关闭。现场门仍独立开放，因此最终结论必须分层，不能用 231/231 补偿未运行的真实环境验收。

## 9. 修复结果与后续现场验证

1. 已完成能力原子化、审计报告校准、六补丁自动 replay 和 required wheel 黑盒回归。
2. 已复验 43 文件账本、60 项逐条 proof、247 项全量回归、82 项上游回归、U0 7 项、vendor sync、Skill validation 和 wheel 四 route。
3. 后续在具备授权和环境后，分别执行真实图片 provider、在线 OCR、真实多页 worker、PowerPoint 打开/编辑和人工逐页视觉验收；每项独立出 receipt，不合并为一个“现场通过”。

## 10. 审查边界

- 初审为 report-only；用户随后授权本地修复。本轮未修改两个上游源码，只修改当前项目的能力账本、补丁治理、release test、文档和 evidence。
- 当前项目和两个上游工作树均存在预先已有或并行产生的 dirty 内容，结论绑定最终重新读取的 dirty snapshot，而非可提交 revision。
- `tests/integration/test_runtime_manager.py` 与 `tests/release/test_installer.py` 在修复期间由其他会话并行更新；本轮未覆盖这些文件，并在其最后观察到的修改之后重跑全量回归。
- 审查中曾看到 0004 补丁在早期目录清单缺失、随后出现；最终结论以最终快照为准，并把工作树漂移列为可复现性限制。
- Graphify/CodeGraph 仅作导航，所有重要结论均回到 source、tests、command results、contracts 和 artifacts。

## 11. 证据索引

- `docs/audits/upstream-integration/evidence/source-snapshot.json`
- `docs/audits/upstream-integration/evidence/upstream-file-ledger.yaml`
- `docs/audits/upstream-integration/evidence/inventory-diff.json`
- `docs/audits/upstream-integration/evidence/verification-summary.json`
- `docs/audits/upstream-integration/evidence/per-capability-results.json`
- `skills/leo-ppt-generator/upstream-capabilities.yaml`
- `skills/leo-ppt-generator/upstreams.yaml`
- `skills/leo-ppt-generator/vendor-lock.json`
- `tests/upstream/test_feature_inventory.py`
- `tests/upstream/test_capability_behaviors.py`
- `tests/release/test_installed_routes.py`
- `tests/release/test_wheel_release.py`
