# 版式：P14 · Loop Diagram · 闭环流程图

**分类:** 12_版式库（guizang-ppt-skill Swiss 版式）

**用途:** 自学闭环、自动化流程(3-5 步循环)。

**适用内容类型:** **循环 / 闭环流程**(终点回到起点,3-5 步)。如自学循环、CI/CD、反馈闭环、agent loop。**线性流程禁用**(那是 P11)。

**骨架:** 左 4 行编号步骤(顶对齐) / 右侧 SVG 同心圆环 / 中央巨字 LOOP / 节点统一灰底直角方块(不用圆点交替色)。

**关键类:** `.loop-diagram` `.loop-steps` `.loop-svg`

**动效 recipe:** `loop-form` — 左侧步骤纵向序列 → 右 SVG 圆环 stroke-dashoffset 描线 → 节点序列点亮

> 版式是「页级可粘贴结构」，约束内容类型匹配（见 `选版式P0原则.md`）。动效 recipe 与图形语义耦合，不是统一 fade-up。