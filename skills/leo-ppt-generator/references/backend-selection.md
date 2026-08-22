# Backend 选择

分别声明 backend 的 `generate`、`edit`、`mask` 和 `reference image`
capability。任务需要的 capability 缺失时，在派发前返回
`blocked/backend_capability_missing`。

setup 的候选必须来自同一个 backend registry。只有宿主明确声明 available，才能
选择 `builtin-imagegen`；宿主声明 unavailable 时，候选中不得出现该 backend；
unknown 必须先确认宿主能力，不能推测为可用。外部 Provider 先按当前任务需要的
capability 过滤，再按凭据状态和用户既有确认排序。需要 mask 时不得推荐不具备 mask
能力的 AtlasCloud。

OpenAI 与 AtlasCloud 是图片 Provider 的选择关系；OCR 不参与图片 Provider 选择。
普通图片式生成不披露 PaddleOCR。只有 editable 阶段明确需要文字 hints 时，setup
才把 PaddleOCR 作为非必需在线增强列出；凭据缺失时使用本地 `builtin-ink`，不得阻断
图片 Provider 确认或普通生成。

优先使用当前宿主可调用的内置图片工具；只有工具不可用、调用错误、输入不可读或
没有有效本地输出时，才按已确认的 run-level fallback contract 使用 CLI/API。
缺少可选参数不是自动 fallback 理由。

确认 backend 时记录：

- backend id、model 与 capability；
- credential reference 类型，不记录 secret value；
- task-local 图片、prompt、mask、reference 的允许发送范围；
- retry/timeout/rate-limit；
- output path、hash 与 provider receipt。

样张确认后保持 backend 和 generation method 不变。域名字符串不能推断 provider
类型；provider 必须来自显式 registry entry。

Backend contract v1 示例：

普通流程不要手写下面的 JSON。用户确认 provider 与 mode 后执行：

```bash
"$LEO_PPT" backend create --provider openai --mode generate --output ./backend.json
"$LEO_PPT" backend validate ./backend.json
```

`create` 从当前静态 registry 生成 capability、execution owner 和允许的 credential
reference，并立刻用同一 loader 自校验。`validate` 的合同通过与
`credential_reference_status` 分层报告；两者都不替代真实 provider smoke。

生成结果示例：

```json
{
  "schema_version": 1,
  "backend_kind": "openai-compatible",
  "provider": "openai",
  "model": "gpt-image-2",
  "mode": "generate",
  "credential_source": "environment-reference",
  "credential_ref": "env:OPENAI_API_KEY",
  "selection_source": "user-confirmed",
  "capabilities": {
    "generate": true,
    "edit": true,
    "mask": true,
    "max_reference_images": 16,
    "execution_owner": "runtime"
  }
}
```

`credential_ref` 只允许 `env:`、`host:` 或 `keychain:` 引用。原始 key/token、旧
`editppt config` 文件和宿主私有认证文件都不是合法来源。
