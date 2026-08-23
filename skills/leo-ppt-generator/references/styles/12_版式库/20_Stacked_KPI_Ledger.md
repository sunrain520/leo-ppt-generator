# 版式：P20 · Stacked KPI Ledger · 纵向账单 KPI

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 4-6 行核心数据账单式展示(每行=数字+标签+图标)。

**适用内容类型:** **4-6 项核心数据账单**(每行必须有真实数值 + 标签 + 图标)。垂直 ledger 形式适合财务数据、KPI 仪表板、关键指标列表。比 P6 KPI Tower 容纳数据更多但视觉化弱(无 bar 高度对比)。

**骨架:** 每行一道 hairline 分隔 / 左侧巨数(限高 `min(13vw,16vh)` 防溢出) / 中部标签 / 右侧 lucide 图标。

**关键类:** `.stacked-ledger` `.ledger-row`(border-bottom:1px solid var(--border-subtle))`.ledger-num`

**动效 recipe:** `stacked-ledger` — 每行数字升起 → 标签左滑 → 图标 pop(每行 180ms 错开)

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。