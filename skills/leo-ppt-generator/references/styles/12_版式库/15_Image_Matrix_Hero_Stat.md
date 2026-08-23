# 版式：P15 · Image Matrix + Hero Stat · 矩阵 + 大字底注

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 大量同类项展示(8-12 项 skill / 团队成员 / 案例图标),底部一个总数据收束。

**适用内容类型:** **8-12 项同类型小项 + 一个汇总指标**。每项只承载短标题(无展开),底部巨数为「汇总值」(项目总数 / 总流量 / 总用户)。**项数过少改用 P4(6 项)**。

**骨架:** 顶部标题(留 9vh 间距)/ 中段 4×3 矩阵卡(每卡 12vh 固定高度)/ 底部巨数 + 标签(margin-top:auto 推到底)。

**关键类:** `.matrix-fill`(grid-template-columns:repeat(4,1fr))`.matrix-cell`(`.card-fill` 灰底,**禁止描边**)`.hero-stat-bottom`

**动效 recipe:** `matrix-fill` — 12 格随机棋盘渐显(每格 random delay)→ 底部巨数 count-up

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。