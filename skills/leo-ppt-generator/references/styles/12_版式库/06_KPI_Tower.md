# 版式：P6 · KPI Tower · 不等高柱状 KPI

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 4 项数据用视觉高度表达层级差异。

**适用内容类型:** **4 项可比量化数据**(必须有真实数值,bar 高度由数据决定)。典型如:成本、容量、计数、效率指标。**禁止**用于无数据的概念列举(那是 P4/P5 的事)。

**骨架:** 4 列均分,每列底部一根不同高度的 IKB 蓝矩形(数据决定高度)+ 顶部图标 + 中段巨数 + 底部标签。

**关键类:** `.kpi-tower-row` `.bar-tower`(min-height:6vh, max:36vh) `.tower-cap`

**动效 recipe:** `tower-grow` — 标签先入 → 数字 scale 弹入 → tower scaleY 从 0 拉起(transform-origin:bottom)

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。