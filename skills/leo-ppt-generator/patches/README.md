# 上游补丁目录

固定上游当前应用六个可由 `git apply --check` 复核的受控补丁：

- `0001-codex-state-directory-barrier.patch`：状态文件替换后同步父目录，聚焦回归为
  `tests/boundary/test_vendor_state.py`。
- `0002-editable-state-atomic-lock.patch`：editable 状态写入原子化并增加并发锁，聚焦
  回归为 `tests/boundary/test_vendor_state.py`。
- `0003-codex-assembly-fidelity.patch`：图片组装默认无损并以 `contain` 保持比例，同时
  保留显式 `crop/stretch`，聚焦回归为
  `test_image_deck_assembly_preserves_source_ratio_by_default`。
- `0004-editable-expected-formula-inventory.patch`：拒绝已确认公式在 worker 输出中静默
  遗漏，聚焦回归为 `test_confirmed_source_formula_inventory_cannot_be_omitted`。
- `0005-codex-chroma-key-dependency-hint.patch`：保证 Pillow 缺失时返回适用于当前
  受管 runtime 的可执行恢复提示，不再引用旧 codex-ppt bootstrap 路径；聚焦回归为
  `test_chroma_key_dependency_hint_is_available`。
- `0006-editable-ppt-dpi-parameter.patch`：`.ppt` 经 Office 转 PDF 后使用
  `normalize_inputs(..., dpi=...)` 的函数参数，聚焦回归为
  `test_legacy_ppt_normalization_forwards_requested_dpi`。

Office 输入信任边界属于当前项目 adapter/route 增强，单独记录为
`assembly-and-office-boundaries.md`，不伪装成 upstream patch。每个补丁必须同时登记到
`../upstreams.yaml`，由 `test_registered_vendor_patches_apply_to_pinned_source_worktrees`
自动枚举并重放检查；相应行为 proof 由上述聚焦测试与
`tests/upstream/core-tests.yaml` 共同约束。

禁止直接修改 vendor 副本后不生成补丁文件。
