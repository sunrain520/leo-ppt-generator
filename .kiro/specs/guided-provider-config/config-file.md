# Leo PPT Generator 配置文件内容说明

## 1. 结论

统一配置流程最终写入的主配置文件是：

```text
<LEO_PPT_HOME>/config.yaml
```

它只保存非敏感配置，不保存 API Key。完整配置状态由三个彼此独立的存储面组成：

| 存储面 | 用途 | 是否包含密钥明文 |
| --- | --- | --- |
| `<LEO_PPT_HOME>/config.yaml` | 当前 External Provider、Provider 档案、非敏感凭据引用、runtime 参数 | 否 |
| macOS Keychain 或 Windows DPAPI | Provider API Key | 仅由操作系统保护存储持有 |
| `<LEO_PPT_HOME>/verification-receipts/<provider>.json` | Provider 基础 fingerprint 与按能力独立累计的非敏感成功证据 | 否 |

因此，复制 `config.yaml` 不能复制密钥，也不能单独证明图片服务已经 `ready`。当档案与凭据引用完整，但当前 readiness scope 的 required capabilities 未被匹配基础 fingerprint 且未过期的 Capability_Evidence 完整覆盖时，状态为 `configured_unverified`：允许开始任务，首张真实业务图片会完成惰性验证。Provider 能力、探测、幂等、重试和 Capability_Evidence TTL 来自 checked-in Provider Registry 与版本化 Verification Policy，不写入用户配置，也不能由安装器、Agent 或用户输入覆盖。

## 2. `LEO_PPT_HOME` 的解析

`LEO_PPT_HOME` 环境变量存在时使用其展开后的绝对路径；否则使用平台默认目录。

| 平台 | 默认 `LEO_PPT_HOME` | 主配置文件 |
| --- | --- | --- |
| macOS | `~/Library/Application Support/leo-ppt-generator` | `~/Library/Application Support/leo-ppt-generator/config.yaml` |
| Windows | `%LOCALAPPDATA%\leo-ppt-generator` | `%LOCALAPPDATA%\leo-ppt-generator\config.yaml` |
| 其他平台 | `${XDG_DATA_HOME:-~/.local/share}/leo-ppt-generator` | `<LEO_PPT_HOME>/config.yaml` |

当前交付只承诺 macOS arm64 和 Windows x64 的安全凭据存储。其他平台即使能解析 `config.yaml`，在没有受支持 Credential_Store 时也必须返回 `credential_store_unsupported`，不得创建明文凭据文件。

## 3. 当前实现与目标格式

### 3.1 当前 runtime

当前源码中的开发期 `config.yaml` 使用 `schema_version: 1`，支持以下字段：

- `schema_version`
- `max_concurrent_workers`
- `max_run_bytes`
- `timeouts.worker_page_seconds`
- `timeouts.backend_api_seconds`
- `timeouts.backend_api_retries`
- `provider_profiles.openai-compatible.endpoint_origin`
- `provider_profiles.openai-compatible.model`

当前 CLI 已有 `auth`、`provider configure`、`backend` 和 `setup` 等开发期底层命令，但尚未实现本规格定义的 `leo-ppt config` 命令组、`selected_provider` 和 Verification_Receipt。这些内部形态尚未对外发布，不构成兼容基线。

### 3.2 本规格落地后的目标格式

统一配置功能使用 `schema_version: 1`，作为首次正式发布的唯一公共配置合同。当前开发期文件虽然也写作 `schema_version: 1`，但其字段集合尚未发布；实现阶段直接以本文件定义的完整 v1 合同替换开发期形态，不引入 v2 或自动迁移层。

首次发布的完整 v1 包含：

- `selected_provider`
- `provider_profiles.openai`
- `provider_profiles.openai-compatible`
- `provider_profiles.atlascloud`
- 每个 External Provider 的 `credential_source`
- 每个 External Provider 的 `credential_ref`
- OS 存储凭据的 `credential_generation`

`builtin-imagegen` 不写入 `config.yaml` 作为持久 `ready` Provider。它只能由 Codex、Claude、Kiro 等当前宿主现场检查并在本次任务上下文中选择。

## 4. schema v1 完整示例

以下示例展示三个 External Provider 均已配置、当前选择中转站的情况。真实用户通常只会出现自己配置过的 Provider。

```yaml
schema_version: 1

selected_provider: openai-compatible

max_concurrent_workers: 4
max_run_bytes: 10737418240

timeouts:
  worker_page_seconds: 600
  backend_api_seconds: 60
  backend_api_retries: 3

provider_profiles:
  openai:
    model: gpt-image-2
    credential_source: os-store-reference
    credential_ref: keychain:leo-ppt-generator/openai
    credential_generation: 1

  openai-compatible:
    endpoint_origin: https://images.example.com
    model: gpt-image-2
    credential_source: os-store-reference
    credential_ref: keychain:leo-ppt-generator/openai-compatible
    credential_generation: 2

  atlascloud:
    model: gpt-image-2
    credential_source: environment-reference
    credential_ref: env:ATLASCLOUD_API_KEY
```

Windows 上使用 DPAPI 时，OS 存储引用形式为：

```yaml
provider_profiles:
  openai-compatible:
    endpoint_origin: https://images.example.com
    model: gpt-image-2
    credential_source: os-store-reference
    credential_ref: host:dpapi/openai-compatible
    credential_generation: 1
```

只使用环境变量时，不写 `credential_generation`：

```yaml
schema_version: 1
selected_provider: openai
provider_profiles:
  openai:
    model: gpt-image-2
    credential_source: environment-reference
    credential_ref: env:OPENAI_API_KEY
```

最小未配置文件为：

```yaml
schema_version: 1
provider_profiles: {}
```

此时状态必须是 `not_configured`，不能因为文件存在就返回 `ready`。

`Config_Status`、`Verification_State`、`Execution_Eligibility` 和 `Installation_Readiness` 都是由 `config.yaml`、Credential_Store、receipt 及当前宿主能力计算得到的结果，不作为可手工篡改的顶层字段写入 `config.yaml`。关键映射为：

| 条件 | Config_Status | Execution_Eligibility | Installation_Readiness |
| --- | --- | --- | --- |
| 本地配置完整，且当前 readiness scope 的全部 required capabilities 均有匹配基础 fingerprint 且未过期的 Capability_Evidence | `ready` | `allowed` | `ready` |
| 本地配置完整，但当前 readiness scope 的 required capabilities 未被有效 Capability_Evidence 完整覆盖 | `configured_unverified` | `allowed` | `usable_unverified` |
| 本地配置完整且当前 Provider 调用或恢复上下文为瞬时失败 | `degraded` | `retryable` | `installed_not_ready` |
| 配置缺失或无效 | `not_configured` / `invalid` | `blocked` | `installed_not_ready` |

纯本地 `config status` 不持久推断历史瞬时失败。没有当前失败上下文且当前 readiness scope 的能力证据不足时，它返回 `configured_unverified`；`degraded` 只属于当前 Provider 调用或仍在恢复的当前操作。

## 5. 字段说明

### 5.1 顶层字段

| 字段 | 类型 | 必填 | 约束与含义 |
| --- | --- | --- | --- |
| `schema_version` | integer | 是 | 首次发布固定为 `1`；更高版本返回 `config_schema_too_new` |
| `selected_provider` | string | 否 | 仅允许 `openai`、`openai-compatible`、`atlascloud`；未配置 Provider 时省略 |
| `max_concurrent_workers` | integer | 否 | `1..16`；缺省值由 runtime 按 CPU 计算，上限为 4 |
| `max_run_bytes` | integer | 否 | `1048576..107374182400`，单位为字节 |
| `timeouts` | object | 否 | runtime 超时和重试设置，只允许已定义子字段 |
| `provider_profiles` | object | 是 | External Provider 的非敏感档案；允许为空对象 |

`selected_provider` 必须指向 `provider_profiles` 中存在且可解释的档案，否则返回 `provider_selection_invalid`。多个 Provider 可用但缺少 `selected_provider` 时返回 `provider_selection_required`，不得随机选择。

### 5.2 `timeouts`

| 字段 | 类型 | 范围 | 默认值 |
| --- | --- | --- | --- |
| `worker_page_seconds` | integer | `1..86400` | `600` |
| `backend_api_seconds` | integer | `1..3600` | `60` |
| `backend_api_retries` | integer | `0..10` | `3` |

### 5.3 Provider 公共字段

| 字段 | 类型 | 必填 | 约束与含义 |
| --- | --- | --- | --- |
| `model` | string | 是 | trim 后不能为空 |
| `credential_source` | string | 是 | `environment-reference` 或 `os-store-reference` |
| `credential_ref` | string | 是 | 只允许与 Provider、平台和 source 匹配的非敏感引用 |
| `credential_generation` | integer | 条件必填 | OS 存储凭据从 1 开始的代次；每次成功覆盖后递增 |

允许的凭据引用为：

| Provider | 环境变量引用 | macOS Keychain 引用 | Windows DPAPI 引用 |
| --- | --- | --- | --- |
| OpenAI | `env:OPENAI_API_KEY` | `keychain:leo-ppt-generator/openai` | `host:dpapi/openai` |
| OpenAI-compatible | `env:OPENAI_COMPATIBLE_API_KEY` | `keychain:leo-ppt-generator/openai-compatible` | `host:dpapi/openai-compatible` |
| AtlasCloud | `env:ATLASCLOUD_API_KEY` | `keychain:leo-ppt-generator/atlascloud` | `host:dpapi/atlascloud` |

环境变量值不写入 YAML。为识别环境变量值轮换且避免每个进程重复付费 smoke，runtime 使用设备本地受保护的随机 Fingerprint_Key 计算 `HMAC-SHA256(Fingerprint_Key, provider || env-name || secret)`，只把结果作为 `credential_version` 写入 receipt。Fingerprint_Key 保存在 Keychain/DPAPI，HMAC 不写入 `config.yaml`、不在人类输出中展示。OS 存储凭据使用 `credential_generation` 参与 Verification_Fingerprint。

若 Config_File 保存 `environment-reference`，但当前进程中的目标变量缺失或为空，该 Provider 状态为 `not_configured`，Reason Code 为 `credential_environment_missing`，Execution Eligibility 为 `blocked`。这不是 schema `invalid`；其他兼容 Provider 仍可独立执行。默认 Primary Action 为 `run_cli / config repair`，用户可以让当前宿主获得该环境变量，或改用 Keychain/DPAPI。

### 5.4 OpenAI-compatible 专属字段

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `endpoint_origin` | string | 是 | 只允许 HTTPS origin，不得包含用户名、密码、查询串或片段；保存时移除末尾 `/` |

示例合法值：`https://images.example.com`

示例非法值：

- `http://images.example.com`
- `https://user:pass@images.example.com`
- `https://images.example.com?api_key=...`
- `https://images.example.com/#config`

## 6. 凭据实际存放位置

### 6.1 macOS

密钥保存在当前用户 Keychain 中，不对应 `LEO_PPT_HOME` 下的普通文件：

```text
service: leo-ppt-generator
account: openai | openai-compatible | atlascloud
```

`config.yaml` 只保存 `keychain:leo-ppt-generator/<provider>` 引用。

### 6.2 Windows

密钥使用当前 Windows 用户 DPAPI 加密后写入：

```text
<LEO_PPT_HOME>\credentials\openai.dpapi
<LEO_PPT_HOME>\credentials\openai-compatible.dpapi
<LEO_PPT_HOME>\credentials\atlascloud.dpapi
```

`credentials` 目录和 `.dpapi` 文件必须限制为当前用户 ACL。ACL 过宽、blob 无效或解密失败时配置状态为 `invalid`，不得降级读取明文文件。

### 6.3 环境变量 Fingerprint_Key

为使环境变量凭据的 receipt 能安全识别 Key 轮换，runtime 首次通过显式 smoke 或真实业务图片验证环境变量凭据时生成 256-bit 随机 Fingerprint_Key：

```text
macOS Keychain
  service: leo-ppt-generator
  account: verification-fingerprint-key

Windows DPAPI
  <LEO_PPT_HOME>\credentials\verification-fingerprint-key.dpapi
```

Fingerprint_Key 只用于 HMAC，不是 Provider API Key。若该 key 丢失、损坏或不可访问，已有环境变量 receipt 立即变为 `stale`，Config_Status 回到 `configured_unverified`，由显式 smoke 或下一张真实业务图片重新验证；不得退回保存 API Key 的裸 hash。

## 7. Verification_Receipt

每个 External Provider 使用独立回执，避免切换或修复一个 Provider 时覆盖其他 Provider 的有效验证结果：

```text
<LEO_PPT_HOME>/verification-receipts/openai.json
<LEO_PPT_HOME>/verification-receipts/openai-compatible.json
<LEO_PPT_HOME>/verification-receipts/atlascloud.json
```

回执目标格式示例（日期仅用于展示字段；v1 默认 TTL 为每项能力成功后的 7 天）：

```json
{
  "protocol": "leo-ppt-verification-receipt/v1",
  "schema_version": 1,
  "provider": "openai-compatible",
  "endpoint_origin": "https://images.example.com",
  "model": "gpt-image-2",
  "credential_ref": "keychain:leo-ppt-generator/openai-compatible",
  "credential_version": "generation:2",
  "runtime_identity": "leo-ppt-generator/1.0.0",
  "adapter_version": "openai-compatible/v1",
  "verification_policy_version": 1,
  "fingerprint_sha256": "<64-hex-base-fingerprint>",
  "capability_evidence": {
    "generate": {
      "verified_at": "2026-08-22T10:00:00Z",
      "expires_at": "2026-08-29T10:00:00Z",
      "operation_id": "<opaque-non-secret-id>",
      "verification_source": "provider_smoke",
      "artifact": {
        "sha256": "<64-hex>",
        "media_type": "image/png",
        "size_bytes": 12345
      }
    }
  }
}
```

Verification_Receipt 只保存成功证据；`capability_evidence` 的 key 仅允许 Registry 声明的能力。每项证据独立保存验证时间、过期时间、operation id、验证来源和产物摘要。新增或刷新一个能力时必须原子合并，不能删除仍匹配同一 Verification_Fingerprint 且未过期的其他能力证据。若基础 fingerprint 变化，则整份旧 receipt 失效，不得把旧能力证据合并到新身份。

`verification_source` 取值为 `provider_smoke` 或 `business_image`。v1 的 Provider_Smoke 只产生 `generate` 证据；`edit`、`mask` 和 `reference` 只能由实际执行对应能力的真实业务请求产生。JSON 状态中的 `verified_capabilities` 由当前未过期且匹配基础 fingerprint 的 `capability_evidence` key 派生，不作为第二套可漂移字段写入 receipt。

`operation_id` 不含用户材料和凭据，用于关联重试、任务恢复与 Capability_Evidence 持久化修复，且不能复用于另一项验证意图。回执不得包含鉴权 header、密钥、完整请求、完整响应、生成图片或用户 PPT 材料；`artifact` 只保存非敏感摘要。`provider_smoke` 的临时图片完成校验后删除；`business_image` 对应的图片由任务产物 owner 正常保留。

OS 存储凭据使用 `credential_version: generation:<n>`；环境变量凭据使用 `credential_version: hmac-sha256:<64-hex>`。两种形式都参与 Verification_Fingerprint，且不得在人类可读状态输出中展示完整 HMAC。

### 7.1 Verification Scope、Route 能力与 TTL

Verification_Fingerprint 只标识基础配置身份，至少包含：

```text
provider
+ endpoint_origin（适用时）
+ model
+ credential_version
+ adapter_version
+ verification_policy_version
```

它不得包含 `verified_capabilities` 或其他验证结果。Verification_Scope 使用该 fingerprint 与规范化后的目标能力集合构造。single-flight、operation 恢复和 Capability Evidence 合并均使用同一 scope 语义。

v1 的 Route 基础能力矩阵为：

| Route | 基础 `required_capabilities` |
| --- | --- |
| `generate` | `generate` |
| `direct-editable` | `edit` |
| `upgrade-full` | `edit` |
| `upgrade-selected` | `edit` |

实际业务请求使用 mask 时增加 `mask`，使用独立额外参考图时增加 `reference`。未指定 Route 时 Default Route 固定为 `generate`，并必须在状态输出中显示。该矩阵由 checked-in Route owner 维护，setup、Config Command 和业务执行器不得各自复制。

Provider Registry 中的 Verification Policy 拥有 TTL、Auth Probe、模型发现、幂等与重试策略。v1 默认 TTL 为每项能力成功后的 7 天；Registry 可以按 Provider 或能力显式覆盖，用户不能通过 `config.yaml` 延长 TTL 或把 `unknown` 覆盖为 `supported`。Verification Policy version 变化时基础 Verification_Fingerprint 随之变化，整份旧 receipt 失效；在同一 policy version 内，每项 Capability_Evidence 仍按各自 `expires_at` 独立过期。

静态 capability 只用于候选兼容性判断，不构成真实验证。一个 Route 的 `ready` 必须满足：

```text
required_capabilities(route, task) subset_of valid_capability_evidence(receipt)
```

### 7.2 Provider Registry 的 fail-closed 合同

Provider Registry 是 checked-in runtime source，由 registry loader 校验并由 setup、Config Command 和业务执行器共同消费。每项探测或执行策略必须显式声明 `supported`、`unsupported` 或 `unknown`；缺失字段等价于 `unknown`。

任意用户配置的 OpenAI-compatible endpoint 默认：

- 不自动运行 Auth Probe；
- 不自动查询模型列表；
- 不假定支持幂等键或幂等重放；
- 结果不确定时不自动重试；
- 不以静态 capability 声明返回 `ready`。

只有当前 adapter 与目标 endpoint 存在可复核的明确声明时，runtime 才能提升对应策略。Registry 的具体源码格式、模块划分和发布签名属于 Design，但其唯一 owner 与 fail-closed 行为属于公共合同。

### 7.3 惰性验证 single-flight

在同一 Verification Scope 尚无覆盖全部目标能力的有效证据时，runtime 最多允许一个可能计费的验证请求处于进行中。协调键至少覆盖 Verification_Fingerprint 与排序、去重后的目标能力集合。

并发页面必须等待同一在途结果：成功后共享原子合并后的 receipt 并放行；失败后共享同一 Reason Code 和恢复动作。等待者不得自行生成新的 operation id 或再次调用 Provider。具体采用进程锁、文件 lease 或 run operation 由 Design 决定。

## 8. 写入与更新规则

### 8.1 写入 owner

`leo-ppt config` 命令组是 `config.yaml` 与凭据引用关系的唯一推荐用户写入入口。Verification_Receipt 的文件级变更由共享 runtime Receipt Store 作为唯一 owner：Config_Command 与业务执行器都只能调用该 Store 的校验、失效和原子合并能力，不得各自直接实现第二套 receipt 写入逻辑。用户可以查看 YAML，但不应通过手工编辑完成密钥配置。

### 8.2 原子性

每次更新必须：

1. 读取并验证现有文件。
2. 在同一目录写入权限受限的临时文件。
3. 重新解析并验证临时文件。
4. 原子替换目标文件。
5. 写入失败时删除临时文件，保留旧文件不变。

Provider_Profile 写入并通过本地检查后即返回 `configured_unverified`，不要求自动 smoke。显式 smoke 失败时保留档案，但不写入本次操作对应的成功 Capability_Evidence。smoke 或真实业务图片成功而 Capability_Evidence 原子合并失败时仍不得返回当前 Route 的 `ready`：状态保持 `configured_unverified`；已生成的业务图片必须保留，修复动作只使用本地产物和恢复证据重试证据合并，不得再次调用 Provider。

覆盖 OS 存储凭据的事务顺序必须保证不存在“新 Key + 旧 receipt 仍为 ready”的窗口：先使旧 receipt 失效，失效失败则停止；再写 Credential_Store；最后递增 `credential_generation` 并原子更新 `config.yaml`。最后一步失败时 receipt 已失效，状态只能是 `configured_unverified` 或 `invalid`，由 `config repair` 续接。

任意步骤中断后，`config repair` 必须能从非敏感恢复证据确定当前 secret 与 `credential_generation` 的对应关系，不得猜测 generation、重复覆盖 secret 或恢复旧 receipt。具体采用 generation-specific reference、Credential Store 元数据或 pending operation 由 Design 决定；在恢复证据不存在或矛盾时必须 fail closed 为 `invalid`。

### 8.3 权限

即使 `config.yaml` 和 receipt 不含密钥，也应使用当前用户可写、其他普通用户不可写的权限：

- macOS/POSIX：目录 `0700`，文件 `0600`
- Windows：当前用户 ACL；禁止向 `Users` 或 `Everyone` 授予写权限

Credential Store adapter 不得将明文密钥放入当前进程或子进程 argv、命令回显或普通临时文件。调用平台工具时必须使用不暴露 secret 的平台 API、受保护输入通道或等价机制；无法满足时返回稳定失败，不得降级到 argv。

### 8.4 禁止字段

任何未知字段名包含 `token`、`secret`、`password` 或 `key`，或任何字段值疑似包含明文凭据时，读取器必须返回 `unknown_sensitive_field`，且错误输出不得回显字段值。

以下内容禁止出现在 `config.yaml`：

```yaml
api_key: sk-example
password: example
token: example
authorization_header: Bearer example
```

## 9. 配置优先级

配置解析按以下优先级执行：

1. 进程环境变量：`LEO_PPT_HOME`、Provider 凭据变量、`LEO_PPT_MAX_WORKERS`
2. `<LEO_PPT_HOME>/config.yaml`
3. runtime 默认值

环境变量只覆盖它明确拥有的字段，不得替换整个 Provider_Profile。例如 `OPENAI_COMPATIBLE_API_KEY` 可以提供凭据，但不能补齐缺失的 `endpoint_origin` 或 `model`。

## 10. 开发期配置替换策略

项目尚未对外发布，当前本地开发配置不属于用户数据兼容范围。首次运行目标版 `leo-ppt config status` 时按以下规则处理：

```text
读取 config.yaml
        |
        +-- 符合本文件定义的完整 schema v1
        |      -> 正常执行 Local_Configuration_Check
        |
        +-- 属于旧的开发期字段集合或无法完整解释
               -> development_config_reset_required
               -> 不猜测字段映射，不执行自动迁移
               -> 用户运行 config repair 并确认重建
               -> 原子写入目标 schema v1
```

重建只处理非敏感 Config_File，不复制、打印或擅自删除 Credential_Store 中的密钥。能按 Provider 明确识别的现有 OS 凭据可由新向导重新引用；无法确认归属的凭据保持不变，用户通过统一向导显式覆盖或删除。项目不维护开发期字段到正式字段的迁移代码，首次发布前的测试 fixture 直接更新为目标 schema v1。

## 11. 用户查看与诊断

普通用户优先使用只读命令：

```text
leo-ppt config status
leo-ppt config status --json
```

状态输出可以显示配置文件绝对路径、schema 版本、字段来源、Credential_Reference 和 receipt 路径，但不得读取或展示密钥。无参数 `config status` 必须使用 Default_Route `generate`，并在 `readiness_scope.route` 中明确输出；直接打开文件只适合排查非敏感档案，修复应回到 `leo-ppt config repair`。

## 12. 验证清单

实现阶段必须逐项验证：

- macOS 默认路径、Windows 默认路径和自定义 `LEO_PPT_HOME` 均解析正确。
- schema v1 最小文件、三个 Provider 示例和各边界值均通过 schema 校验。
- 旧开发期配置返回 `development_config_reset_required`，不进入自动迁移分支。
- `config repair` 经用户确认后能原子重建目标 schema v1，重建失败不改变旧文件字节。
- `config.yaml`、receipt、stdout、stderr、日志、当前进程与子进程 argv 中均无密钥明文，Credential Store adapter 不使用普通临时文件传递 secret。
- Keychain 引用、DPAPI 引用和环境变量引用不能跨 Provider 混用。
- Config_File 保存的环境变量引用在当前进程缺失或为空时返回 `credential_environment_missing`、`not_configured` 和 `blocked`，不误报为 schema invalid，也不阻断其他兼容 Provider。
- 覆盖 OS 存储凭据后 `credential_generation` 递增，旧 receipt 变为 stale。
- 环境变量值不变时 receipt 可跨进程复用；值或 Fingerprint_Key 变化时整份 receipt 失效。
- receipt 不包含裸 API Key hash，环境变量 `credential_version` 只能由受保护 Fingerprint_Key 生成。
- endpoint、model、credential version、runtime adapter 或验证策略变化后整份 receipt 失效；新增能力证据不会改变 Verification_Fingerprint。
- 每项 Capability Evidence 独立记录 verified_at、expires_at、operation id、source 和 artifact digest，并按当前策略独立过期。
- 新增或刷新一个能力时原子保留同 fingerprint 下其他仍有效能力证据；不得仅合并 `verified_capabilities` 数组而丢失逐能力来源。
- 当前 readiness scope 缺少、过期、损坏或写入失败的能力证据均不能返回该 Route 的 `ready`。
- Provider Registry 缺失的 Auth Probe、模型发现、幂等和重试声明均按 `unknown` fail closed；用户配置不能覆盖安全策略。
- 本地配置完整但 required capabilities 未被有效证据完整覆盖时返回 `configured_unverified`、`allowed` 和 `usable_unverified`，不得阻断首张业务图片。
- 未指定 Route 时固定使用 `generate` 并输出该 readiness scope；Route 基础矩阵与任务级 mask/reference 附加规则来自唯一 checked-in owner。
- 配置向导未收到用户对可能计费 smoke 的明确肯定同意时，不产生 Provider 图片请求；提示默认值为“否”，默认回车、超时、取消、安装器、更新器和 Agent 宿主均不能视为或代替同意。
- `Auth_Probe` 只在 registry 明确声明无费用且无实质副作用时自动运行，成功后仍保持 `configured_unverified`。
- v1 Provider Smoke 只生成 `generate` Capability Evidence；不会声称验证 `edit`、`mask` 或 `reference`。
- 首张真实业务图片成功后保留图片，为实际执行能力原子合并 `verification_source: business_image` 证据，并仅在覆盖当前 Route 后升级为 `ready`。
- 同一 Verification Scope 的多页并发只产生一个在途验证请求，等待页面共享成功或失败结果。
- `generate` 证据不会使缺少 `edit`、`mask` 或 `reference` 证据的目标 Route 返回 `ready`。
- 首张真实业务图片失败时保留任务上下文和全部有效中间产物，修复后从图片节点恢复。
- 真实业务图片成功但 Capability Evidence 合并失败时保留图片与 `configured_unverified`，只重试本地证据合并且不重复调用 Provider。
- 显式 smoke 与惰性验证在重试和中断恢复时复用稳定 operation id；Provider 支持幂等时复用相同幂等键，Capability_Evidence 持久化修复永不调用 Provider。
- Provider registry 未明确声明幂等支持且调用结果不确定时不自动重试，返回 `provider_outcome_unknown`；用户确认新调用后使用新的 operation id。
- 凭据覆盖在任意事务步骤中断后，`config repair` 能确定 secret/generation 对应关系；证据矛盾时 fail closed。
- 一个 Provider 损坏不影响另一个 ready Provider 执行兼容 Route。
