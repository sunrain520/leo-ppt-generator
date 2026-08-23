# 版式：P8 · Duo Compare · 双轨对照

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** Before/After、A vs B、旧/新对比。

**适用内容类型:** **二元对照**(必须正好 2 项)。两侧结构同质(t-cat 标签 + 大字标题 + 段落 / 列表说明)。典型如:旧/新工作流、传统/AI、客户视角/团队视角。

**骨架:** 左右两半屏中间一根纵向 1px 长线分隔 / 各自顶部 t-cat + 大字标题 + 下方说明。

**关键类:** `.duo-compare` `.duo-half` `.vrule`(scaleY 拉开)

**动效 recipe:** `duo-mirror` — 中线 vrule 先 scaleY 0→1 → 左右各自标题、文字镜像入场

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。