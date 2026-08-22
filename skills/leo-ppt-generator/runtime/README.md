# leo-ppt-generator runtime

此目录是 `leo-ppt-generator` Skill 随包分发的确定性 Python runtime。用户应通过
`scripts/runtime_manager.py` 安装和选择不可变 runtime，不直接从 PATH 猜测 CLI。

发布构建必须同时通过：

- `python -m build`；
- wheel inventory 不含 `__pycache__`、`.pyc` 或旧 Skill 入口；
- `scripts/sync_upstreams.py --check`；
- 干净 runtime 的 `ensure → doctor → print-cli`。
