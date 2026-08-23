# 版式：P9 · Closing Manifesto · 收束宣言

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 整套 deck 收尾页。

**适用内容类型:** **deck 收尾**(每个 deck 只有一页)。固定结构:左侧宣言短句 + 右侧 3 条 takeaway(编号 + 标题 + 一行说明)。**不能在中间页使用**(那会与 P1 封面重复)。

**骨架:** 

**关键类:** `.slide.split` `.half.b-accent` `.ascii-bg`(IIFE 自动启动)

**动效 recipe:** `split-statement` — 左 ink/IKB 标题字符序列升起 → 右白半 takeaway 三条尾随

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。