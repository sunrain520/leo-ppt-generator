# 上游聚焦回归

`core-tests.yaml` 记录 U0 对固定 clean export 实际运行的核心检查。尖括号参数是
由 U0 harness 注入的临时路径，不是可复制的本机固定路径。

上游源码进入 `_vendor/` 后，这些检查必须改为从正式 bundle 与发布 lock 运行；
不得把本清单本身当作测试通过证据。

