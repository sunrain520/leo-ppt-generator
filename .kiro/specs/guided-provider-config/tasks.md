# Implementation Plan: Guided Provider Config

## Overview

本计划使用 Python 实现统一 Provider 配置与 readiness 控制面，严格保持 Domain/Application/Ports/Infrastructure 边界，并按“纯合同 → 本地状态 → 真实验证 → 恢复协调 → 安装与宿主集成”的顺序增量交付。测试使用 pytest 与精确锁定的 `Hypothesis==6.165.5`；所有 Provider 调用默认使用 fake，真实付费 smoke 仅保留显式 opt-in 路径。

## Tasks

- [x] 1. 建立领域合同、单一真值与测试基础
  - [x] 1.1 定义配置领域模型、ports 和机器协议 schema
    - 在 `config/models.py` 定义 Provider、Route、Capability、状态、scope、evidence、typed action 与 report 数据模型及 invariant，并创建 `config-report-v1.json`、`verification-receipt-v1.json`。
    - 保证 Domain 层不依赖 CLI、subprocess、平台 API 或 vendor SDK，为后续 fake ports 和纯函数测试建立边界。
    - _Requirements: 2.1, 2.11, 2.12, 7.1, 7.2, 15.1_
  - [x] 1.2 将 Route 基础能力收敛到唯一 owner
    - 在 `application/routes.py` 的 RouteDefinition 中加入 `base_capabilities`，实现默认 `generate` 与任务级 `mask/reference` 并集解析，删除后续消费者自建映射的需要。
    - _Requirements: 6.19, 16.1, 16.2, 16.3, 16.4, 16.9_
  - [x] 1.3 实现 Reason catalog、typed Primary_Action 与跨 shell 命令渲染
    - 在 `config/reason_codes.py` 建立稳定原因码、阶段、恢复类别与唯一默认动作映射；实现只接受绝对 CLI/launcher 路径的 POSIX 和 PowerShell renderer。
    - 校验只有 `run_cli` 可包含 command，`primary_action: null` 是唯一无动作表示，未解析 CLI 时不得伪造路径。
    - _Requirements: 2.12, 2.13, 8.7, 10.7, 15.1, 17.6_
  - [x] 1.4 实现 fail-closed Provider Registry 并桥接现有 BackendRegistry
    - 新建 `config/provider_registry.py`，声明三态能力、adapter identity、probe/discovery、幂等、重试、产物 allowlist、逐能力 TTL 与 policy version；generic OpenAI-compatible 策略默认为 `unknown`。
    - 让现有 `backend_contract.py` 从该 Registry 构造候选元数据，避免维护第二份 capability 或安全策略真值。
    - _Requirements: 1.5, 1.6, 6.11, 6.13, 7.10, 19.1, 19.2, 19.3, 19.4, 19.6, 19.8_
  - [x] 1.5 固定 property-based testing 工具链
    - 在 macOS/Windows 测试约束与测试环境中精确锁定 `Hypothesis==6.165.5`，配置 deterministic CI profile 和每条 property 至少 100 examples，且不把 Hypothesis 加入 runtime 必需依赖。
    - _Requirements: 18.5_

- [x] 2. 实现 schema v1、敏感字段防线与跨平台凭据边界
  - [x] 2.1 用正式 schema v1 替换开发期 Config_File 合同
    - 扩展 `config/runtime_config.py`，实现 `LEO_PPT_HOME` 解析、完整字段/范围/Provider 引用校验、递归敏感字段扫描、source map、canonical digest、CAS 与权限受限原子写入。
    - 对开发期文件返回 `development_config_reset_required`，不猜测迁移；环境变量缺失返回 `credential_environment_missing` 而非 schema invalid。
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.2, 5.5, 10.8, 18.1, 18.2, 18.3, 18.4_
  - [x] 2.2 实现显式 Credential_Input_Channel 与受保护 envelope 基础
    - 在 `credentials.py` 定义不可序列化、redacted、可清零的 SecretBuffer，OS store envelope metadata，以及 env → existing store → TTY getpass → explicit stdin → unavailable 的唯一通道选择。
    - 禁止注册 `--api-key`，非 TTY 且无 `--key-stdin` 时不得读取 stdin/getpass，环境变量路径仅持久化引用。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 2.3 实现 macOS Keychain adapter
    - 使用进程内 Security.framework `SecItem` API 完成当前用户 add/update/read/delete，按 service/account 唯一定位并串行化访问，彻底移除 secret-in-argv 的 `security` 调用路径。
    - _Requirements: 3.10, 3.11, 14.1, 14.4, 14.5_
  - [x] 2.4 实现 Windows current-user DPAPI adapter
    - 使用 `CryptProtectData`/`CryptUnprotectData` 和受限 ACL 原子维护 `<LEO_PPT_HOME>/credentials/*.dpapi`，校验目录、文件、blob 与当前用户作用域，不允许 machine scope 或明文回退。
    - _Requirements: 3.10, 3.11, 14.2, 14.4, 14.5_
  - [x] 2.5 实现环境变量 credential version 与 Fingerprint_Key
    - 通过同一受保护 CredentialStore 创建/读取设备本地随机 Fingerprint_Key，并按 provider、env name、secret 计算 HMAC credential version；只暴露截断的非敏感引用。
    - Fingerprint_Key 缺失或轮换时只使 receipt stale，不保存裸 key hash，也不阻断其他 Provider。
    - _Requirements: 7.7, 10.8, 15.2_
  - [x] 2.6 编写 Property 6 的 property-based test
    - **Property 6: Credential channel selection is explicit and non-interfering**
    - 生成 TTY/env/store/stdin/flag 组合，验证只选择一个通道以及未授权输入零读取。
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6, 10.2, 10.3, 10.4**
  - [x] 2.7 编写 Property 9 的 property-based test
    - **Property 9: Provider profiles are normalized, isolated, and secret-free**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
  - [x] 2.8 编写 Property 11 的 property-based test
    - **Property 11: Sensitive unknown fields fail without disclosure**
    - **Validates: Requirements 5.5, 15.2, 18.4, 19.8**
  - [x] 2.9 编写 Property 19 的 property-based test
    - **Property 19: Environment credential versions are keyed and rotation-sensitive**
    - **Validates: Requirements 7.7**
  - [x] 2.10 编写 Property 32 的 property-based test
    - **Property 32: Credential storage fails closed on unsupported or unsafe platforms**
    - **Validates: Requirements 14.3, 14.4, 14.5**
  - [x] 2.11 编写 Property 34 的 property-based test
    - **Property 34: Development config reset never guesses or leaks**
    - **Validates: Requirements 18.3, 18.4**
  - [x] 2.12 编写 schema、profile 与 credential adapter 示例型单元测试
    - 覆盖最小/完整 v1、边界值、空 key、覆盖确认、跨 Provider 引用、环境变量缺失、Keychain/DPAPI 稳定错误分类和原子写失败旧字节保留。
    - _Requirements: 3.7, 3.8, 4.3, 4.4, 5.4, 10.8, 13.4, 14.3, 14.4, 18.3_

- [x] 3. 实现 Receipt Store 与纯 readiness 状态内核
  - [x] 3.1 实现 Verification_Fingerprint、逐能力 evidence 与原子 Receipt Store
    - 新建 `config/receipt_store.py`，按 canonical JSON 计算基础 fingerprint，校验 receipt schema、UTC 时间、Registry TTL 与 artifact digest，并按 Provider 独立存储。
    - 原子 merge 只保留同 fingerprint 下仍有效的其他能力；写失败保持旧字节，invalidate 与 inspection 不泄露 credential version 全值。
    - _Requirements: 6.5, 7.1, 7.2, 7.3, 7.4, 7.8, 7.9, 7.10, 13.5_
  - [x] 3.2 实现确定性的 readiness、scope 与 ConfigReport 内核
    - 新建 `config/readiness.py`，按 invalid → not_configured → operation-local degraded → ready → configured_unverified 优先级计算分层状态、执行资格、安装可用性和唯一 action。
    - 仅当当前 scope 的 required capabilities 被有效 evidence 或当前宿主现场能力覆盖时返回 ready；非目标 Provider 错误保持 Provider-local。
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.16, 6.18, 12.5, 16.5, 16.7, 16.8_
  - [x] 3.3 编写 Property 1 的 property-based test
    - **Property 1: Route scope conservation**
    - **Validates: Requirements 2.16, 6.19, 16.2, 16.3, 16.4, 16.8**
  - [x] 3.4 编写 Property 2 的 property-based test
    - **Property 2: Aggregate status is deterministic and priority-safe**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.18**
  - [x] 3.5 编写 Property 3 的 property-based test
    - **Property 3: Ready requires current capability evidence or live host coverage**
    - **Validates: Requirements 2.6, 2.16, 7.4, 16.3, 19.5**
  - [x] 3.6 编写 Property 4 的 property-based test
    - **Property 4: Config report protocol is closed and semantically consistent**
    - **Validates: Requirements 2.1, 2.11, 2.12, 2.14, 2.15, 15.1, 15.5**
  - [x] 3.7 编写 Property 15 的 property-based test
    - **Property 15: Receipt merge is atomic and capability-preserving**
    - **Validates: Requirements 6.5, 6.6, 7.9, 13.5**
  - [x] 3.8 编写 Property 16 的 property-based test
    - **Property 16: Fingerprint changes exactly with base identity**
    - **Validates: Requirements 4.6, 7.3, 7.5, 19.7**
  - [x] 3.9 编写 Property 17 的 property-based test
    - **Property 17: Capability expiry is independent and policy-bounded**
    - **Validates: Requirements 7.4, 7.10**
  - [x] 3.10 编写 Property 18 的 property-based test
    - **Property 18: Explicit re-verification refreshes generate only**
    - **Validates: Requirements 7.6**
  - [x] 3.11 编写 Property 33 的 property-based test
    - **Property 33: Provider and Route isolation is order-independent**
    - **Validates: Requirements 10.8, 16.5, 16.6, 16.7**

- [x] 4. 实现 ConfigService、向导与 CLI/状态协议
  - [x] 4.1 实现只读 status 与共享 ConfigService 编排
    - 新建 `config/service.py`，通过 ConfigStore、CredentialStore metadata、Registry、ReceiptStore 和 Clock 构建同一 ConfigReport；status 类型接口不可访问 Provider port。
    - 列出所有 Provider 的非敏感状态，稳定处理 selected provider、默认 Route 和 provider selection required。
    - _Requirements: 1.5, 1.6, 2.11, 5.1, 5.2, 5.3, 5.4, 6.18, 16.4, 16.6, 16.7, 16.8_
  - [x] 4.2 实现 configure/repair/change 用例与 Config_Wizard
    - 新建 `config/wizard.py`，实现四项菜单、零提问 happy path、隐藏输入、显式 stdin、默认否费用提示、取消与 earliest-step repair；change 在候选提交前保留原 Provider。
    - ConfigureRequest 只携带短生命周期 secret handle，一次性 consent 不得持久化或由安装器/宿主构造。
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 3.1, 3.3, 3.8, 4.1, 6.1, 6.2, 13.1, 13.2, 13.6, 13.7_
  - [x] 4.3 注册统一 `leo-ppt config` 命令组与渲染/退出合同
    - 在 `cli.py` 注册 `status/verify/repair/change`、`--json`、`--route`、`--key-stdin` 和显式 `--verify`，从同一 report 渲染 human/JSON，不复制状态规则。
    - 实现 status/config/repair/verify 的稳定退出类别、准确 `configured_unverified` 文案和至多一个 Primary_Action。
    - _Requirements: 1.1, 1.2, 2.11, 2.14, 2.15, 6.3, 10.1, 10.5, 15.5, 17.1_
  - [x] 4.4 编写 CLI 与向导示例型单元测试
    - 覆盖五个命令、菜单、默认“否”、空 key 重试、零提问路径、JSON/human golden、退出码与明文参数拒绝。
    - _Requirements: 1.2, 1.3, 1.7, 2.14, 2.15, 3.4, 3.7, 6.1_
  - [x] 4.5 编写 Property 5 的 property-based test
    - **Property 5: Shell command rendering round-trips safely**
    - **Validates: Requirements 2.13, 8.7, 10.7**
  - [x] 4.6 编写 Property 10 的 property-based test
    - **Property 10: Local status is side-effect free**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - [x] 4.7 编写 Property 12 的 property-based test
    - **Property 12: Paid verification requires a one-shot affirmative capability**
    - **Validates: Requirements 1.4, 6.1, 6.2, 6.3**
  - [x] 4.8 编写 Config CLI subprocess 集成测试
    - 以参数数组运行五个命令，验证 status 零网络、stdout/stderr 分离、非 TTY 不等待、无 flag 不消费管道、路径引用和协议 schema。
    - _Requirements: 2.11, 2.13, 5.1, 10.2, 10.6, 10.7, 15.5_

- [x] 5. 实现 generate-only smoke 与业务图片惰性验证包装器
  - [x] 5.1 实现共享 VerifiedProviderExecutor、产物校验与安全失败分类
    - 新建 `config/verification.py`，统一 probe、Provider 调用、错误归一、普通文件/非空/大小/Pillow decode/media type 校验、摘要和 evidence 生成。
    - 原始响应、header、prompt 与异常正文不得进入 DomainFailure；401/403/404/429/5xx/网络/超时/空或损坏产物映射稳定 reason/action。
    - _Requirements: 6.4, 6.7, 6.8, 15.2, 15.3, 15.4_
  - [x] 5.2 实现显式 generate-only Provider_Smoke 与安全 probe/retry
    - `verify()` 必须接收一次性 PaidVerificationConsent，忽略现有 generate evidence 但不刷新其他能力；仅 Registry 明确安全时运行 Auth Probe/model discovery。
    - 通过 `backend_execution.py` 传递受控 credential 和幂等键；v1 smoke 仅生成 generate evidence，摘要后删除临时图片。
    - _Requirements: 4.7, 6.3, 6.4, 6.5, 6.10, 6.11, 6.12, 6.13, 6.14, 6.15, 6.19, 7.6_
  - [x] 5.3 将首张真实业务图片接入同一验证包装器
    - 在业务图片执行路径中传入实际 capability 集合与 `business` ownership，先由 run owner 原子保留图片，再合并对应 evidence；不为未执行能力写证据。
    - 失败时保留主题、材料、逐页稿和中间产物，并在图片节点生成可恢复 checkpoint。
    - _Requirements: 6.6, 6.9, 6.16, 7.8, 11.3, 11.8, 16.2_
  - [x] 5.4 编写 Property 13 的 property-based test
    - **Property 13: Valid images are the only source of capability evidence**
    - **Validates: Requirements 6.4, 6.6, 6.7, 6.19, 7.8**
  - [x] 5.5 编写 Property 14 的 property-based test
    - **Property 14: Artifact ownership controls retention**
    - **Validates: Requirements 6.9, 6.10, 6.16, 13.5**
  - [x] 5.6 编写 Property 21 的 property-based test
    - **Property 21: Probe success never implies image readiness**
    - **Validates: Requirements 6.11, 6.12**
  - [x] 5.7 编写 Property 22 的 property-based test
    - **Property 22: Retry occurs if and only if outcome safety is established**
    - **Validates: Requirements 6.13, 6.14, 6.15, 19.4**
  - [x] 5.8 编写 Property 25 的 property-based test
    - **Property 25: Provider failures preserve configuration and map safely**
    - **Validates: Requirements 6.7, 6.8, 15.4**
  - [x] 5.9 编写 Provider、generate-only smoke 与故障矩阵集成测试
    - 使用 fake HTTP/adapter 覆盖所有稳定失败类别、probe/model discovery 三态、幂等键和 operation id；断言 smoke 删除图片且从不产生 edit/mask/reference evidence。
    - _Requirements: 4.7, 6.4, 6.7, 6.10, 6.11, 6.12, 6.13, 6.15, 6.19_

- [x] 6. 实现 Verification_Scope single-flight 与本地 evidence 恢复
  - [x] 6.1 实现跨进程 VerificationCoordinator 与 operation journal
    - 新建 `config/verification_operations.py`，按 fingerprint 与规范化 capability 集合计算 scope key，以 FileLock 和原子 journal 协调 owner/joiner、terminal result 与稳定 operation id。
    - 崩溃恢复区分 pre-send、accepted/idempotent、unknown outcome 和 evidence_pending；joiner 共享结果且不创建新付费调用。
    - _Requirements: 6.14, 6.15, 6.17, 13.3_
  - [x] 6.2 扩展 RunIndex 的图片暂停、恢复与 evidence-repair 引用
    - 在 `application/run_index.py` 原子保存 task/run id、Route、stage、operation id、artifact refs 和非敏感 recovery digest；图片成功但 receipt 失败时仅提供本地 merge 恢复。
    - _Requirements: 6.9, 6.16, 11.7, 11.8, 13.3, 13.5_
  - [x] 6.3 编写 Property 23 的 property-based test
    - **Property 23: Verification is single-flight per scope**
    - **Validates: Requirements 6.17**
  - [x] 6.4 编写 Property 24 的 property-based test
    - **Property 24: Evidence persistence recovery never recalls the Provider**
    - **Validates: Requirements 6.16, 13.5**
  - [x] 6.5 编写多进程 single-flight 与 owner 崩溃集成测试
    - 共享真实 `LEO_PPT_HOME` 和 FileLock，覆盖并发调用一次、共享成功/失败、pre-send 接管、post-send unknown 禁止重试和 idempotent resume。
    - _Requirements: 6.14, 6.15, 6.17_
  - [x] 6.6 编写业务 run lifecycle 恢复集成测试
    - 覆盖首图失败、业务图成功但 evidence merge 失败、纯本地 repair、同 run/stage/artifact refs 恢复和零重复 Provider 调用。
    - _Requirements: 6.9, 6.16, 11.8, 13.3, 13.5_

- [x] 7. 实现配置事务、repair 和 Provider change 的崩溃一致性
  - [x] 7.1 实现 ConfigTransaction journal 与恢复状态机
    - 新建 `config/transactions.py`，按 prepared → receipt_invalidated → credential_written → config_committed → completed 原子记录非敏感 checkpoint。
    - 凭据覆盖严格先失效 receipt，再写 envelope，最后 CAS 提交 generation；元数据矛盾 fail closed。
    - _Requirements: 3.9, 13.2, 13.3, 13.4, 14.4_
  - [x] 7.2 将 `config repair` 和 `config change` 接入事务恢复
    - 根据 Reason catalog 从最早未完成步骤续接，不重复已完成 secret 写入、不修改无关 Provider；候选切换失败时保留原 ready Provider。
    - 开发配置重建必须再次确认，只重建非敏感 v1，不删除无法确认归属的凭据。
    - _Requirements: 13.2, 13.3, 13.6, 13.7, 18.3, 18.4_
  - [x] 7.3 编写 Property 8 的 property-based test
    - **Property 8: Existing credentials are preserved without overwrite consent**
    - **Validates: Requirements 3.8, 3.9, 13.1**
  - [x] 7.4 编写 Property 30 的 rule-based state machine test
    - **Property 30: Config transactions are crash-consistent and provider-isolated**
    - 对每个事务 barrier 注入失败，验证恢复只出现旧完整状态或新完整状态。
    - **Validates: Requirements 3.9, 13.2, 13.3, 13.4, 13.6, 14.4**
  - [x] 7.5 编写 Property 31 的 property-based test
    - **Property 31: Provider change preserves the previous ready selection until commit**
    - **Validates: Requirements 13.7**
  - [x] 7.6 编写配置事务 kill-point 故障注入集成测试
    - 在 receipt invalidation、CredentialStore write、ConfigStore replace 与 completion barrier 杀进程，再运行 repair 验证收敛、Provider 隔离与旧文件完整。
    - _Requirements: 3.9, 13.2, 13.3, 13.4, 13.6, 14.4_

- [x] 8. 将 Registry 和 Route 单一真值接入 setup 与执行器
  - [x] 8.1 移除 setup/backend 的本地能力与安全策略副本
    - 修改 `setup.py`、`backend_execution.py` 和相关 loader，共同消费 `route_definition(...).base_capabilities` 与同一 ProviderRegistry snapshot，并支持 OpenAI-compatible 的一致选择与状态。
    - _Requirements: 1.6, 16.1, 16.6, 16.9, 19.1, 19.5_
  - [x] 8.2 编写 Property 20 的 property-based test
    - **Property 20: Registry policy is fail-closed**
    - **Validates: Requirements 4.7, 6.11, 6.12, 19.2, 19.3, 19.4, 19.6, 19.8**
  - [x] 8.3 编写 Property 35 的 property-based test
    - **Property 35: Registry consumers observe one policy**
    - **Validates: Requirements 1.6, 16.9, 19.1**
  - [x] 8.4 编写 Registry/Route 消费者契约集成测试
    - 对每个 Provider 验证 adapter、capability、probe/discovery、idempotency、retry、TTL 字段完整，并断言 setup/config/executor 查询结果一致且用户配置无法提升 unknown。
    - _Requirements: 16.1, 16.6, 16.9, 19.1, 19.2, 19.6, 19.8_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 10. 接入安装与更新后的 Post_Activation_Onboarding
  - [x] 10.1 扩展 runtime manager 的绝对 CLI 解析与 onboarding 包装
    - 修改 `scripts/runtime_manager.py`，从 bootstrap receipt/current runtime 解析绝对 CLI_Path，以参数数组执行 `config status --json --route generate`，校验协议并为 unresolved path 渲染已知 launcher repair。
    - 更新流程始终本地复查，复用匹配 evidence；只有显式 operation context 才传播 operation-local degraded/action。
    - _Requirements: 8.1, 8.7, 8.8, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - [x] 10.2 在 POSIX 安装器中加入激活后的 onboarding
    - 修改 `install.sh`，把 Skill 原子激活保持为 Install_Transaction commit point；之后报告 installed/configuration/verification/eligibility，TTY 可选择立即配置或推迟，无 TTY 不等待且不产生费用同意。
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 10.6, 10.7_
  - [x] 10.3 在 PowerShell 安装器中加入等价 onboarding
    - 修改 `install.ps1`，使用参数数组与 PowerShell call operator 安全处理带空格/引号路径；配置失败、取消或推迟不得触发 Skill 回滚。
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 10.6, 10.7_
  - [x] 10.4 编写 Property 26 的 property-based test
    - **Property 26: Onboarding decisions do not alter installation truth**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6**
  - [x] 10.5 编写 Property 27 的 property-based test
    - **Property 27: Update checks reuse valid state and preserve typed recovery**
    - **Validates: Requirements 9.2, 9.3, 9.5**
  - [x] 10.6 扩展 installer/release 自动化测试
    - 覆盖激活后顺序、ready/usable_unverified/installed_not_ready、TTY 推迟、无 TTY 短超时、向导失败不回滚、更新不覆盖 `LEO_PPT_HOME` 以及 POSIX/PowerShell 特殊路径。
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 9.1, 9.6, 10.6, 10.7_

- [x] 11. 实现 Host_Readiness_Guard 与原任务恢复
  - [x] 11.1 实现 capability-local Host Readiness Guard
    - 新建/扩展 application guard，组合只读 config status、setup 的现场 Host_Capability_State、External Provider 状态与任务 scope，返回 `continue_host`、`continue_external` 或 `pause` 及至多一个动作。
    - Host available 只覆盖本次宿主能力，不写 External receipt；host unavailable 按 External ready/unverified/degraded/blocked 降级。
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4, 12.5_
  - [x] 11.2 实现 guard recheck 与同任务节点恢复
    - 将 pause/recheck/resume 接入 RunIndex：修复后重新执行 status+setup，allowed 才清除 pause 并恢复同 task/run/Route/stage/input refs/artifact refs，其他状态仅替换唯一动作。
    - _Requirements: 11.6, 11.7, 11.8, 13.3_
  - [x] 11.3 更新项目拥有的 Skill 首次使用合同
    - 仅修改 `skills/leo-ppt-generator/SKILL.md` 与 `skills/leo-ppt-generator/references/first-use.md`，要求 Codex/Claude/Kiro 首次图片节点必经 guard、禁止聊天 secret、配置后复查恢复，并提供无 post-install hook 兜底。
    - 不直接修改 `.agents/skills/`、`.codex/` 或其他生成投影。
    - _Requirements: 11.1, 11.4, 11.5, 11.6, 11.7, 11.9, 18.6_
  - [x] 11.4 编写 Property 28 的 property-based test
    - **Property 28: Host guard is capability-local and receipt-independent**
    - **Validates: Requirements 11.2, 11.3, 11.4, 12.1, 12.2, 12.3, 12.4, 12.5**
  - [x] 11.5 编写 Property 29 的 property-based test
    - **Property 29: Guard recheck resumes the same task state**
    - **Validates: Requirements 11.6, 11.7, 11.8**
  - [x] 11.6 扩展 Codex、Claude、Kiro skill eval
    - 覆盖 host available 零 key、External unverified 首图、blocked 单命令、degraded typed action、配置完成后同任务恢复和无 post-install hook fallback；扫描 tool transcript 中的 canary。
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 12.3, 12.4_

- [x] 12. 同步统一入口文档、帮助与 Reason_Code 合同
  - [x] 12.1 更新 CLI help、README、用户手册和故障排查
    - 统一推荐 `leo-ppt config`，覆盖首次安装、更新、宿主首次调用、中转站、环境变量/显式 stdin、change/repair、`usable_unverified` 与 `installed_not_ready` 语义。
    - 加入各 External Provider 官方 key 获取入口、所需权限、可能费用提示和禁止在聊天、参数、项目配置或 issue 粘贴 API Key 的说明。
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_
  - [x] 12.2 编写 Property 36 的 property-based test
    - **Property 36: Reason documentation is total and single-action**
    - **Validates: Requirements 17.6**
  - [x] 12.3 编写 release 文档/帮助一致性测试
    - 比较 README、user guide、troubleshooting、Skill source、CLI help 与 Reason catalog，验证入口、状态术语、官方链接、费用提示、禁止 secret 和唯一动作完整一致。
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_

- [x] 13. 补齐安全 canary、平台集成与成本安全验证
  - [x] 13.1 编写 Property 7 的 property-based security test
    - **Property 7: Secrets never cross forbidden sinks**
    - 用高熵 canary 覆盖成功、取消和全部故障路径，扫描 Config_File、receipt、journal、run、stdout/stderr、日志、异常、遥测、argv 与普通临时文件。
    - **Validates: Requirements 3.4, 3.10, 3.11, 10.5, 11.5, 15.2**
  - [x] 13.2 编写 macOS arm64 Keychain 平台集成测试
    - 对隔离 service/account 执行 SecItem add/update/read/delete round-trip，验证锁定/拒绝分类、进程表无 secret-in-argv，并可靠清理测试 item。
    - _Requirements: 3.11, 14.1, 14.4, 14.5_
  - [x] 13.3 编写 Windows x64 DPAPI/ACL 平台集成测试
    - 验证 current-user round-trip、其他用户不可解密（环境允许时）、目录/文件 ACL 无 `Users`/`Everyone` 写权限，以及损坏 blob/放宽 ACL fail closed。
    - _Requirements: 14.2, 14.4, 14.5_
  - [x] 13.4 编写 unsupported platform adapter contract test
    - 断言安全存储不可用时稳定返回 `credential_store_unsupported`，不创建 plaintext fallback、普通临时 secret 或可被识别为有效凭据的残留文件。
    - _Requirements: 14.3, 14.4_
  - [x] 13.5 编写文件系统故障注入与 canary 扫描集成测试
    - 覆盖 symlink、特殊文件、宽 ACL、temp race、fsync/replace 失败和 endpoint userinfo/query/fragment；递归解析所有非敏感 schema 并确认日志只含安全 origin。
    - _Requirements: 3.10, 4.3, 5.5, 13.4, 14.4, 15.2, 15.3_
  - [x] 13.6 编写离线零真实 Provider 调用与 opt-in paid smoke 安全门测试
    - 普通 unit/integration/release/installer/skill eval 全部断言零真实网络；真实 Provider smoke 必须独立低额度账户、显式环境开关和费用提示，且只验证 generate 后删除临时图。
    - _Requirements: 6.1, 6.3, 6.4, 6.10, 6.19_

- [x] 14. 收敛旧入口、完成端到端 wiring 与验证矩阵
  - [x] 14.1 收敛仅服务开发期的重复配置入口和 capability 表
    - 在统一入口、Registry 和 schema v1 已接通后，删除或降级重复的公开 auth/provider/backend 配置路径与旧 fixtures，同时保留必要内部能力和回归覆盖。
    - 确认项目拥有源码与安装/投影流程是唯一持久真值，不修改生成投影。
    - _Requirements: 1.5, 1.6, 18.2, 18.5, 18.6_
  - [x] 14.2 编写全离线端到端配置与任务恢复 journeys
    - 覆盖首次 TTY/非 TTY 配置、OpenAI-compatible、跳过/显式 smoke、更新复用、首图惰性验证、single-flight、evidence repair、Provider change 回退和宿主恢复。
    - _Requirements: 1.1, 4.1, 6.2, 6.3, 6.6, 8.1, 9.1, 10.6, 11.7, 13.5, 13.7_
  - [x] 14.3 接通完整 CI 验证矩阵
    - 配置 unit/property/schema/type/lint、macOS Keychain、Windows DPAPI、single-flight、多进程 crash injection、run resume、installer release 和三宿主 skill eval 分层门禁。
    - 保留 Hypothesis seed/最小 counterexample，不通过降低 examples、扩大 retry 或放宽 canary scan 绕过失败。
    - _Requirements: 14.1, 14.2, 15.2, 17.1, 18.5_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 实现语言为 Python；shell/PowerShell 仅用于现有安装器适配与对应测试。
- 标记 `*` 的测试子任务是可选加速项，但 dependency graph 仍完整调度；所有核心实现子任务均为必做。
- 每条 Correctness Property 恰好映射一个独立 property-based testing 子任务，并至少运行 100 examples。
- 默认测试不得产生真实费用；真实 Provider smoke 只能通过独立、显式授权的 opt-in 门执行。
- 不实现浏览器、localhost 配置服务或网页密钥录入，也不直接编辑生成的宿主投影。


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.5"] },
    { "id": 1, "tasks": ["1.4", "2.1", "2.2", "3.1"] },
    { "id": 2, "tasks": ["2.3", "2.7", "2.8", "2.11", "3.2", "8.2"] },
    { "id": 3, "tasks": ["2.4", "2.6", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "8.3"] },
    { "id": 4, "tasks": ["2.5", "4.1", "5.1"] },
    { "id": 5, "tasks": ["2.9", "2.10", "2.12", "4.2", "4.6", "5.2", "7.1", "8.1"] },
    { "id": 6, "tasks": ["4.3", "4.5", "5.3", "5.4", "5.6", "5.7", "5.8", "5.9", "6.1", "7.2", "8.4"] },
    { "id": 7, "tasks": ["4.4", "4.7", "4.8", "5.5", "6.2", "6.3", "7.3", "7.4", "7.5", "7.6", "10.1", "11.1"] },
    { "id": 8, "tasks": ["6.4", "6.5", "6.6", "10.2", "10.3", "11.2", "11.4"] },
    { "id": 9, "tasks": ["10.4", "10.5", "10.6", "11.3", "11.5", "13.2", "13.3", "13.4"] },
    { "id": 10, "tasks": ["11.6", "12.1", "13.1", "13.5", "13.6", "14.1"] },
    { "id": 11, "tasks": ["12.2", "12.3", "14.2"] },
    { "id": 12, "tasks": ["14.3"] }
  ]
}
```
