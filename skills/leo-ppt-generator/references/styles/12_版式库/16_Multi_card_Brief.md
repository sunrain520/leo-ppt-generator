# 版式：P16 · Multi-card Brief · 微卡小报

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 6 项小卡并列(快讯、tip 集合、特性概览)。

**适用内容类型:** **6 项轻量短讯 / tip / 注脚**(数量 = 6,每项主文短 + 小字注脚)。比 P4 内容更碎,适合快讯类。**只允许一张 accent 蓝突出**(单焦点法则)。

**骨架:** 顶部大标题(留 9vh)/ 下方 3×2 微卡(每卡:左上主文 + 右下小字 + 中间留空)。

**关键类:** `.brief-grid` `.brief-card`(`.card-fill` 灰底)`.brief-card.is-accent`(单一蓝底强调)

**动效 recipe:** `field-notes` — 6 卡按 z 形顺序点亮(L→R, T→B,90ms 错开)

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。