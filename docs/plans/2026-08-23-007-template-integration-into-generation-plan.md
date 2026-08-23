# 计划 007：模板高质量集成到 PPT 生成流程

> 项目负责人视角的计划文档。记录目标、链路调研、差距分析、集成方案、执行与验收。
> 状态：调研完成 → 方案确定 → 执行中

## 一、项目目标

leo-ppt-generator 从文章/报告/笔记/大纲生成**图片式 PPTX**（每页一张 16:9 AI 生成图），
并可升级为对象级可编辑/hybrid。质量底线：门控流程（大纲→逐页稿→样张→逐页质检）、
确定性 CLI、不可变 runtime。

**差异化优势**（vs ppt-master / PPTAgent / presenton / codex-ppt-skill）：

1. 图片式 + 可编辑升级**双能力**（generate + direct-editable + upgrade-full/selected）；
2. **门控式质量流程**（五层非补偿质量门 + 对抗式视觉质检，见 `references/visual-qa.md`）；
3. **模板体系深度**（139 风格 + 117 分节轴规范，六轴正交 + 页级版式 + 页面语义）；
4. 确定性 `leo-ppt-machine/v1` CLI + 不可变受管 runtime。

## 二、链路理解（调研结论）

```
输入 → 冻结内容合同 → 大纲 → 逐页稿
  → 选视觉风格（agent 读风格路由/风格库）→ 样张确认
  → deck_spec(slides.json)  ← agent 写：style(完整 brief) / slides[].layout / ...
  → `leo-ppt image prepare --slides` 冻结
  → prepare_slide_prompts.py 的 _build_prompt 拼每页 prompt
       ├─ Global Style 块 ← deck.get("style")   ← 已支持任意 dict 注入
       ├─ Layout 块      ← slide.get("layout")  ← 已支持任意 dict 注入
       └─ Universal Constraints
  → slide-worker 按 prompt 生成每页图
  → image record → image assemble → PPTX
```

**关键发现**：`_build_prompt` 的 `_format_block` 对任意 dict 都做 JSON 格式化注入，
**注入链路本身是通的**。真正的缺口是：

1. 模板内容（图片渲染 paste-ready 段落、版式骨架、论证模式、信息图类型）是
   **markdown 分节文档**，代码读不到（`styles.py` 的 `_is_style_md` 判「无 JSON」排除）；
2. agent 写 deck_spec 时**靠手动读文档、自由文本合并**，无确定性支持、无验证；
3. 选择结果不可复现（同一个内容，两个 agent 写的 style 不同）。

## 三、集成方案（确定）

**核心：新增「模板渲染」能力 —— `leo-ppt style render`，让模板内容由 CLI 从模板库确定性渲染，agent 只做「选 → render → 写 deck_spec」。**

不改 `_vendor`（不可变上游），不改 `_build_prompt`（注入链路已通）。在 leo-ppt 自己的层：

1. **新模块 `templates.py`**（与 `styles.py` 并列）：
   - 结构化解析 08 图片渲染（paste-ready 段落 + 线条纹理深度表）、12 版式库（用途/内容类型/骨架）、
     07 信息图类型（构图骨架）、06 论证模式（论证骨架）——它们都是固定分节的 markdown。
   - `compose_style(visual_style)`：视觉风格 brief + 配对图片渲染 paste-ready + 论证模式，
     返回「完整注入 brief」（agent 直接写进 `deck_spec.style`）。
   - `compose_layout(layout_name, image_type)`：版式骨架 + 信息图类型骨架，
     返回「每页 layout 注入块」（agent 写进 `slides[].layout`）。
2. **新 CLI 命令 `leo-ppt style render <name> [--mode <mode>] [--layout <layout>]`**：
   输出合并后的注入内容（JSON），agent 复制进 deck_spec。
3. **SKILL.md / image-deck-workflow.md 指令更新**：明确「选模板后调 `style render`
   得到确定性注入内容，写进 deck_spec；不得自由文本手写 style」。

**为什么这个方案「高质量」**：

- **确定性**：同一个模板选择，render 输出逐字节一致（可验证、可复现）；
- **不改上游**：`_vendor` 保持不可变，模板加载在 leo-ppt 层；
- **模板内容真正进入生成流程**：render 输出 → deck_spec.style → _build_prompt → prompt；
- **选择质量可验证**：deck_spec 里能审计「选了哪个渲染/模式/版式」，而非自由文本。

## 四、执行步骤

- [x] 1. 调研：链路 + 注入点 + 架构约束（本计划第二节）
- [x] 2. 实现 `templates.py`（结构化解析 08/12/07/06 + compose_style/compose_layout）
- [x] 3. 实现 `leo-ppt style render` CLI（含 `--mode/--layout/--image-type/--list-templates`）
- [x] 4. 更新 SKILL.md 指令（选模板后调 `style render` 确定性注入，禁止自由文本手写 style/layout）
- [x] 5. 单元测试 `tests/unit/test_templates.py`（10 个用例，全过；现有 4 个 styles 测试不破坏）
- [x] 6. 验收：`style render 玻璃拟态风 --mode 结论先行金字塔 --layout P6 --image-type 漏斗图`
   输出写进 deck_spec → `prepare_slide_prompts.py` 生成 prompt，四项注入全部确认：
   ✓ glassmorphism paste-ready 渲染 · ✓ 论证模式 · ✓ 版式骨架 · ✓ 信息图类型

## 五、验收标准（全部达成）

1. ✅ `leo-ppt style render` 输出含：视觉风格 brief + paste-ready 段落 + 论证骨架 + 版式骨架 + 信息图骨架；
2. ✅ render 输出逐字节确定（`test_compose_style_is_deterministic` 验证）；
3. ✅ 现有 4 个 styles 测试不破坏 + 新增 10 个 templates 测试通过；
4. ✅ 端到端：render 输出 → deck_spec.style/layout → `prepare_slide_prompts.py` 的
   Global Style / Layout 块，四项模板内容全部注入生成 prompt。

## 六、遗留（明确不属本轮）

- 模板库的 markdown 轴文档仍在子目录（`list_styles` 只枚举含 JSON 风格）——`style render`
  通过 `templates.py` 直接路径读取，已绕过此限制，无需改 `list_styles`。
- `chart-integration.md`（ECharts SSR 图表注入）仍为设计文档，未落地代码——属下一计划。
- 真实图片生成验证（拿材料跑一次 generate 全链路）仍是检验模板效果的最终标准。

## 七、收尾归档（2026-08-23）

状态：**本阶段收尾**。模板高质量集成到生成流程的目标已达成并验收（326 单元测试全绿），
以下遗留项显式归档，转入下一阶段：

| 遗留项 | 归档去向 | 负责人 |
|---|---|---|
| 真实生成验证（拿真实材料跑 generate 全链路） | 下一阶段 P0——模板效果真伪试金石 | 用户发起 |
| `chart-integration.md` ECharts SSR 图表注入代码落地 | 下一阶段 P1（解决数据页图表失真） | 待排期 |
| git 提交（72 个文件：3 源码 + 256 模板实体 + 测试 + 文档） | 用户确认后提交（项目纪律：不代提交） | 用户 |

收尾判定：**模板集成阶段完成**；「项目彻底完成」需以真实生成验证为最终证据。

## 八、真实生成验证闭环（2026-08-23，P0 完成）

真实材料：人教版五年级上册第一单元第 1 课《小数乘整数》，8 页。

端到端链路全部真实跑通：内容 → `style render` 模板确定性注入（数学可视化教学风 +
教学分解 + 手绘笔记渲染 + 8 版式）→ 8 页 prompt → openai-compatible 中转站真实出图
（每页 40-90s）→ `image record`（revision 乐观锁）→ `image assemble` →
`image_delivery_completed`。交付：8 页 1536×1024 PPTX（桌面），**人工质检 accepted**。

验证发现并修复 6 项：① 02 行业 48 风格无配对渲染（已批量补 47+1 条子类默认映射）；
② `_field` 空值跨空行（已修）；③ P1 版式缺骨架（已补）；④ 安装后 `parents[3]` 路径
失效致 `style list` 返回 0（launcher 导出 `LEO_PPT_BUNDLE` 已修）；⑤ 官方 openai key
401（换中转站）；⑥ `image record` 的 `--expected-revision` 对应 slide_jobs 而非
run.json（已掌握语义并正确执行）。

结论：**模板体系经真实生成验证，链路、注入、出图、组装、质检全闭环通过。**
