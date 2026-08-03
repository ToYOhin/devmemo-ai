# R5 验收记录

R5 已在明确限定、默认关闭的单机范围内完成。lifecycle dispatcher、rebuild generation
activation、durable retrieval 与同源 Agent 路径已实现，并通过一次性 Docker、Qdrant、SQLite
Memos 和认证 headed-browser 验收。这不是对真实数据、多实例、跨主机或外部 Provider 的声明。

## 证据矩阵

| 要求 | 状态 | 直接证据与限制 |
| --- | --- | --- |
| 未授权 context 与 citation 保持为零 | 已验证（运行时与测试） | 两个临时用户证明：自有 private Memo 可被引用；另一用户的 private Memo 返回 404 且不进入 citation；另一用户的 public Memo 可见并可被引用。既有 Go/Python 测试继续覆盖同一可见性矩阵。 |
| 支持的 Agent 浏览器路径只使用同源 Memos BFF | 已验证（运行时、源码与测试） | headed browser 的网络证据显示 `POST /api/ai/agent/answer` 返回 200 安全投影。Agent overlay 只发布 Memos 5230；AI Service 与 Qdrant 仅容器内可达。旧直连 AI 面板继续 fail closed，不属于受支持的 Agent 路径。 |
| 浏览器 Agent response 只包含受控投影 | 已验证（运行时与测试） | 认证 response 只包含 answer state、有界 citation 字段与 execution trace，不包含 raw Memo 正文、authority capability、vector metadata、Provider 设置、secret 或内部 transport 数据。 |
| memory 与 durable retrieval 在文档容差内等价 | 已验证（synthetic 与运行时） | 产品测试证明 answer state、retrieved count、Memo UID 集合与 `memo-v1` citation version 等价；运行时 durable answer 只返回当前授权 Memo citation。adapter-specific embedding ID、score、title、tag 继续明确排除。 |
| durable failure 不 fallback 到 legacy/raw-content retrieval | 已验证（测试与运行时回滚） | ownership 缺失与 durable failure 继续安全返回 503，且不回退。关闭 rehydration 但保留 lifecycle Qdrant point 也会安全失败；恢复默认 memory store 后返回 200 no-context 与零 citation。 |
| lifecycle dispatch 与 rebuild activation 可运行 | 已验证（运行时与测试） | 默认关闭的 Memos mutation hook 向现有 AI listener 交付认证 create/update/delete event。启动阶段准备权威 SQLite outbox、重放当前 synthetic Memo，并以 204 激活配置 generation。 |
| update/delete 收敛且没有 stale retrieval | 已验证（运行时与测试） | update 推进 lifecycle sequence，并替换当前 generation 的无正文 document hash。delete 形成 applied tombstone、删除目标所有 generation point，之后的 answer 没有再次出现已删除 Memo。 |
| restart reconciliation 可运行 | 已验证（运行时） | 串行重启 Qdrant、AI Service 与 Memos 后，Memos 重放权威 lifecycle state，activation 返回 204；已删除 point 未复活，当前 point 保留，认证 BFF answer 仍返回 200。 |
| disabled/default 与 rollback 保持安全 | 已验证（运行时、源码与测试） | rehydration 与 lifecycle 仍默认 false。运行时 rollback 将两者关闭并恢复 `AI_VECTOR_STORE=memory`；同一认证浏览器得到零 citation 的 no-context 200，同时 Memos 源数据不变。需要完全关闭时仍可设置 `AI_AGENT_ENABLED=false`。 |
| disposable cleanup 精确 | 已验证（运行时） | 两个具名 disposable Compose project 的精确 container、network 与四个 project volume 均已删除；临时账号、Memo、secret、Qdrant 数据、浏览器状态、build context、生成前端资产与验收 image tag 均已清理。没有 push、tag 或 release。 |
| 真实数据与多实例 opt-in 可安全执行 | 未验证且不在 R5 范围 | 真实用户数据、MySQL/PostgreSQL、backup/restore 执行、外部 Provider、shared atomic replay/capability state、跨主机加密和多实例仍需单独设计与授权。 |

## 已通过的本地门禁

- Python R5/A4/R4 定向回归：417 passed，保留一个既有 TestClient deprecation warning。
- 相关 Go Agent/BFF/SQLite tests 与 `go vet` 通过。
- Web suite：153 tests passed；Evidence Answer API/component 测试继续断言同源 BFF 与用户操作后才请求。
- Agent/Qdrant profiles 的 Docker Compose 静态配置通过；运行时只暴露 Memos 5230。
- Python compile sanity、格式化、diff、source-wiring、credential/local-path 扫描通过。

## 安全回滚

1. 设置 `AI_AGENT_LIFECYCLE_ENABLED=false` 与
   `AI_AGENT_REHYDRATION_ENABLED=false`。
2. 恢复 `AI_VECTOR_STORE=memory`，或设置 `AI_AGENT_ENABLED=false` 完全关闭 Agent。不得让
   legacy memory path 继续指向仅含 lifecycle metadata 的 Qdrant point，再把安全 503 描述成 parity。
3. 重启单机 stack，并通过 Memos BFF 验证 no-context 或预期 disabled response。
4. 保持 Memos 及其源数据库不变。
5. 只在备份验证后删除预先确定的可重建 AI ledger/vector state；不得删除宽泛或未解析的 volume/path。
6. 只有 clean rebuild 并与 Memos 对账后才能重新启用。

## 完成边界

R5 证明的是本地单机、默认关闭的 Agent 架构：Memos 拥有授权与 lifecycle 权威，Qdrant 只是可重建
derived state，并具备 deterministic disposable runtime 验收、安全回滚与精确清理。下一阶段可以进入 R6，
但不得把本记录解释为真实数据、外部 Provider、公开 AI 端口、多实例部署或跨主机明文 transport 的授权。
