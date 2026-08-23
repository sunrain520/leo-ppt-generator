# 结构化图表注入（ECharts SSR）接入设计

> 解决图片式 PPT 数据页的核心痛点：**AI 生成图表会失真**（编造百分比、单位错、排序
> 乱、图例漏）。方案是用 **ECharts SSR 在服务端生成精确图表**，再作为 `required
> asset` 注入 slide job，让 AI 页面**保留图表真值而非重画**。

## 一、问题

leo-ppt 是图片式 PPT：每页是一张 16:9 AI 生成图。数据页（KPI、占比、排名、趋势）
靠 AI 按 prompt 画图表时，会出现：

- 编造数字（「智能补全 96%」这种无可比百分比的概念列表被硬塞成 H-Bar）；
- 单位/标签/图例/排序与 approved 不一致；
- 数据真值丢失（AI 重画近似图，非原始数据）。

`slide-worker.md` 已要求「charts preserve approved values」但 AI 生成图无法保证。

## 二、方案：结构化图表 + required asset 注入

对**需要精确数据**的页面，分两步：

1. **服务端生成精确图表**：用 ECharts SSR（或 Vega headless）以结构化数据渲染出
   精确的图表 PNG/SVG。
2. **作为 required asset 注入**：把图表作为 `strict input asset` 交给 slide job，
   AI 生成页面时**保留图表真值**（不重画、不改数据），只负责排版与文字。

## 三、ECharts SSR 技术链路（源码已确认）

子代理深读 `ppt-github/echarts` 确认：

- `src/core/echarts.ts:555-580`：`if (opts.ssr) zrender.registerSSRDataGetter(...)`；
- `src/core/echarts.ts:940-949`：`renderToSVGString({useViewBox:true})` 返回 SVG 字符串；
- `test/node/ssr.js` 有官方 Node SSR 用例；`build:ssr` 证明 SSR 是正式链路。

链路：

```
结构化数据 (JSON)
  → ECharts init(null, {renderer:'svg', ssr:true, width, height})
  → setOption({...spec, color: <deck 色板>})
  → chart.renderToSVGString({useViewBox:true})      # 纯 Node，无 DOM
  → resvg-js 或 sharp 栅格化为 PNG（16:9 槽位尺寸）
  → 作为 required asset 注入 slide job
```

`chart.setOption` 的 `color` 数组映射自 `10_品牌身份` 的 `colors`（或视觉风格默认
色板），保证图表与 deck 配色一致。

## 四、接入点（leo-ppt 现有机制）

leo-ppt 已有 `required asset` 机制（`prepare_slide_prompts.py` 的 `required_images` /
`slide-worker.md` 的 `strict input asset; preserve labels/data/arrows/content`）。
结构化图表注入就是：

1. 数据页在 `deck_spec` 里标记 `chart: {type, data}`（结构化数据，非自然语言）。
2. 生成图表 PNG 到 `origin_image/`。
3. `prepare_slide_prompts.py` 把图表 PNG 列为 `required_images`（`strict input asset`）。
4. slide worker 生成页面时，图表以「证据块」出现，AI 不重画、只保留。

## 五、落地方式（Python 底座 + Node sidecar）

leo-ppt 是 Python 运行时。ECharts SSR 是 Node 生态，需一个轻量 sidecar：

- **方案 A（sidecar 脚本）**：一个 `chart-render.mjs` 脚本，读 JSON 数据 → ECharts
  SSR → 输出 PNG。Python 通过 `subprocess` 或 bridge 调用。
- **方案 B（Vega，纯 spec 更贴合 LLM）**：若希望图表由 LLM 直接产出声明式 JSON
  spec，用 Vega（`toSVG()` 纯 Node，`render-headless` 原生）。学习曲线陡，需封主题。

推荐先 **方案 A（ECharts SSR）**：开箱即用、主题成熟、图种全（30+）。

## 六、与现有风格体系的关系

- **不新增风格**，补「数据页图表真值」能力。
- 图表配色复用 `08_图片渲染` 的 `data-journalism` / `digital-dashboard` 画风 + 
  `10_品牌身份` 色板；图表类型复用 `07_信息图类型`（H-Bar/漏斗/矩阵…）与
  `11_图表语法`（mermaid）。
- 本设计只在「数据页需要精确图表」时启用；纯定性页仍走 AI 整页生成。

## 七、落地清单（待执行，非本轮完成）

- [ ] 验证 ECharts SSR 在 Node 环境可跑（`init(null,{ssr:true})` + `renderToSVGString`）。
- [ ] 写 `chart-render.mjs` sidecar（JSON → PNG）。
- [ ] `prepare_slide_prompts.py` 支持 `chart` 字段 → 生成图表 PNG → 列为 required asset。
- [ ] 图表色板映射 `10_品牌身份` colors。
- [ ] 端到端验证：一个数据页用结构化图表生成，确认图表真值保留。
