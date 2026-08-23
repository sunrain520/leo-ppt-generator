# 版式：P17 · System Diagram · 同心圆系统图

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 层级架构(core→middle→outer)、生态地图。

**适用内容类型:** **严格三层嵌套关系**(core 内核 / middle 中间层 / outer 外圈)。典型如:技术栈层级、生态分层、影响力辐射。**非三层结构禁用**(扁平用 P4,层级不清用 P5)。

**骨架:** 左半屏标题 + 三段说明 / 右半屏 SVG 三层同心圆 + 标签外引线。

**关键类:** `.system-diagram` `.sys-svg` `.sys-label`

**动效 recipe:** `system-diagram` — 同心圆从外向内 scale 入 → 标签序列出现  ---

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。