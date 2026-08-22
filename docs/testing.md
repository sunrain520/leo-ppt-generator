# leo-ppt-generator 测试方案

## 目标与证据分层

测试采用“合同 → 领域能力 → 跨阶段 → 发布 → 现场”五层结构，避免把离线 fixture
外推为真实模型、视觉或桌面兼容证据。

| 层级 | 主要风险 | 权威证据 | 声明上限 |
| --- | --- | --- | --- |
| 合同单测 | route、schema、revision、idempotency、配置与 hybrid 前置条件 | `tests/unit/` | 证明确定性合同，不证明外部工具 |
| 边界测试 | 并发、crash、原子写、vendor 状态和 fail-closed | `tests/boundary/` | 证明受控故障注入与本机文件系统行为 |
| 集成/e2e | CLI → adapter → PPTX、四 route、失败保留 | `tests/integration/`、`tests/e2e/` | 证明离线 fixture 的跨层机制 |
| 发布验证 | upstream pin、wheel inventory、双平台 installer、runtime ensure/doctor/rollback | `sync_upstreams.py`、构建与安装 receipt | 只证明实际执行对应门禁的平台发布包 |
| 现场验证 | provider、OCR、Office viewer、PowerPoint、人工视觉 | 分项现场 receipt | 每项只证明当次模型、网络、凭据、fixture 和客户端 |

## 场景设计

- 四条 route 各覆盖 happy path、worker 不可用、未知 route/step 和失败保留。
- `generate`、`direct-editable`、`upgrade-full`、`upgrade-selected` 分别与
  `fixture`、`openai` capability contract 组合，共 8 个离线 e2e 场景；其中
  `openai` 只验证 provider contract，不伪造真实网络调用。
- hybrid 覆盖空 deck、页序、尺寸、validation、选择范围、source hash 与
  partial 精确确认 7 类前置条件。
- durable state 覆盖 8 个 checkpoint、并发 expected revision、vendor 同文件
  record、6 个 idempotency replay/conflict 场景。
- runtime 覆盖重复 ensure、并发 ensure、半安装 quarantine、失败升级不切换、
  rollback 与活动 run 禁删。
- installer 覆盖 macOS Bash 与 Windows PowerShell 的全新安装、四 route doctor、同名拒绝、
  升级备份、失败不替换、通用 Agent 发现目录，以及缓存/`third_party` 拒绝或排除。
- Skill 合同覆盖 25 个正反向用户意图 case、渐进 reference 与旧入口禁用；静态 eval
  不能替代真实模型行为 eval。

## 墨菲定律故障驱动模型

本项目把墨菲定律转化为可验证规则：任何依赖“正常网络、单进程、完整 JSON、正确
平台、充足磁盘、可信压缩包、子进程 exit 0、用户不会重复执行”的假设，都必须至少
满足以下一项：自动故障注入、真实平台门禁、明确 fail-closed，或带 owner 的现场验收。
这不是穷举所有宇宙状态；使用 FMEA 的损失优先级，先覆盖会导致旧版本丢失、错误激活、
半安装、误报就绪、不可恢复删除或跨平台失真的故障。

### 发布故障矩阵

| 故障域 | 最坏故障 | 注入或验证方式 | 必须保持的不变量 | 当前证据 |
| --- | --- | --- | --- | --- |
| 参数解析 | 缺值、未知选项、危险 ref | 非法 `--ref/-Ref` 与错误组合 | 在下载和目标写入前退出 | 自动合同测试 |
| 平台选择 | macOS Intel/Linux/Windows ARM 被误装 | fake `uname`、Windows architecture 环境 | 明确拒绝，不创建目标 | 自动故障注入 |
| Python | 非 3.12 或 32 位解释器 | installer 版本/位数 probe | runtime 前退出，旧 Skill 不变 | 代码合同；真机矩阵需补 |
| 路径 | 空格、Unicode、不同发现目录 | 临时特殊字符 source/target | 路径不截断、不装错目录 | Bash/PowerShell 自动测试 |
| 远程下载 | 网络失败、错误 ref、代理错误页 | 本地确定性 tar/zip 服务 | 非零退出，无目标和 staging | 自动集成测试 |
| 公开 origin | 仓库私有、未创建或 tag/脚本路径 404 | 匿名网络从全新 HOME 访问 README 三个入口 | 发布前全部 URL 为 2xx，并从固定 tag 完成真实安装 | 当前 2026-08-22 检查为 404，发布阻断 |
| 压缩包 | 截断、非 archive、目录结构漂移 | 损坏 tar 与缺失 bundle 路径 | 解压失败即停止 | 自动故障注入 |
| 内容边界 | `third_party`、符号链接、缓存、构建垃圾 | 恶意 fixture、开发目录与真实 runtime 安装 | vendor 目录拒绝；安装前后均无生成物，runtime source 不被 pip 修改 | 自动安全与集成测试 |
| 并发 | 两个安装器同时看到目标不存在 | ensure barrier 后双进程竞争 | 恰好一个激活；不得嵌套或暗中备份 | Bash + PowerShell 竞态测试 |
| 陈旧锁 | 上次进程被 SIGKILL | 预建 Bash lock | fail closed，给出显式清理路径 | 自动测试；真实 SIGKILL 为手工演练 |
| staging | ensure/doctor 中途失败 | 稳定非零 reason 注入 | 无目标、无 staging、锁释放 | 双平台自动测试 |
| runtime receipt | exit 0 但 receipt 缺字段 | 假成功 JSON | 不得把 exit 0 当作 ready | 双平台反假绿测试 |
| route receipt | exit 0 但 `status=blocked` | false-green doctor | 四 route 任一未 ready 均不激活 | 双平台反假绿测试 |
| 升级 | 新版本验证失败 | 指定 route 失败 | 旧 Skill 字节保持，零备份残留 | 双平台自动测试 |
| 激活 | 旧目录已备份后 `mv` 失败 | Bash `mv` fault injection | 自动恢复旧目录 | 自动故障注入 |
| 备份 | 成功升级后无法追溯旧版 | 正常 upgrade | 恰好一个时间戳备份 | 双平台自动测试 |
| runtime 安装 | pip 失败、timeout、CLI 不可执行 | broken bundle、权限破坏、half install | 候选 quarantine；current 不切换 | runtime integration 测试 |
| identity | lock 缺失或内容漂移 | 删除/修改 platform lock | 拒绝或生成新 identity | 自动测试 |
| operation | receipt 损坏或同 ID 异请求 | 损坏 JSON/fingerprint conflict | 稳定 `operation_conflict`，不覆盖 receipt | 自动故障注入 |
| 删除保护 | active run、损坏 run/current | active/corrupt JSON | 无法证明未引用时禁止删除 | 自动 fail-closed 测试 |
| 状态原子性 | 写入各 checkpoint 崩溃 | crash checkpoint fixture | 旧 JSON 可读，不误报完成 | boundary 测试 |
| wheel | cache、旧入口、Skill 文件混入 | clean-copy build 与 inventory | wheel 只含 runtime | release 测试 |
| 双渠道发布 | Plugin/standalone 内容漂移、版本或 cachebuster 陈旧 | 可复现构建、tree hash 与 manifest drift 注入 | 两个归档只含同一 canonical Skill tree | release 测试 |
| 凭据生命周期 | 非 TTY、覆盖误操作、Keychain/DPAPI/ACL/blob 失败 | fake OS store、子进程协议、平台只读 smoke | secret 不进入参数、状态、receipt、run 或日志 | 自动测试；Windows 真机待跑 |
| Windows 依赖 | 某个 pin 没有 x64 wheel | `uv --python-platform` + only-binary | 全部 pinned wheel 可解析 | 跨平台解析；Windows 真机待跑 |
| 四 route | 安装成功但真实 CLI 链路断裂 | 绝对 console script e2e | 四 route 完成且 replay 稳定 | macOS 黑盒；Windows 真机待跑 |
| 外部现场 | provider/OCR/viewer/PowerPoint/人工失败 | hash-bound receipt | 未运行项保持 `not-run` | 现场门禁，不由 fixture 补偿 |

### 统一判定与反假绿

- 成功不能只看进程存活或 exit code；安装必须解析 `ensure` receipt，并要求四个 doctor
  receipt 均为 `status=ready`、`reason_code=ready`。
- 失败路径同时断言结果与副作用：目标是否保持、备份数量、staging/锁/quarantine、
  current identity、reason code 和是否出现嵌套 Skill。
- 并发测试必须至少重复 10 轮；任何“双成功”、目标嵌套、旧版消失或锁残留都算失败。
- 损坏元数据不能被当成“不存在引用”；删除和清理必须 fail closed。
- runtime 安装必须从隔离副本构建；`ensure` 前后 source identity 不变，且 Skill 内不得
  新增 `build`、`dist` 或 `*.egg-info`。
- fake/本地 HTTP/跨平台解析只证明受控机制；Windows NTFS、真实 GitHub、真实 provider
  和 PowerPoint 必须由对应平台或现场 receipt 独立关闭。

### 重复冷安装体验门

安装体验不能由单次成功外推。每个发布候选至少执行 20 次 standalone 冷安装；Plugin
渠道也使用 20 个互相隔离的 `HOME`、`CODEX_HOME`、`LEO_PPT_HOME` 和目标目录。每次
必须从未初始化状态运行公开入口，解析 runtime receipt，依次关闭四 route doctor，并
确认最终目标存在。不得共享 runtime cache 来缩短冷安装，不得把失败样本从统计中删除。

结构化结果至少记录 `sample_size`、`successes`、`success_rate`、`median_seconds`、
`p95_seconds`、`max_seconds` 和逐次 exit/status。门禁为成功率不低于 95%、中位耗时不
超过 10 分钟；P95 和最大值用于识别长尾，不由中位数补偿。任一失败都保留对应 HOME、
installer 输出和 reason code 直到 root cause 关闭。fixture 重复测试与上述真实安装样本
分开报告，不能合并计数。

2026-08-22 当前 macOS arm64 的两渠道本地样本均为 20/20 成功：standalone 成功率
100%，中位 60.343 秒、P95 108.705 秒、最大 118.788 秒；Codex Plugin 本地 marketplace
安装成功率 100%，中位 56.198 秒、P95 70.310 秒、最大 103.159 秒。每次均使用独立
HOME、配置目录、runtime home、缓存和目标目录，并关闭四 route doctor。结构化逐次结果见
`.spec-first/workflows/spec-work/leo-ppt-generator/install-repeat-20260822/standalone-summary.json`
与 `.spec-first/workflows/spec-work/leo-ppt-generator/install-repeat-20260822/plugin-summary.json`。
该结果不包含远程 GitHub 或 Windows 样本。

## 标准命令

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/leo-ppt-generator/runtime/src \
  uv run --with pytest --with pytest-cov --with pillow --with python-pptx \
  --with filelock --with pyyaml --with pymupdf --with numpy --with openai \
  --with requests --with build --with jsonschema \
  python -m pytest tests -q --cov=leo_ppt_generator \
  --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=80

PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml \
  python skills/leo-ppt-generator/scripts/sync_upstreams.py --check

PYTHONDONTWRITEBYTECODE=1 python /Users/kuang/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/leo-ppt-generator

PYTHONDONTWRITEBYTECODE=1 uv run --with build python -m build \
  --outdir <temporary-directory> skills/leo-ppt-generator/runtime

uv pip install --dry-run --python-version 3.12 \
  --python-platform x86_64-pc-windows-msvc --only-binary :all: \
  --target <temporary-directory> \
  -r skills/leo-ppt-generator/runtime/constraints/py312-win32-amd64.txt

PYTHONDONTWRITEBYTECODE=1 uv run --with pytest \
  pytest -q tests/release/test_installer.py tests/integration/test_runtime_manager.py
```

最终发布验证还必须按 `upstream-capabilities.yaml` 的顺序独立执行全部 60 个
`proof_case`，不能用一次聚合 pytest 代替逐项结果；随后在固定 commit 的 clean export
运行 U0 7 项隔离测试与 editable 82 项原生回归。Wheel 必须从排除缓存和构建垃圾的
clean copy 构建，再分别验证两种 Skill 发现布局、四 route doctor 和四 route 离线 e2e。
`tests/release/test_installed_routes.py` 会从临时 clean copy 构建 wheel，以绝对 wheel
路径安装到不继承 system site packages 的临时 venv，并且只通过绝对 `leo-ppt` 运行四条 route；该测试不能用源码
目录安装、direct import 或手工 domain state 替代。

Windows 发布必须在 Windows 10/11 x64 runner 使用 Python 3.12 执行
`.\install.ps1 -Source <clean-skill> -Target <temporary-target>`，再从安装结果的绝对
`leo-ppt.exe` 运行 `tests/release/test_installed_routes.py` 的四 route 等价场景。macOS
上的 `pwsh` 测试可证明 PowerShell 控制流，`uv --python-platform` 可证明 Windows wheel
可解析，但二者都不能替代 Windows 真机进程、文件锁、路径和原子替换证据。

## 退出门

- 所有 required 自动检查 exit 0；既有失败与本轮新增失败分开记录。
- wheel 不含 `__pycache__`、`.pyc`、旧 Skill 或旧 CLI 入口。
- macOS 与 Windows release 各自的 clean install、四 route doctor、绝对 CLI e2e 必须
  独立通过；一个平台的结果不能补偿另一个平台未运行。
- 公开仓库、Skill 路径、`install.sh` 和 `install.ps1` 必须对匿名用户可访问；固定
  release tag 发布后从全新 HOME 按 README 原命令安装。当前工作树或本地 HTTP 成功
  不能补偿公开 origin 404。
- 各计划指定模块覆盖率达到 adapter ≥80%、run index ≥90%、hybrid ≥85%。
- 真实 provider、在线 OCR、Office viewer、PowerPoint 桌面与人工视觉没有 receipt
  时必须逐项记为 `not-run`，不得由离线 fixture 替代。
- provider provenance 必须匹配 canonical 页面产物 hash；独立 visual receipt 必须逐页
  校验真实 render 文件 hash；manual acceptance 必须绑定当前最终 PPTX hash、客户端
  版本和逐页 accepted，三者不可互相补偿。
- P0/P1 故障域不得只有文档声明；必须有当前自动结果、平台 receipt，或明确阻断 release
  的 `not-run`。测试失败后必须改变实现、fixture 或环境再重跑，不允许原样重试碰运气。

当期实际结果与不可替代的现场缺口见
[2026-08-22 发布候选验证报告](verification-report-2026-08-22.md)。
