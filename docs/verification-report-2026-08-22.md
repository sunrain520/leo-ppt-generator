# 2026-08-22 发布候选验证报告

## 结论

当前工作树的结构、确定性行为、macOS 安装后黑盒、凭据防泄露机制、双渠道发布包和
本机正式安装均已通过。全仓测试为 `329 passed`，覆盖率为 `86.32%`；60 个能力
`proof_case` 已按清单顺序逐项执行，U0 clean export 为 7/7，editable 固定来源原生
回归为 82/82。

最终 verdict 为 `degraded / field acceptance open`，不能声明公开发布 Definition of
Done 已全部关闭。Windows 10/11 x64 真机、真实 OpenAI/AtlasCloud、
在线 PaddleOCR、Microsoft PowerPoint 和人工成品验收没有可替代的现场环境或凭据。
macOS 上的 PowerShell 7.6.2 只证明 PowerShell 控制流，不能代替 Windows 真机。
此外，2026-08-22 匿名访问 GitHub 仓库、Skill 路径与两个安装脚本均返回 404，公开
origin 尚未建立或不可公开访问，外部用户当前不能按远程命令安装。

## Source binding

- Git 基线：`2230fa83bf358a64386d21b97765c5421d4537df`；结果绑定 2026-08-22
  当前未提交工作树，不绑定尚不存在的 commit、tag 或公开 release。
- 平台：macOS 26.5.1、arm64、Python 3.12.13、uv 0.11.19、PowerShell 7.6.2。
- 发布 identity：`0.1.0+d0d0ecc6460a54d8`；canonical Skill tree SHA-256：
  `d0d0ecc6460a54d8a9a71719b38c9fc9789d6f8bf59a932a54e378293bae3812`。
- 固定来源：`codex-ppt` 为 `f2ed80372f65bb05fe62dd07979b239a17ac065d`；
  `image-to-editable-ppt` 为 `fb869763127fd31ba7288d905671ffc4ea542f60`。
- `sync_upstreams.py --check`：`status=passed`，46 个文件无漂移。

## 非补偿门禁

| Gate | 状态 | 已执行证据 | 结论边界 |
| --- | --- | --- | --- |
| G1 Structure | passed | Skill quick validator、Plugin validator、单一 canonical `SKILL.md`、双归档 tree hash 一致、MIT 与许可证清单、`third_party/` 不存在 | 发布包结构可信；不证明安装宿主或现场效果 |
| G2 Deterministic behavior | passed | 全仓 `329 passed`；coverage `86.32%`；journey 9/9；60/60 逐能力 proof；U0 7/7；editable 82/82 | fixture、clean export 与本地机制可信；不外推真实服务 |
| G3 Installed black-box | passed locally on macOS | standalone 与 Codex Plugin 各 20 次独立冷安装均为 20/20；standalone 中位 60.343 秒、Plugin 中位 56.198 秒；均完成 bootstrap、绝对 CLI setup 和四 route doctor，另有当前用户安装与 installed wheel route/replay | macOS 两渠道本地安装入口与重复性可信；匿名 GitHub 仓库、Skill 路径和两个安装脚本均返回 404，远程安装未通过 |
| G4 Platform | partial | macOS arm64 真机通过；PowerShell 7.6.2 控制流通过；Windows x64 only-binary 依赖可解析 | Windows 10/11 x64 真机仍为 `not-run/missing_environment` |
| G5 Credential security | partial | 非 TTY 拒绝、环境引用撤销/恢复、冻结合同；macOS Keychain 真实隐藏 TTY add/status/backend contract/remove 与删除后 item 缺失检查通过；DPAPI/ACL/blob 确定性测试和 artifact secret scan 通过 | macOS Keychain 生命周期通过；Windows DPAPI 真机与真实有效密钥调用未运行 |
| G6 Host integration | passed on current Codex | Codex 0.149.0 分别启动两个全新 ephemeral、read-only 会话；在不含项目级 Skill 的中性目录中，显式 `$leo-ppt-generator` 与隐式“文章生成高质量 PPTX”均选择 `/Users/kuang/.codex/skills/leo-ppt-generator/SKILL.md` | 证明当前 macOS 用户安装后的新会话发现；不外推 Windows 或其他 Codex 版本 |
| G7 Field execution | not-run | 当前会话工具注册表未暴露内置图片生成调用；安装后 setup 以 `host-imagegen=unavailable` 运行并稳定返回 `image_provider_configuration_required`；OpenAI/AtlasCloud 均为 `credential_missing` | 零密钥宿主生成不可执行；未配置 OpenAI、AtlasCloud、PaddleOCR，也没有真实外部 Provider receipt |
| G8 Delivery quality | not-run | LibreOffice 存在，但本轮没有新的真实最终候选 PPTX | Microsoft PowerPoint 不存在；render hash、逐页人工验收与成品接受未运行 |

后层状态不补偿前层缺口。G4 尚未关闭，因此本报告不批准扩大 Windows 可用性声明；
G7 与 G8 未关闭，因此不声明真实 Provider 成功率、视觉质量或最终
PPT 高质量交付已现场验证。

## 当期执行结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| U8 public-entry journeys | 9/9 passed，约 56 秒 | 真实 bundle bootstrap；zero-key setup；unknown 反假绿；双 Provider；mask/OCR 延迟披露；空格/中文路径；凭据撤销/恢复与泄露边界 |
| 全仓 pytest + coverage | 329 passed，5 warnings，181.59 秒；86.32% | coverage 门槛 80%；warning 来自 PyMuPDF/SWIG deprecation，不是本轮失败 |
| Ruff | 受管自有 runtime 源码 27 文件通过 | 全范围 `runtime/src + tests` 仍报告 388 个既有 vendor/测试风格项；本轮没有把这一非功能性遗留问题误报为全量 lint 通过 |
| 60 个 capability proof | 60/60 passed | 严格按 `upstream-capabilities.yaml` 顺序为每个能力单独启动 pytest；对应 42 个唯一 proof case |
| 固定 commit clean export | U0 7/7；editable 82/82 | 不读取两套来源仓库的 dirty 工作树作为测试源 |
| Release build/validate | passed | standalone 与 Plugin 解包后 tree hash 相同；release manifest、bootstrap lock、license 与 archive SHA 完整 |
| Windows dependency resolve | passed | `uv pip install --dry-run --python-version 3.12 --python-platform x86_64-pc-windows-msvc --only-binary :all:` 可解析 26 个包；不是 Windows 进程证据 |
| macOS isolated standalone | passed | `install.sh --source`、bootstrap、zero-key setup、四 route doctor |
| macOS standalone 20 次冷安装 | 20/20 passed | 独立 HOME、`LEO_PPT_HOME`、target；成功率 100%；中位 60.343 秒，P95 108.705 秒，最大 118.788 秒；未共享 runtime home |
| macOS Codex Plugin 20 次冷安装 | 20/20 passed | 独立 HOME、`CODEX_HOME`、`LEO_PPT_HOME`、cache 与 target；本地 marketplace 安装、缓存 launcher、bootstrap、四 route doctor；成功率 100%；中位 56.198 秒，P95 70.310 秒，最大 103.159 秒 |
| PowerShell compatibility | passed on macOS | `install.ps1 -Source`、bootstrap、zero-key setup、四 route；明确不是 Windows NTFS/DPAPI 真机 |
| Codex Plugin isolated install | passed locally | 首次显式 `CODEX_HOME` 不存在时 CLI fail-closed；创建目录后 marketplace/add 成功；缓存内 launcher 与四 route 通过 |
| Codex 新会话发现 | passed on current Codex | 中性目录中的全新 ephemeral 只读会话分别验证显式与隐式触发，二者均加载用户安装路径；项目目录的首次隐式探测命中项目本地投影，已作为 cwd 污染对照而未计入正式结果 |
| 当前用户正式安装 | passed | `/Users/kuang/.codex/skills/leo-ppt-generator` 原子升级；绝对 CLI 与四 route 通过；只剩一个可发现副本 |
| 当前宿主能力反假绿 | passed | 当前会话没有内置图片生成 callable；setup 使用真实 `unavailable` 事实后返回单一安全配置动作，没有把零密钥路径误报为 ready |
| macOS Keychain 生命周期 | passed | 无效测试凭据经隐藏 TTY 写入；状态与 backend contract 只包含 `keychain:` reference；删除后 `security` 确认 item 不存在，项目与临时 artifact 扫描无原始测试值；未调用外部 Provider |
| 公开安装 URL | blocked | 匿名访问仓库根、Skill 路径、`install.sh`、`install.ps1` 与 releases/latest 均返回 HTTP 404；结构化结果见 `.spec-first/workflows/spec-work/leo-ppt-generator/install-repeat-20260822/public-origin-summary.json` | 未创建公开仓库、仓库不可公开访问或尚未发布；不能声称外部用户可安装 |
| Skill 备份治理 | passed | 两个旧可发现 backup 和本次升级 backup 均保存在 `/Users/kuang/.codex/skills/.leo-ppt-generator-backups/`，未删除 |
| 包污染检查 | passed | canonical Skill 内无 `third_party/`、`.venv`、`__pycache__`、`*.pyc`、`build/`、`dist/` 或 `*.egg-info` |

## 凭据与外部调用状态

本轮环境没有 `OPENAI_API_KEY`、`ATLASCLOUD_API_KEY` 或 `PADDLE_OCR_TOKEN`。未向聊天、
命令参数、项目文件或普通配置写入生产 secret。为验证 macOS Keychain 真实生命周期，
曾通过隐藏 TTY 写入一条明确无效、禁止外部调用的测试凭据；`status` 与 backend contract
只返回 `keychain:` reference。测试结束后已删除该 item，并由 `security` 确认不存在。
原始测试值在项目与临时证据目录扫描为零命中；没有调用外部 Provider。

## 现场验收清单

以下项目需要对应 owner 在可用环境中逐项执行，不能用当前自动化替代：

1. 创建或公开 GitHub 仓库，提交并发布固定 tag；匿名访问仓库、Skill 路径与两个安装
   脚本均为 2xx，再从全新 HOME 按 README 原命令完成 standalone 与 Plugin 安装。
2. Windows 10/11 x64 clean user home：standalone 与 Plugin 各完成安装、升级、bootstrap、
   DPAPI add/status/remove、四 route 和绝对 `leo-ppt.exe`。
3. 在宿主图片能力明确 `available` 时完成一条零密钥真实 PPT 任务；保留样张确认、run、
   provider owner、耗时、成本、失败分类和最终 hash。
4. 使用 OpenAI 或 AtlasCloud 真实凭据完成一条外部 Provider 任务；凭据仅从环境变量或
   OS store 解析，运行结束执行 secret scan。
5. 可编辑 route 按需运行一次在线 PaddleOCR，并与 `builtin-ink` 降级结果分别记录。
6. 使用 Microsoft PowerPoint 打开最终 PPTX；逐页检查渲染、字体、动画/媒体、备注、
   对象可编辑性和重开保存；由人工 owner 签署接受或记录拒绝理由。

## 发布决定

当前候选可作为 macOS 本地机制和发布包结构的验证版本继续验收，但不应标记为“全部完成”
或对外宣称 Windows、真实 Provider 和最终 PPT 质量已经验证。完成上述现场清单
并达到方案规定的样本量后，才能关闭 D3、D6、D11、D13 及最终公开发布门禁。

本轮最终命令、两渠道安装样本与阻断分层汇总见
`.spec-first/workflows/spec-work/leo-ppt-generator/install-repeat-20260822/final-closeout.json`。
