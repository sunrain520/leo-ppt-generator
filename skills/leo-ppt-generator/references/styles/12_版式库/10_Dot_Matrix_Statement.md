# 版式：P10 · Dot Matrix Statement · 点阵宣言

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 第二张陈述页 / 章节切换 / 视觉透气页。

**适用内容类型:** **口号 / 隐喻 / 章节切换**(同 P3,但加几何点阵装饰)。用于一个 deck 内**避免连续两页都是 P3**;通常用作"概念定义"前的视觉调味页。

**骨架:** 中段 7vw 巨字三行宣言 / 右上角 36vw 圆点矩阵 + 左下角描边圆环矩阵。

**关键类:** `.dot-mat`(SVG mask 实心点)`.ring-mat`(描边圆)`.cross-mat`(× 网格)

**动效 recipe:** `matrix-statement` — 文字逐行入 → 点阵 mask-position 从左推到右

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。