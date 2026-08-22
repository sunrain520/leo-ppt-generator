# 组装与 Office 输入边界

这不是对固定上游源码的 patch，而是当前项目 adapter/route 层拥有的增强：

- `leo_ppt_generator.image_deck.adapter` 在上游 finalizer 前拒绝缺页、漂移和
  未完成状态；
- `leo_ppt_generator.application.routes` 与 `upstream_bridge` 在进入 editable
  解析器前拒绝未确认或含 active/external 内容的 Office 输入。

聚焦回归：`tests/unit/test_adapters.py`、`tests/unit/test_routes.py`、
`tests/integration/test_upstream_bridge.py`。
