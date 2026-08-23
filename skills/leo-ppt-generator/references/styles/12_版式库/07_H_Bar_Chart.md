# 版式：P7 · H-Bar Chart · 横向条形图

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 多项排名比较 / 占比对比(5-10 项)。

**适用内容类型:** **5-10 项可比量化数据**(必须有真实百分比 / 评分 / 数值,bar 宽度由数据决定)。典型如:benchmark 排名、市场份额、问卷占比。⚠️ **严禁用于无量化数据的概念列举**(那是 P4/P5/P15)— 编造数字会被识破。

**骨架:** 顶部大标题 / 中段空 / 下半部条形列表(每行:文字标签 + 1px 蓝条 0→target width + 末端数字)。

**关键类:** `.h-bar-chart` `.bar-row` `.bar-fill`(scaleX 动画)

**动效 recipe:** `hbar-grow` — 大标题先入 → 每行依序 width 0→target(transform-origin:left)+ 末端数字 count-up

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。