# Guizang PPT 风格系统 · 提取库

本目录从本地技能仓库 `ppt-github/guizang-social-card-skill` 真实提取其**借用的 Guizang PPT 视觉原则**,整理为 leo-ppt-generator 可参考的 PPT 风格模板。

- **用途差异**:`01_通用母版 / 02_行业内容域 / 03_场景用途结构` 是**自研策展**风格;本目录是**有明确来源、可直接引用规则文本**的风格系统。两者并存,Guizang 可作为「电子墨水杂志 / 瑞士国际」类别的权威版。
- **原作者**:该技能声明「borrows visual principles from the Guizang PPT style system, but must not edit the original PPT skill」——本目录同样只做提取与参考,不改动上游技能源码。

## 两大风格模式

| 权威落点文件 | 模式 | 调色板 | 版式配方 |
|---|---|---|---|
| `../电子墨水杂志风.md`(顶层内置,已补强) | **Editorial Magazine × E-ink**(杂志慢节奏) | 6 套(墨经典 / 青花瓷 / 森林墨 / 牛皮纸 / 沙丘 / 夜墨) | M01–M16 |
| `../01_通用母版/极简排版/瑞士网格风.md`(自研,已补强) | **Swiss International**(工程化量化节奏) | 4 套强调色(IKB 蓝 / 柠檬黄 / 柠檬绿 / 安全橙) | S01–S12 |

> 模式是「视觉姿态」而非内容分类:同一主题可用任一模式,区别在于版式结构与可用构件(ledger / marginalia / pull-quote ↔ matrix / KPI tower / h-bar)。由上风意图(「feature story」vs「release note / system explainer」)选择,不按主题查表。
>
> **说明**:本目录不再单独存放两份模式风格文件——Guizang 权威内容已折叠进上述两个权威落点(替换/补强,不并存)。本文件仅作为来源与配方索引保留。

## 版式配方索引

**Editorial(M01–M16)** 封面 / 素材笔记 / 文章分栏 / 金句主张 / 清单购买 / 证据墙 / 结语 / 高台账 / 氛围论点 / 证据特写 / 旁注随笔 / 章节隔页 / 问题页 / 纵向流水线 / 前后对比 / 图像主导封面。

**Swiss(S01–S12)** 强调封面 / 双信号对比 / 数据层文件卡 / 界面浏览器mock / 陷阱警告 / 流水架构 / 结论台账 / 图像英雄 / KPI 塔 / 横向条形图 / 堆叠台账 / 矩阵+底部大数。

## 画布适配

来源画布为 `3:4`(1080×1440)、`1:1`(1080×1080)、`21:9`(2100×900)。本文档已**按 leo-ppt-generator 的 16:9 全页幻灯片适配**:

- 纵向堆叠版式(M14 纵向流水线、M15 上下前后对比)→ 在 16:9 下转**横向**(左→右)。
- 左右分栏(M03 / M11 / S02 / S04)→ 直接适用,列宽按 16:9 调整。
- 图像主导(M16 / S08)→ 16:9 天然强项,保持「图片是证据」。

## 关键规则(两模式通用,来自 `style-system.md`)

1. 内容形状决定版式:不为漂亮版式先编内容。
2. 强层级:标题 → 钩子 → 证据 → 说明 → 元信息。
3. 图是真证据或氛围,不是装饰。
4. 避免杂乱:无随机 SVG 圆、圆点、斑影、bokeh、装饰贴纸、假图解、装饰渐变。
5. 一套视觉内所有页面靠网格、排印、配色、重复元信息保持关联。
6. 每页有一个清晰焦点。

「更大的字更轻」对 Editorial 与 Swiss 都是硬规则。

## 组件模板（`组件模板/`，规则手册，非风格 brief）

> 从 Guizang 系统提取的第二层——**组件/规则模板**，与「风格 brief」正交：管 deck 结构、图文叠放、截图、地图、竖图填充、标题压缩。每个文件保留真实规则与数值，并补 16:9 适配注记。

- `deck结构模板.md` — 压缩阶梯 / 页面角色 / 封面钩子 / 图像主导序列 / 页数参考 / 元信息（`content-planning.md`）
- `图文叠放规则.md` — 选图两测试 / 无遮罩优先 / 取图像色局部 tint / subject map / 裁剪守卫 / 交付清单（`image-overlay.md`）
- `截图处理模板.md` — frame-shot 六参数 / 9 张纹理背景 / device chrome / 安全区裁剪（`screenshot-treatment.md`）
- `地图组件模板.md` — 三模式（Mapbox/OSM/示意 SVG）/ 硬规则 / pin 放置 / 色调 token（`map-component.md`）
- `竖图填充规则.md` — 竖向五区 / 欠填气味 / 最小占用率 78% / 页面节奏（`portrait-fill.md`）
- `标题压缩模板.md` — 五步提取 / 1:1 句式 / 反模式 / 字号 / 跨平台配对（`title-shortener.md`）

## 来源文件

`style-system.md` · `theme-presets.md` · `layout-recipes.md` · `components.md` · `background-systems.md` · `category-cookbook.md` · `platform-specs.md` · `content-planning.md` · `image-overlay.md` · `screenshot-treatment.md` · `map-component.md` · `portrait-fill.md` · `title-shortener.md`

> 种子 HTML 模板（`assets/template-editorial-card.html` 838 行 / `template-swiss-card.html` 943 行）与 `live-photo-production.md`、`production-workflow.md`、`qa-checklist.md` 属实现与流程层，未转写进本库；需要时直接读上游 `assets/`。

## 深度内化（跨风格护栏）

Guizang 最强的不是 28 个配方，而是那些**跨风格的元原则**。已把它们提炼、泛化到 16:9 PPT 语境，形成一条**上位约束**：

→ [`../00_索引/通用设计规范.md`](../00_索引/通用设计规范.md)

内容涵盖：排印铁律（越大越轻 / 先缩文案再缩字号 / 语义断行 / 混排克制）、版式铁律（内容定版式 / 一页一焦点 / 不欠填 78% / 页面节奏）、配色铁律（单一强调色 / 60-30-10 / 强调是信号）、图像铁律（图是证据 / 选图两测试 / 主体避让 / 局部取图像色 tint）、身份自检 6 问、反模式/坏味道清单。**所有风格 brief 之上先过这套护栏**，再走各风格自身约束。
