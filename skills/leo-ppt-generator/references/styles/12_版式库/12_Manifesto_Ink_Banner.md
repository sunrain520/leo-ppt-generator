# 版式：P12 · Manifesto + Ink Banner · 宣言 + 通栏 ink 条

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 阶段性结论、章节封底、口号 + 视觉强收束。

**适用内容类型:** **章节性收束 / 阶段性宣言**(用于 deck 中段而非结尾,P9 是 deck 终结)。承载「主张 + 简短说明 + ink 通栏宣言」三段结构,无数据。

**骨架:** 上半屏左侧 t-cat + 大字 4 行宣言 + 右侧短段说明 / 下半屏 ink 通栏(无左右下边距)+ 反白短句 + lucide 图标矩阵。

**关键类:** `.manifesto-top` `.ink-banner-full`(`margin:0 -5vw -4.4vh` 取消父级 padding)

**动效 recipe:** `manifesto` — 大字三段错峰升起 → 底 ink 条横向 scaleX 0→1 铺开 → 反白文字 fade in

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。