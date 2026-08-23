# 2026-08-21 直接验证报告

## 结论

U0–U12 的源码、离线自动化、发布构建与干净 runtime 安装已完成验证；真实图片
provider 与 PowerPoint 桌面两项 required field proof 因当前环境缺少凭据/应用而
未运行，因此本报告的最终 verdict 为 `degraded`，不能声明完整现场交付已验证。

## Source binding

- Git 基线：`2230fa83bf358a64386d21b97765c5421d4537df`；最终改动未提交，验证绑定
  当前工作树而非新 revision。
- 当前 macOS 用户级 Runtime identity：`e64441b2b4516a3cdaf46f2daf14f3ee`；升级后
  再次 `ensure` 返回 `outcome=reused`。PowerShell 控制流只在 macOS `pwsh` 验证，
  不与 Windows 真机证据合并。
- 上游 commit/tree/license/clean archive：见 `docs/reviews/u0-report.md` 与
  `skills/leo-ppt-generator/upstreams.yaml`。
- Vendor/patch/lock：`sync_upstreams.py --check` 返回 `status=passed`、46 files。

## 已执行

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| U0 clean export isolation | 7/7 passed | 两上游同 runtime、资源、状态隔离、Office 拒绝与 worker gate |
| editable upstream regression | 82/82 OK | 固定 clean export 的上游测试 |
| 逐能力 proof | 60/60 passed | 按 YAML 原始顺序分别启动 pytest；60 个映射对应 42 个唯一 proof case |
| 当前仓库全套测试 | 247/247 passed | 最终树的 unit/integration/boundary/e2e/skill/release contract |
| 覆盖率 | total 87.53%；image 85、editable 83、hybrid 89、run index 91、routes 98、backend contract 85、lifecycle 87 | 达到 adapter ≥80%、run index ≥90%、hybrid ≥85%；vendor 由上游回归负责 |
| Skill 校验 | `quick_validate.py`: valid；bundle 仅 1 个 `SKILL.md` | 结构与发现面，不证明模型语义稳定性 |
| 静态检查 | first-party Ruff passed；first-party Bandit 0 个 medium/high；`sync_upstreams.py --check` 46 files passed；`git diff --check` passed | 固定 vendor 未纳入 first-party lint；对 vendor 直接运行 Bandit 仍报告 15 个 medium，见限制 |
| Wheel | 83 entries；46 vendor Python；7 schemas；0 pycache/pyc/legacy/`third_party`；SHA-256 `560e83990ded02b4ee9230b16b72454c491dbd6656a3bbf510e186acecadaae6` | 当前 Python 3.12/macOS arm64 的 clean-copy 构建；最终 wheel 自身隔离安装后四 route + replay 通过 |
| Skill bundle | 125 files、0 symlink、1 个 `SKILL.md`；SHA-256 `f34536a8d6d9ed04d5991f0d3123d7cf66a728009a97a5cd07dcf6b0f35bfdd0` | clean bundle、tar 解包与用户级安装目录逐文件一致 |
| Runtime clean install | Bash 与 macOS 上的 PowerShell 各自完成隔离安装；8/8 route doctor `ready`；安装后 Skill 无 `third_party`、`.venv`、`build`、`dist`、`*.egg-info` 或字节码 | PowerShell 控制流与 identity 已实测；不等同 Windows NTFS 真机 |
| Wheel 离线 route smoke | 8/8 passed；四条 route 的 fixture/openai-contract 组合；导入来自隔离 `site-packages` | 证明离线确定性机制，不外推真实 provider 质量 |
| 最终代码审查 | 内联复核发现并关闭 2 个低频未定义名/参数缺陷及 1 个失效恢复提示；6 个补丁均可重放，新增聚焦回归 4/4 passed | reviewer/validator/cross-model 因缺少派发授权未运行，采用 inline fallback，不声称独立审查覆盖 |
| Offline OCR | `builtin-ink`，PNG 与 trusted PPTX 各 1 页 | 无在线文字识别 |
| Office normalization | trusted PPTX 在 deny-network sandbox 中生成 1 页 run | 不证明任意不可信 Office 安全 |
| LibreOffice viewer | 26.2.1.2 将四 route 最终 fixture 分别转为 1 页 PDF/PNG，均非空 | 此次成功转换未在 deny-network sandbox 内完成 |

## 未运行/不可替代

- 真实图片 provider：`not-run/missing_credential`。
- 在线 PaddleOCR：`not-run/missing_credential`。
- Microsoft PowerPoint 桌面打开与逐页检查：`not-run/missing_application`。
- 人工视觉等价：`deferred/owner_acceptance_required`。
- 真实多页 worker 行为 eval：`not-run/dispatch_authorization_missing`；当前仅有
  deterministic Skill contract 与 worker gate 测试。
- Windows 10/11 x64 NTFS 真机安装与 `leo-ppt.exe` 四 route：`not-run/missing_environment`；
  本机 PowerShell 控制流与 Windows x64 wheel only-binary 解析均通过，但不能替代真机。
- 真实 GitHub 远程安装：`not-run/unpublished_worktree`；当前修改尚未发布，不能用本地
  archive server 或本地 `--source/-Source` 冒充公开下载验证。
- 固定 vendor 静态安全扫描：Bandit 当前报告 15 个 medium、0 个 high，主要是
  `urlopen` scheme 约束与 `ElementTree.fromstring`。Office 输入在 adapter 前置检查中
  fail closed，但该边界不消除 vendor 扫描结果，不能声明 vendor Bandit 全绿。

## 自动门结论

当前发布候选的自动化、逐项能力、固定上游、打包、双安装与四 route 机制均通过。
最终 verdict 仍为 `degraded`，原因只来自上述不可替代现场证据缺失；不得把该限制解释为
自动化失败，也不得把自动化通过解释为真实视觉、真实 provider 或桌面验收完成。
