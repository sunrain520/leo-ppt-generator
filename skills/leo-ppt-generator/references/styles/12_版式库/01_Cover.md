# 版式：P1 · Cover · 封面页

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 整套 deck 起手 / 主题宣言。

**适用内容类型:** 封面 / 章节首页 / 主题宣言。**纯文字结构**(主标题 + 副标 + 元信息),不承载数据。

**骨架:** IKB 满屏 + ASCII 呼吸场 / 主标题反白 weight 200，强调字用斜体（非 accent 色）/ 底部副标 + 元信息带。

**关键类:** `.slide.accent` `.ascii-bg` + `min(11.6vw,19vh)` 双约束大字

**动效 recipe:** `hero` — ASCII 字符场持续呼吸,文字 fade-up 序列入场

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。