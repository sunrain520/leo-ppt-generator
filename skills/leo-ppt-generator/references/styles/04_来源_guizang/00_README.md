# Guizang PPT 风格系统 · 提取库

本目录从本地技能仓库 `ppt-github/guizang-social-card-skill` 真实提取其**借用的 Guizang PPT 视觉原则**,整理为 leo-ppt-generator 可参考的 PPT 风格模板。

- **用途差异**:`01_通用母版 / 02_行业内容域 / 03_场景用途结构` 是**自研策展**风格;本目录是**有明确来源、可直接引用规则文本**的风格系统。两者并存,Guizang 可作为「电子墨水杂志 / 瑞士国际」类别的权威版。
- **原作者**:该技能声明「borrows visual principles from the Guizang PPT style system, but must not edit the original PPT skill」——本目录同样只做提取与参考,不改动上游技能源码。

## 两大风格模式

| 模式文件 | 模式 | 调色板 | 版式配方 |
|---|---|---|---|
| `电子墨水杂志风_Guizang.md` | **Editorial Magazine × E-ink**(杂志慢节奏) | 6 套(墨经典 / 青花瓷 / 森林墨 / 牛皮纸 / 沙丘 / 夜墨) | M01–M16 |
| `瑞士国际风_Guizang.md` | **Swiss International**(工程化量化节奏) | 4 套强调色(IKB 蓝 / 柠檬黄 / 柠檬绿 / 安全橙) | S01–S12 |

> 模式是「视觉姿态」而非内容分类:同一主题可用任一模式,区别在于版式结构与可用构件(ledger / marginalia / pull-quote ↔ matrix / KPI tower / h-bar)。由上风意图(「feature story」vs「release note / system explainer」)选择,不按主题查表。

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

## 来源文件

`style-system.md` · `theme-presets.md` · `layout-recipes.md` · `components.md` · `background-systems.md` · `category-cookbook.md` · `platform-specs.md`
