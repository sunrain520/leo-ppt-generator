# U0 可内嵌性与发行边界报告

decision: go

## 结论

两个 owner 指定的上游可以在一个 Python 3.12 受管 runtime 中以
`compose / thin-glue` 方式共存。clean export、依赖解析、同进程 import、
wheel/editable 资源定位、两个最小 fixture、可信 Office/PPTX 无网络处理、
离线 OCR 和无 worker 边界均已得到可复跑证据。

U1–U5 可以开始，但必须保留两个领域状态 owner，并在 U2 通过最小 patch
关闭本报告列出的持久化、缺页拒绝和 Office preflight 缺口。U0 不证明四条
产品 route、真实图片 provider、在线 OCR、PowerPoint 桌面打开或人工视觉等价。

## 证据身份

- 目标仓库：`https://github.com/sunrain520/leo-ppt-generator.git`
- 目标基线 HEAD：`2230fa83bf358a64386d21b97765c5421d4537df`
- 执行日期：2026-08-20 至 2026-08-21
- 平台：macOS 26.5.1 arm64
- Python：3.12.13
- 上游身份权威：用户在当前会话明确给出的本地仓库路径、各仓库的 Git
  object database、`origin` 配置、commit/tree/blob 与 clean `git archive`
- 远端刷新限制：执行时 `github.com` DNS 解析失败，因此未重新取得
  `ls-remote` receipt；本结论不声称远端在本次执行时可访问。固定对象本身已在
  owner 提供的本地仓库中逐项复核。

完整机器可读身份与 import set 见
`skills/leo-ppt-generator/upstreams.yaml`。

| 上游 | repository | commit | repository tree | import tree | license |
| --- | --- | --- | --- | --- | --- |
| codex-ppt | `https://github.com/ningzimu/codex-ppt-skill.git` | `f2ed80372f65bb05fe62dd07979b239a17ac065d` | `551cb696b09ead91df2ee42ce353397f00753c33` | `a7ecf0863b03356c447471a9678973ae26f01078` | MIT，blob `f769fc5582d3f8ee0f9eb4da5fbf95ac85834c17` |
| image-to-editable-ppt | `https://github.com/ningzimu/image-to-editable-ppt-skill.git` | `fb869763127fd31ba7288d905671ffc4ea542f60` | `7723bbb98311e938eb1fd53419f955eeae1eb933` | `5dafb6e837a82fff64a1c58efaf43792e53751b7` | MIT，blob `f769fc5582d3f8ee0f9eb4da5fbf95ac85834c17` |

clean export 通过 `git archive <commit> <import-root> LICENSE` 生成，而不是从
两个 dirty/unknown 工作树复制。归档 SHA-256：

- codex-ppt：`e96d8134d616e8f19570f0b645a67c825628ae85122e016c99b5826ce78708c6`
- image-to-editable-ppt：`f15682824f0fdaac22734be7a2d2399fd31b50a6db257b52eacfb92d7a279823`

## 量化 Gate

| 指标 | 标准 | 实测 | 结论 |
| --- | --- | --- | --- |
| Vendor 代码变化率 | `< 5%` | `0 / 14,894` 导入文件总行；spike 从 clean archive 直接打包，无源码 patch | pass |
| Adapter 代码量 | `< 500` 行/adapter | wheel spike 的 `PageArtifact + CapabilityAdapter` 合计 48 行 | pass |
| 无法解决的依赖冲突 | `0` | 两份依赖合并解析为 27 个包；`pip-compile`、`uv pip install`、`uv pip check` 均成功 | pass |
| 上游核心测试 | `>= 95%` | editable 82/82；codex 上游未发布测试目录，U0 聚焦 import/help/assembly 3/3 | pass，按来源分别披露 |
| wheel/editable 资源定位 | `100%` | 两种安装都定位 `slide-worker.md`、`page-worker.md` 并 import 两个入口 | pass |
| 顶层直接 import vendor | `0` | U0 原型只有 adapter 访问 vendor；`PageArtifact` 不含 vendor path | pass |
| 两 adapter 状态隔离 | 互不干扰 | 40+40 次并发领域写入保持独立目录与 domain | pass |
| 核心算法保留 | 输出一致/无改动 | 0 vendor 源码改动；editable 原测试全绿；两个最小输出结构通过 | pass |
| 来源身份 | URL/commit/tree/license/import set 全部可复核 | 两个上游均完整登记并绑定 archive hash | pass |
| Office/OCR 出站 | `0` | `sandbox-exec` deny network 下可信 PPTX 归一化成功；无 token OCR 使用 `builtin-ink` | pass，范围仅限固定可信 fixture |
| 无 worker 多页行为 | 明确 blocked | editable 真实两页 run 返回 `stage=dispatch_pages`；adapter 在 live capability=false 时返回 `blocked/worker_capability_unavailable` | pass |

`pip-compile` 生成的 U0 临时 constraints SHA-256 为
`0ae8810cb4f07af5edd3c2d6e21ce83992f9d185e6ad1f5df8048b594ecade21`。
U1 必须从正式 runtime `pyproject.toml` 重新生成并提交发布 lock；不得把这个
临时 hash 当成最终 runtime identity。

clean wheel 共 85 个 archive entry，包含两份 MIT license、prompt、
reference 和 runtime source，且不包含 `__pycache__` 或 `.pyc`。wheel
SHA-256 为
`65a9c7282230be98c91d43f81197ae9490d598c4b18d9b80817f54deecb41c90`；
它是 U0 临时 spike receipt，不是发布 artifact。

## 实际 Fixture

### image-deck

- 两张 `1600x900` PNG 由固定 clean export 的 `assemble_ppt.py` 组装。
- 输出 PPTX 29,761 bytes，`python-pptx` 重新打开后为 2 页。
- `prepare_slide_prompts.py --help`、`assemble_ppt.py --help` 与 combined
  runtime import 均退出 0。
- 缺页 characterization：只存在 `slide_01.png` 与 `slide_03.png` 时，上游
  当前仍退出 0 并生成 2 页 PPTX。这不是通过行为，已进入 U2 必修 patch。

### editable

- 一张 `1600x900` PNG 经 `prepare → local dispatch → page build → page
  validate → record → finalize` 完成。
- 页面验证：`passed: true`、1 个 editable text shape、0 个 missing part。
- deck 验证：`passed: true`、expected/slides 均为 1。
- clean export 的 82 个 `unittest` 全部通过。
- 两页输入的真实 `run next` 返回 `stage=dispatch_pages` 和两个
  `dispatchable_pages`；runtime 没有自行生成或模拟 worker。

### Office 与 OCR

- 在 `(deny network*)` sandbox 内，无 `PADDLE_OCR_TOKEN` 的单页 prepare
  完成，`text_hints.json.backend=builtin-ink`。
- 同一 sandbox 内，可信的两页图片型 PPTX 完成归一化，
  `input_type=pptx`、`page_count=2`。
- U0 原型 preflight 对 `TargetMode="External"` 返回
  `blocked/untrusted_office_input`。现有 editable 上游本身不拥有这一
  fail-closed 检查，必须由正式 adapter 在进入 Office 解析前补齐。
- 本项不证明任意不可信 Office 安全，也未运行在线 PaddleOCR、旧 `.ppt`
  soffice 转换或真实 PowerPoint viewer。

## 并发、中断与持久化 Characterization

| Owner | 当前事实 | 中断观测 | U1/U2 约束 |
| --- | --- | --- | --- |
| codex slide state | `FileLock` + temp write + file fsync + `os.replace` | replace 前 SIGKILL 保留旧有效 JSON，但遗留 temp；无 parent-directory fsync | 保留状态 schema；补目录 barrier、temp 诊断/清理与 focused crash test |
| editable deck/page state | 直接 `Path.write_text`，无 lock/expected revision/atomic replace | 写入中 SIGKILL 留下截断且无法解析的 JSON | 在当前 owner 内补 lock、temp write、file fsync、atomic replace、directory fsync 和 revision conflict；不得新建第二套状态模型 |

两个领域使用不同目录与文件名，跨领域并发未观察到互相覆盖。该结果不能外推为
同一领域多个 writer 已安全；editable 的同文件并发安全在修复前明确不成立。

## 定性 Gate

- 不需要重写 `manifest`、`page_jobs` 或 `slide_jobs` 状态模型：pass。
- 不需要 adapter 模拟旧 CLI 子命令调度：pass；原型只负责 namespacing、
  resource lookup、稳定 artifact 与 capability fail-closed。
- 两份依赖使用同一 Python major：pass；editable 声明 `>=3.10`，本次只实测
  Python 3.12。
- 未删除或跳过上游关键测试：pass；editable 82/82，codex 没有上游测试目录。
- wheel/editable 都能定位 prompt/reference：pass。

没有触发 U0 no-go 条件。

## 必要 Patch 与聚焦回归

以下 patch 必须先有失败或 characterization fixture，再在正式 vendoring 后
登记到 `patches/` 与 `upstreams.yaml`：

1. codex assembly：预期 slide id 缺失、重复或 job 未 recorded/accepted 时
   fail closed，禁止仅按现存图片成功组装。
2. editable state：保留现有 schema，补原子写、锁、expected revision、
   directory barrier 和 interruption/concurrency regression。
3. codex state：补 parent-directory fsync 与遗留 temp 的 diagnose/cleanup
   证据，不改变 slide job contract。
4. Office preflight：在任何 PPT/PPTX 解析或 soffice 调用前拒绝宏、嵌入对象、
   external relationship 和远程 template；MVP 不提供 override。
5. import/resource：用唯一 package namespace 与 adapter 访问 vendor；正式同步
   必须从 Git tree 导出并排除 `__pycache__`、`.pyc` 和其他生成物。

`skills/leo-ppt-generator/patches/` 在 U0 时为空是有意状态：U0 没有修改
vendor 源码；后续 U2 已在 failing proof 后登记所需 patch 与回归证据。

## 可复跑入口

- `tests/integration/u0_isolation.py`：向
  `U0_CODEX_EXPORT`、`U0_EDITABLE_EXPORT` 注入固定 commit 的 clean export。
- `tests/upstream/core-tests.yaml`：记录 U0 实际核心检查与已知
  characterization，不把清单文本冒充运行证据。
- `skills/leo-ppt-generator/upstreams.yaml`：固定来源、tree、
  import set、license 和回归映射。

U0 的 claim ceiling 仅为“允许开始 U1–U5”。最终交付仍必须重新绑定正式
vendor tree、patch hash、发布 lock、runtime identity 与最终工作树验证。
