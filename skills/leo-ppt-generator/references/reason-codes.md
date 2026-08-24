# Reason Codes

| Reason code | 含义 | 可恢复性 | 动作 |
| --- | --- | --- | --- |
| `runtime_incompatible` | 当前平台无 lock、runtime 缺失或 identity 不匹配 | 条件式 | 恢复原 runtime 或安装已验证兼容版本 |
| `runtime_install_failed` | venv、依赖或 smoke 失败 | 是 | 保留旧 current，检查 quarantine 与安装日志 |
| `operation_conflict` | operation id 已绑定不同请求 | 是 | 重新读取 operation/status，生成新 id |
| `worker_capability_unavailable` | 多页任务无已授权且可调用 worker | 条件式 | 提供 worker 能力或缩小为恰好一页 |
| `untrusted_office_input` | Office 文件来源未知或含主动/外部内容 | 是 | 提供可信确认后仍需通过 preflight，或改用 PDF/图片 |
| `backend_capability_missing` | backend 不支持当前 job 必需能力 | 是 | 选择兼容 backend 并重新确认 |
| `backend_contract_exists` | 目标 backend contract 已存在且未授权覆盖 | 是 | 选择新路径，或确认替换后显式传 `--overwrite` |
| `backend_contract_unwritable` | backend contract 目标路径无法安全写入 | 是 | 检查父目录权限与目标类型，改用可写普通文件路径 |
| `backend_model_invalid` | model 为空或不是有效字符串 | 是 | 使用 registry 默认 model，或提供非空 model |
| `assembly_precondition_failed` | 页数、顺序、尺寸、validation、notes 或 hash 不一致 | 是 | 修复具体前置条件后重新 finalize |
| `unknown_route` | route 不在四条有限定义中 | 否 | 返回受支持 route，不注入任意步骤 |
| `unknown_step` | step 不属于当前 route 的固定定义 | 否 | 重新读取机器协议和 route definition |
| `revision_conflict` | `run.json` 或领域状态的 expected revision 已漂移 | 是 | 重新读取当前状态并做 reconciliation |
| `generation_conflict`、`lease_invalid`、`lease_revoked`、`run_not_mutable` | worker lease 不属于当前 generation，或 run 已进入 terminal 状态 | 条件式 | 丢弃旧 worker 结果，重新 dispatch；completed/cancelled run 不接受新 mutation |
| `idempotency_conflict` | 相同 operation id 绑定了不同 fingerprint | 是 | 查询原 operation；新请求使用新 id |
| `unknown_contract_version` | PageArtifact/vendor contract 高于当前支持范围 | 条件式 | 使用兼容 runtime 或迁移 fixture |
| `config_invalid` | runtime 配置格式、取值或允许范围无效 | 是 | 按 v1 配置合同修正字段和值后重新执行 doctor |
| `config_schema_too_new` | 配置 schema 高于当前 runtime 支持范围 | 条件式 | rollback 或按兼容声明迁移配置 |
| `unknown_sensitive_field` | 配置出现未知且疑似敏感字段 | 是 | 删除明文秘密，改用允许的 credential reference |
| `credential_reference_missing` | 当前进程未见允许的 provider 凭据引用 | 是 | 由宿主或允许的环境变量注入，不在配置/日志中写值 |
| `worker_host_capability_unverified` | CLI 不能证明当前宿主可真实派发 worker | 条件式 | 由顶层 Agent 核对用户授权、会话能力和容量 |
| `provider_field_smoke_required` | 本地合同通过但尚未调用真实 provider | 条件式 | 在用户授权与凭据就绪后运行独立现场 smoke |
| `manual_visual_acceptance_required` | 自动结构检查不能替代人工视觉验收 | 条件式 | 对最终渲染逐页检查并记录接受/拒绝结果 |
| `raw_credential_forbidden` | 配置携带明文 token/key/secret | 是 | 改为宿主或 allowlist reference |
| `source_hash_mismatch` | 页面源文件与冻结 hash 不一致 | 是 | 重新确认输入并创建新 operation |
| `artifact_hash_mismatch` | 已记录产物在 finalize 前发生变化 | 是 | 重新验证并 record 当前产物 |
| `missing_page_artifact` | 预期页面未完成或缺失 | 是 | 完成缺页后再 finalize |
| `page_validation_failed` | 页面 validation 未通过 | 是 | 修复该页并按新 attempt 重试 |
| `partial_hybrid_confirmation_required` | 当前失败集合未得到精确降级确认 | 是 | 展示成功/失败集合并取得明确确认 |
| `partial_hybrid_proposal_required` | 未找到当前 run 的 partial-hybrid 提案 receipt | 是 | 先运行 `upgrade propose`，核对失败集合后再 confirm |
| `partial_hybrid_proposal_stale` | 提案对应的基线、选择或失败集合已漂移 | 是 | 丢弃旧提案并重新 propose，不复用旧确认 |
| `failure_set_mismatch` | partial 确认的失败集合与当前选择不一致 | 是 | 重新生成确认 fingerprint |
| `cleanup_revision_drift` | cleanup preview 后 run revision 改变 | 是 | 重新执行 dry-run |
| `cleanup_fingerprint_drift` | cleanup preview 后候选文件集合改变 | 是 | 重新执行 dry-run，不删除任何文件 |
| `cleanup_active_workers` | 仍有活动 worker | 是 | 等待或显式 cancel 后重试 |
| `cleanup_symlink_escape` | cleanup 发现 symlink/containment 风险 | 条件式 | 人工检查路径，不放宽全局删除 |
| `input_too_large` | 页数或选择页超出 MVP 限制 | 是 | 分批处理或缩小页集合 |
| `input_file_missing` | 冻结输入缺失，或显式清理后该 run 已禁止重新 prepare | 条件式 | 恢复原输入且 hash 一致，或创建新 run |
| `finalizer_failed` | PPTX 组装/验证未完成 | 是 | 保留既有产物，检查 finalizer 证据后重试 |
| `vendor_state_cleanup_failed` | 输入归一化完成后无法移除 vendor 临时状态 | 条件式 | 停止交付，保留现场并检查文件权限/锁后重试 |
| `style_name_invalid` | 风格名称不符合安全路径与长度规则 | 是 | 使用字母、数字、中文、连字符或下划线组成的名称 |
| `style_content_empty` | 风格内容为空 | 是 | 提供非空风格内容 |
| `style_content_unreadable` | 风格内容文件无法读取或不是有效 UTF-8 | 是 | 检查文件路径与编码后重试 |
| `style_unreadable` | 已保存风格文件无法读取或内容不合法 | 是 | 修复文件权限/编码，或删除后重新保存 |
| `style_sensitive_content_forbidden` | 风格内容包含疑似密钥、令牌、密码或邮箱等敏感信息 | 是 | 移除敏感信息；凭据只允许由宿主注入 |
| `style_name_conflict` | 用户风格名称已存在且未明确覆盖 | 是 | 使用 `--overwrite` 或 `--rename` 明确处理重名 |
| `style_not_found` | 请求的内置或用户风格不存在 | 是 | 先用 `style list` 查看可用风格名称 |
| `style_listed` | 风格列表已读取 | 不适用 | 从返回列表选择名称后执行 load/save |
| `style_loaded` | 风格内容已读取 | 不适用 | 使用返回的内容与 sha256 作为本次运行的风格输入 |
| `style_saved` | 用户风格已原子保存 | 不适用 | 保存返回的路径与 sha256，后续运行优先读取该风格 |
| `style_store_error` | 风格库操作的兜底错误 | 条件式 | 读取具体子 reason code 后修复并重试 |
| `style_rendered` | 模板确定性注入内容已渲染 | 不适用 | 将返回的 template 写入 deck_spec.style 与 slides[].layout |
| `templates_listed` | 模板轴清单已枚举 | 不适用 | 从清单选择渲染/版式/信息图/模式名 |
| `template_store_error` | 模板知识库加载失败或模板不存在 | 是 | 用 `style render --list-templates` 查看可用名后重试 |
| `backend_contract_unreadable` | 冻结的 backend contract 无法读取 | 是 | 检查 run 输入树与文件权限，必要时创建新 run |
| `credential_reference_invalid` | 凭据引用不是允许的 `env:`、`host:` 或 `keychain:` 形式 | 是 | 使用 provider allowlist 中的引用，不写入原始凭据 |
| `credential_reference_unavailable` | 声明的凭据引用当前不可解析 | 是 | 在宿主注入对应环境变量或启用明确 resolver |
| `credential_resolver_unavailable` | host/keychain 凭据未提供显式 resolver | 是 | 由宿主提供受控 resolver，不回退到隐式环境扫描 |
| `credential_provider_unsupported` | `auth` 收到 allowlist 外 Provider | 是 | 只使用 OpenAI、OpenAI-compatible 中转站、AtlasCloud 或 PaddleOCR |
| `provider_profile_invalid` | 中转站 profile 缺少字段、地址不安全或模型为空 | 是 | 使用 `config provider configure` 重新写入 HTTPS 地址与模型 |
| `provider_profile_missing`、`openai_compatible_configuration_required` | 已选择中转站但尚未配置地址与模型 | 是 | 执行 `config provider configure --provider openai-compatible` |
| `endpoint_origin_required`、`endpoint_origin_invalid`、`endpoint_origin_unsupported` | backend contract 的 endpoint 缺失、不安全或用于不支持的 Provider | 是 | 仅为 OpenAI-compatible 中转站创建包含 HTTPS endpoint 的 contract |
| `provider_profile_configured` | 中转站非敏感 profile 已安全写入 | 不适用 | 继续统一 config 向导写入凭据并复查状态 |
| `credential_tty_required` | `config credential set` 不是在交互式终端运行 | 是 | 在本地交互式终端执行，不通过参数、pipe 或聊天传递 secret |
| `credential_overwrite_confirmation_required` | 已存在 OS-store 凭据但未显式允许覆盖 | 是 | 核对 Provider 后用 `--overwrite` 再次执行 |
| `credential_empty` | 隐藏输入为空 | 是 | 重新运行 `config credential set` 并输入非空凭据 |
| `credential_store_locked`、`credential_store_denied`、`credential_store_failed`、`credential_store_unsupported` | OS 凭据服务锁定、拒绝、失败或平台不支持 | 是 | 解锁/授权系统凭据服务；不回退写入项目或普通配置 |
| `credential_store_acl_failed`、`credential_store_acl_too_broad` | Windows DPAPI 容器 ACL 无法收窄或验证过宽 | 是 | 修复当前用户目录 ACL 后重试，不消费该 blob |
| `credential_dpapi_encrypt_failed`、`credential_dpapi_decrypt_failed`、`credential_blob_invalid` | DPAPI 加解密失败、身份不符或密文损坏 | 是 | 删除损坏引用并在当前 Windows 用户下重新添加凭据 |
| `credential_environment_reference_preserved` | 向导已按用户确认保留既有 `env:<NAME>` 凭据引用；只保存引用，不复制或显示变量值 | 不适用 | 继续当前配置；如当前宿主未提供该变量，运行 `config repair` 改用可见环境变量或 OS store |
| `credential_store_reference_preserved` | 向导已按用户确认保留既有 OS-store 凭据引用；不读取、复制或显示受保护的凭据值 | 不适用 | 继续当前配置；如 OS store 不可用，运行 `config repair` 恢复受保护存储 |
| `credential_error` | 凭据 owner 返回未进一步分类的合同错误 | 条件式 | 停止消费并查看同次命令的具体 reason code |
| `credential_saved`、`credential_removed`、`credential_not_found`、`credential_missing`、`credential_store_available`、`credential_environment_available` | 凭据生命周期的非敏感结果 | 不适用 | 只消费状态与引用；输出不得包含 secret value |
| `setup_ready` | 本地机制、宿主声明与已确认 Provider 满足当前 route | 不适用 | 继续创建 backend contract 和 run；现场 Provider 与最终交付仍需独立验证 |
| `setup_local_mechanism_blocked` | doctor 的本地 runtime 或配置检查未通过 | 是 | 运行 primary action 查看原始 reason code，修复后重新执行 setup |
| `host_image_capability_unknown` | 宿主尚未明确声明图片能力是否可用 | 是 | 由宿主确认 available 或 unavailable 后重新执行 setup |
| `host_image_capability_unavailable` | 用户显式选择内建图片能力，但宿主已声明该能力不可用 | 是 | 选择并确认一个外部图片 Provider |
| `host_image_capability_invalid` | 宿主图片能力声明不是支持的三态值 | 是 | 使用 `available`、`unavailable` 或 `unknown` |
| `image_capability_requirement_invalid` | setup 收到 registry 未定义的任务级图片能力 | 是 | 只声明 `mask` 或 `reference`，route 基础能力由 setup 自动补齐 |
| `task_capability_invalid` | 任务级附加能力不是 `mask` 或 `reference` 之一 | 是 | 只使用 `mask`/`reference` 附加能力，route 基础能力由唯一 Route owner 解析 |
| `provider_registry_unknown` | Provider Registry 查询未命中已声明的 Provider 或策略 | 否 | 升级 runtime 或选择已注册 Provider；不按缺失声明推测能力 |
| `schema_not_found` | 请求的机器协议 schema 文件缺失或无法解析 | 否 | 升级 runtime 或修复 schema 打包；不伪造协议结构 |
| `config_service_error` | 配置编排层收到无法解释的输入或状态 | 否 | 读取具体子 reason code 后修复并重试 |
| `config_reset` | 非敏感 Provider 配置已原子重建，receipt 已失效，OS 凭据仍保留 | 不适用 | 重新运行 `config` 或保持未配置状态 |
| `provider_listed` | Provider Registry 与本地配置状态已列出 | 不适用 | 从列表选择一个 Provider，或继续当前任务 |
| `provider_removed`、`provider_not_found` | Provider profile 已删除，或目标 profile 原本不存在 | 不适用 | 需要时重新运行 `config provider configure`；凭据不会随 profile 自动删除 |
| `provider_preference_updated` | Provider 的 priority 或 enabled 偏好已更新 | 不适用 | 新任务将按更新后的配置重新选择；已冻结 run 不变 |
| `credential_status_reported` | 凭据引用状态已列出，未读取 secret value | 不适用 | 缺失时运行 `config credential set` |
| `paid_verification_consent_required` | `config verify` 尚未获得当前操作的一次性付费同意 | 是 | 在真实交互终端运行 `config` 并明确同意付费验证，或跳过并使用首张业务图片惰性验证 |
| `provider_smoke_executor_unavailable` | 已获得同意，但当前 runtime 没有可调用的真实 smoke executor | 否 | 不声明 `ready`；升级 runtime 或直接进入业务图片惰性验证 |
| `runtime_manager_unavailable` | current metadata 未解析到已安装的 runtime manager | 是 | 重新运行安装器或 bootstrap，恢复受管路径 |
| `runtime_lifecycle_unavailable` | update/rollback 无法启动 runtime manager 或执行超时 | 是 | 核对安装路径和活动安装进程后重试 |
| `runtime_lifecycle_protocol_invalid` | runtime manager 未返回可解析的版本化 JSON | 否 | 停止更新或回滚并重新安装可信版本 |
| `update_confirmation_required` | 更新预览完成，但尚未获得替换安装的明确确认 | 是 | 审阅目标版本后运行 `update --yes` |
| `wizard_cancelled` | 用户在配置向导中主动退出 | 是 | 保留已完成步骤，用 `config repair` 从最早未完成步骤续接 |
| `verification_failed` | 真实验证包装器收到无法解释的失败 | 是 | 读取具体子 reason code（鉴权/限流/产物校验等）后修复 |
| `verification_operation_error` | 验证 operation journal 状态或身份不合法 | 否 | 升级 runtime；不猜测 journal 语义 |
| `credential_transaction_inconsistent` | 凭据覆盖事务 checkpoint 缺失或互相矛盾 | 否 | 停止并运行 `config repair` 显式核对；不猜测 generation 或重复写 secret |
| `host_guard_error` | Host readiness guard 收到无法解释的状态 | 否 | 重新读取 config report 与宿主能力声明后重试 |
| `ocr_requirement_invalid` | OCR 阶段声明不是当前 setup 支持的值 | 是 | 使用 `not_required` 或 `editable_text_hints` |
| `image_provider_configuration_required` | 宿主图片能力不可用且没有外部图片 Provider 凭据 | 是 | 在本地安全终端配置一个 Provider 后重新执行 setup |
| `provider_confirmation_required` | 仅一个外部 Provider 就绪，但尚未得到用户确认 | 是 | 使用 primary action 明确确认该 Provider |
| `provider_choice_required` | 多个外部 Provider 就绪，需要用户明确选择 | 是 | 使用 primary action 选择一个 Provider，不按环境偶然状态静默选择 |
| `provider_capability_required` | 当前可用 Provider 不满足任务所需的 mask/reference 等能力 | 是 | 配置并确认 setup 候选中满足 `route_capabilities` 的 Provider |
| `selected_provider_unavailable` | 用户选择的 Provider 当前不可用 | 是 | 配置该 Provider 或重新明确选择其他 Provider |
| `setup_schema_version_unsupported` | setup 报告 schema 版本不是当前支持的 v1 | 是 | 升级 runtime 后重新生成和验证报告，不猜测新旧字段 |
| `setup_status_invalid`、`setup_primary_action_unexpected`、`setup_primary_action_required`、`setup_contract_error` | setup 报告违反 v1 状态或唯一动作不变量 | 条件式 | 停止消费该报告并升级或修复 runtime |
| `bootstrap_ready` | 已解析兼容解释器并完成受管 runtime ensure | 不适用 | 使用 `cli_reference` 继续 doctor/setup；不外推真实 Provider 或交付质量 |
| `bootstrap_bundle_incomplete`、`bootstrap_manifest_invalid`、`bootstrap_manifest_parser_missing` | bundle 缺少 launcher 所需文件、固定 manifest 无效或本机无法安全解析 | 是 | 重新安装 Skill；若系统已有可信 Python 3.12，可先走兼容入口 |
| `bootstrap_platform_unsupported` | 当前平台或架构不在发布矩阵 | 否 | 切换到 macOS arm64/x86_64 或 Windows x64，不强行执行其他工件 |
| `bootstrap_origin_forbidden` | manifest URL 不是固定 uv 版本的官方 HTTPS origin | 否 | 停止执行并重新安装可信发布包 |
| `bootstrap_download_tools_missing` | macOS 缺少安全下载、校验或解压所需系统工具 | 条件式 | 安装兼容系统 Python 3.12 后重试，不执行远程 pipe |
| `bootstrap_download_failed` | 固定 bootstrap 工件因网络、代理、404 或超时未完整下载 | 是 | 检查网络或代理后重试；旧 runtime 保持不变 |
| `bootstrap_artifact_size_invalid`、`bootstrap_artifact_hash_mismatch`、`bootstrap_archive_invalid` | 工件为空、超限、SHA-256 不匹配或归档结构不符 | 否 | 停止执行并重新安装可信发布包，不尝试替代源 |
| `bootstrap_extract_failed`、`bootstrap_python_install_failed`、`bootstrap_python_invalid` | 工件已校验，但解压、私有 Python 安装或版本复验失败 | 是 | 保留旧 runtime，清理私有 stage 后重新运行 launcher |
| `bootstrap_home_unwritable` | Leo 私有 home 无法创建或写入 | 是 | 设置可写的 `LEO_PPT_HOME` 后重试，不申请管理员权限 |
| `bootstrap_lock_timeout` | 同一 Leo home 的另一个 bootstrap 长时间未完成 | 是 | 等待活动操作结束后重试，不并行覆盖 |
| `bootstrap_unhandled_error` | PowerShell launcher 遇到未归一化异常 | 条件式 | 保存 reason 与阶段，重试一次；持续失败时进入高级诊断 |
| `provider_credential_mapping_unsupported` | provider 没有已登记的安全凭据映射 | 是 | 选择已注册 provider 或补充其执行 adapter |
| `backend_timeout_invalid`、`backend_retries_invalid` | backend 超时或重试参数不符合 v1 合同 | 是 | 修正为正整数超时与非负整数重试次数 |
| `secret_in_execution_receipt` | 执行 receipt 意外包含凭据值 | 是 | 停止交付并修复 receipt 脱敏逻辑 |
| `evidence_receipt_invalid`、`provenance_receipt_invalid`、`visual_receipt_invalid`、`acceptance_receipt_invalid` | provider、独立视觉或人工验收 receipt 不符合 v1 合同 | 是 | 补齐必需身份、逐页结论和 hash 后重录 |
| `evidence_sensitive_content_forbidden` | evidence receipt 含疑似凭据或授权头 | 是 | 删除秘密，只保留 provider receipt id 与非敏感身份 |
| `delivery_summary_required`、`delivery_identity_mismatch` | 尚无最终交付，或 receipt 的 PPTX hash 与当前交付不一致 | 是 | 对当前最终 PPTX 重新渲染/验收并生成新 receipt |
| `delivery_summary_invalid`、`delivery_structure_not_ready` | 最终 validation summary 不可读，或结构门禁未通过 | 是 | 修复最终产物与 validation summary，不能用人工 receipt 绕过 |
| `delivery_acceptance_pending` | 产物已生成，但独立渲染或人工视觉验收尚未通过 | 是 | 记录当前 PPTX 的 visual 与 manual acceptance receipt |
| `delivery_accepted` | 交付结构、独立渲染与人工验收均已闭环 | 不适用 | 保存 evidence refs 并交付 |
| `run_output_outside_project`、`input_outside_project`、`backend_contract_outside_project`、`project_path_untrusted`、`output_outside_run`、`output_path_untrusted` | 输入、backend contract 或 run 不在项目固定目录，或项目/final 路径包含不可信链接 | 否 | 将输入、合同和 run 分别放入项目 `sources/`、`contracts/`、`runs/`，移除路径链接并使用默认 final 输出 |
| `slides_fingerprint_conflict` | 已冻结的 `input/slides.json` 与新输入不一致 | 否 | 创建新 run，不能覆盖已绑定的逐页合同 |
| `evidence_conflict` | 同类证据路径已绑定不同内容 | 是 | 保留旧证据；变更结论必须创建新 run 或受控复验 |
| `provenance_artifact_mismatch` | provider provenance 未绑定 canonical 页面产物 hash | 是 | 从当前 domain state 读取页面产物 hash 后重新记录 |
| `provenance_recorded`、`visual_evidence_recorded`、`manual_acceptance_recorded` | provider provenance、独立视觉或人工验收证据已绑定 | 不适用 | 核对 receipt hash 与 validation summary 后交付 |
| `evidence_error` | evidence 操作的兜底错误 | 条件式 | 读取具体子 reason code 后处理 |

## 完整协议补充

以下分组仍逐个列出机器码；同一行中的代码共享该行的恢复语义。成功/状态码不是
错误，但同样属于稳定机器协议，调用者只能按代码和结构化字段推进。

| Reason code | 含义 | 可恢复性 | 动作 |
| --- | --- | --- | --- |
| `ready`、`route_selected`、`backend_contract_created`、`backend_contract_valid`、`run_created`、`run_status`、`operation_status`、`diagnosis_complete`、`stage_advanced` | 请求成功，结构化结果已可读取 | 不适用 | 按 `next_action` 或当前状态继续；backend valid 不代表真实凭据/provider 已就绪 |
| `run_retry_ready`、`cleanup_preview`、`cleanup_applied`、`run_cancelled` | 生命周期 mutation 已创建或重放 | 见 `safe_to_retry` | 保存 operation id；取消后不得 retry |
| `image_deck_prepared`、`image_recorded`、`image_delivery_completed` | image-deck 阶段已完成对应 checkpoint | 是 | 依据 state hash 继续 dispatch/record/assemble |
| `editable_dispatch_recorded`、`editable_recorded`、`editable_page_reset`、`editable_delivery_completed` | editable 阶段已完成对应 checkpoint | 见 `safe_to_retry` | 查询页面状态后继续，reset 不进入自动重试 |
| `delivery_completed`、`upgrade_delivery_completed`、`partial_hybrid_proposed` | delivery/finalize 已完成，或 partial-hybrid 提案 receipt 已冻结并可供确认 | 是 | 验证交付 manifest、PPTX hash 与类型；提案需由用户确认后 finalize |
| `input_required`、`output_required`、`backend_contract_required`、`run_path_required`、`slides_required`、`slide_required`、`result_required`、`editable_result_paths_required`、`upstream_tool_required` | 必需参数或输入路径缺失 | 是 | 补齐明确参数，不猜测默认文件 |
| `unsupported_input`、`input_type_mismatch`、`input_route_mismatch`、`route_confirmation_required`、`upgrade_route_required` | 输入类型、目标 route 或确认关系不成立 | 是 | 重新分类输入并取得会改变 route 的确认 |
| `input_changed_during_copy`、`backend_contract_changed_during_copy` | 冻结复制期间源文件发生变化 | 是 | 停止使用副本，稳定源文件后创建新 run |
| `run_symlink_forbidden` | run 用户内容树出现 symlink | 条件式 | 停止处理并人工核对来源，不放宽 containment |
| `missing_source`、`normalized_page_sources_missing`、`editable_input_normalization_failed` | 输入规范化未生成可用逐页源 | 条件式 | 查看上游 normalize 证据，修复依赖/输入后重试 |
| `empty_deck`、`invalid_page_sequence`、`invalid_page_id`、`invalid_slide_id`、`invalid_agent_id`、`unknown_page`、`unknown_page_mode`、`selection_out_of_range`、`page_selection_mismatch` | 页面集合、编号、worker id、mode、顺序或选择非法 | 是 | 修正页面清单或使用符合 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` 的 worker id，再重新 prepare |
| `selection_required` | selected upgrade 未冻结任何目标页面 | 是 | 在创建或更新 run 时明确选择至少一页，再执行 propose/finalize |
| `page_order_mismatch`、`page_count_mismatch`、`page_size_mismatch`、`selected_page_not_editable` | 组装输入不满足页序、页数、尺寸或 mode 前置条件 | 是 | 修正对应 PageArtifact 后重新 finalize |
| `validation_missing`、`validation_hash_mismatch`、`validation_ref_invalid`、`invalid_editable_page` | editable 单页缺少有效验证、验证报告发生漂移，或不是单页 PPTX | 是 | 重新 build/validate，再 record |
| `notes_manifest_invalid` | 输入 PPTX 的 speaker notes manifest 无法解析或页号无效 | 是 | 重新规范化输入并核对 notes manifest |
| `manifest_missing`、`manifest_invalid`、`manifest_hash_mismatch`、`delivery_manifest_invalid` | manifest 缺失、损坏或 hash 漂移 | 条件式 | 不使用损坏产物；从权威页面结果重建 |
| `image_deck_not_prepared`、`image_prepare_fingerprint_conflict`、`image_assemble_rebuild_required` | image-deck 未准备，或 prepare/assemble fingerprint 已变化 | 是 | 新 run 或显式 `--rebuild`，保留旧 revision |
| `upgrade_baseline_inspected`、`upgrade_baseline_imported` | 已完成 image delivery 已被读取或冻结为 upgrade baseline | 不适用 | 以 baseline fingerprint 作为后续 upgrade 输入身份 |
| `upgrade_baseline_required`、`upgrade_baseline_artifact_missing` | upgrade route 尚未导入完整 baseline，或 baseline 页面产物已缺失 | 是 | 先 inspect/import-baseline，不从原始输入绕过基线 |
| `upgrade_baseline_source_missing`、`upgrade_baseline_source_invalid`、`upgrade_baseline_delivery_missing`、`upgrade_baseline_delivery_hash_mismatch`、`upgrade_baseline_route_mismatch`、`upgrade_baseline_conflict`、`upgrade_baseline_artifact_changed`、`upgrade_baseline_delivery_changed`、`upgrade_baseline_manifest_invalid` | upgrade baseline 无法从完整、未漂移的 image delivery 导入 | 是 | 修复源 run 或重新导入；禁止从可变路径继续 upgrade |
| `upgrade_baseline_notes_changed`、`upgrade_baseline_manifest_changed` | 已冻结 baseline 的 notes 或 manifest identity 发生漂移 | 是 | 删除/隔离损坏 baseline，重新从未漂移的 image delivery 导入 |
| `editable_not_prepared`、`editable_prepare_fingerprint_conflict`、`editable_finalize_manifest_conflict` | editable 未准备，或 prepare/finalize 输入集合已变化 | 是 | 重新 diagnose；变化输入使用新 run/reset |
| `editable_dispatch_conflict`、`editable_dispatch_state_conflict`、`editable_agent_conflict` | page 的 agent、prompt 或状态与 dispatch/record 不一致 | 是 | 查询当前 binding；必要时确认后 reset |
| `reset_confirmation_required` | reset 会丢失已记录页面 | 是 | 明确 `--confirm-lost` 后执行一次非幂等 reset |
| `state_hash_conflict`、`vendor_revision_conflict`、`immutable_run_field`、`run_identity_conflict`、`run_index_invalid`、`state_mismatch` | expected state/revision、不可变 run identity、run index 或领域产物 hash 漂移 | 是 | 重新读取当前状态，不覆盖已有写入；无法唯一推导时 diagnose |
| `event_log_tail_invalid` | `events.ndjson` 尾部不完整或 seq 不连续 | 是 | diagnose 只读报告有效边界；按有效 seq 截断后再 mutation |
| `retry_state_conflict`、`run_not_retryable`、`cancel_state_conflict`、`run_cancelled_mutation_forbidden` | retry/cancel 的 terminal 或 fingerprint 条件不成立，或迟到 mutation 试图写入已取消 run | 条件式 | diagnose；cancelled/completed run 不再推进 |
| `unknown_operation` | operation id 不存在 | 是 | 查询 run status 和已记录 operation id |
| `cleanup_conflict`、`cleanup_revision_required`、`cleanup_scope_invalid`、`cleanup_input_requires_terminal_run` | cleanup 请求缺少 revision、scope 非法或 run 尚未 terminal | 是 | 重新 dry-run；只在允许状态使用精确 scope |
| `backend_contract_error`、`backend_contract_invalid`、`credential_reference_invalid`、`unknown_backend` | backend contract 不可解析、provider 未注册或 credential ref 非 allowlist 形式 | 是 | 使用 v1 schema 和 `env:/host:/keychain:` 引用 |
| `upgrade_baseline_error` | upgrade baseline 读取或冻结过程发生未细分的合同错误 | 是 | 读取具体子 reason code，修复源 delivery 后重试 |
| `backend_contract_unknown_field`、`backend_capabilities_invalid`、`backend_capability_overclaim` | contract 含未知字段、能力结构无效或声明超过 registry | 是 | 按 v1 精确字段和代码拥有的 provider capability 修正 |
| `backend_kind_mismatch`、`backend_mode_invalid`、`backend_mode_route_mismatch`、`backend_execution_owner_mismatch`、`backend_selection_source_invalid` | kind、mode、route、执行 owner 或选择来源互相矛盾 | 是 | 回到用户确认的 backend 选择，重新生成完整 contract |
| `credential_environment_not_allowed` | env 引用不在该 provider 的静态 allowlist | 是 | 只引用 provider 明确登记的环境变量 |
| `raw_credential_configuration_forbidden` | 旧 config 入口尝试接收/保存原始凭据 | 是 | 改用 run-level backend contract 和宿主注入 |
| `upstream_setup_replaced_by_runtime_manager` | 旧 setup 已由受管 runtime 替代 | 是 | 运行 `runtime_manager.py ensure|doctor` |
| `unknown_upstream`、`unknown_upstream_tool` | 固定 bridge 不认识上游或工具名 | 否 | 使用 `upstream --help` 中固定命令树 |
| `route_contract_error`、`contract_error` | 稳定合同的兜底分类；具体子码不可用 | 条件式 | 保存证据并运行 diagnose，不盲重试 |

## 配置与验证控制面（guided-provider-config）

以下 code 属于统一配置、验证与宿主守卫控制面；机器可读输出始终带
`execution_eligibility` 与唯一 `primary_action`。

| Reason code | 含义 | 可恢复性 | 动作 |
| --- | --- | --- | --- |
| `configuration_ready`、`provider_verification_not_run`、`provider_verification_stale` | 当前 Route 已真实验证、尚未验证或证据已过期 | 不适用 | 按 `start_task` 继续；stale 由显式 smoke 或下一张业务图片刷新 |
| `development_config_reset_required` | 开发期配置与正式 schema v1 不符 | 是 | 确认后执行 `config repair` 重建非敏感 v1；不猜测迁移 |
| `provider_selection_required` | 存在候选但未选择当前 Provider | 是 | 运行 `config` 进入统一向导 |
| `provider_priority_tie` | 多个合格 Provider 共享最高 priority | 是 | 使用 `config provider priority` 调整排序，或 `config provider select` 设置全局首选 |
| `requested_provider_unavailable` | 调用方显式指定的 Provider 不满足当前任务资格 | 是 | 修正指定项或配置该 Provider；不会静默改选其他 Provider |
| `backend_selection_invalid` | backend contract 的冻结选择 metadata 缺失、格式错误或与选择来源不一致 | 否 | 重新由当前 CLI 创建 contract；不要手改选择 metadata |
| `provider_profile_invalid:endpoint_origin`、`provider_profile_invalid:model` | endpoint 或 model 不符合 v1 合同 | 是 | `config repair` 修正字段 |
| `credential_input_channel_unavailable` | 无 TTY、无 env、无显式 stdin 通道可用 | 是 | 在终端运行 `config`，或用环境变量引用 |
| `credential_environment_missing` | env 引用存在但当前进程变量缺失 | 是 | `config repair` 改用宿主可见引用或 OS store |
| `provider_authentication_failed`、`provider_permission_denied`、`provider_endpoint_not_found`、`provider_model_not_found` | Provider 鉴权/权限/端点/模型错误 | 是 | `config repair` 核对凭据与档案 |
| `provider_rate_limited`、`provider_server_error`、`provider_timeout` | 限流、服务端错误或超时 | 是 | `wait_and_retry`；限流/超时不附 CLI |
| `provider_network_error` | DNS/连接/TLS 失败 | 是 | `config repair` 后重试 |
| `provider_outcome_unknown` | 调用结果不确定且无幂等证明 | 是 | `confirm_new_request`：用户确认后使用新 operation id |
| `provider_artifact_empty`、`provider_artifact_unreadable`、`provider_artifact_media_type_unsupported` | 产物为空、损坏或类型不支持 | 是 | `verify` 或 `repair` 后重试 |
| `verification_receipt_invalid`、`verification_evidence_persist_failed` | receipt 结构非法或 evidence 合并失败 | 是 | `config repair` 本地修复；业务图片成功后绝不再次调用 Provider |
| `config_write_failed` | 配置原子写失败 | 是 | `config repair`；不覆盖已存在有效配置 |
| `cli_path_unresolved` | 受管 runtime 绝对 CLI 尚未解析 | 是 | 由安装器返回 absolute launcher `ensure` 命令 |
| `config_protocol_invalid` | 机器协议输出不符合合同 | 是 | `config repair` |
| `config_check_unavailable` | 本地状态检查暂时不可用 | 是 | `wait_and_retry` |
| `host_check_required` | Host_Provider 需宿主现场确认 | 条件式 | 由当前宿主 setup 现场声明；不凭配置文件推断 |
| `host_recheck_allowed` | 复查后 Host 能力允许继续原任务 | 不适用 | `resume_task` 从中断节点恢复 |
