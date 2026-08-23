# 版式：P3 · Statement · 极简陈述

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 中心论点、章节起始、口号。一页只放一句话 + 简单装饰。

**适用内容类型:** **纯定性论断 / 口号 / 章节切换**。一句话压缩到 8-12 词,**不承载任何数据或列表**。如果需要数据支撑,改用 P18 Why Now;如果是封面,用 P1。

**骨架:** 左 1/3 空白 + 中段巨字陈述(8-10vw, weight 200) + 右下小字注脚 + 底部 hairline。

**关键类:** `.h-statement`(9.6vw,letter-spacing:-.05em) `.stmt-anchor`

**动效 recipe:** `statement-rise` — 大字按词序错峰升起(每词延迟 180ms)+ 注脚 fade in

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。