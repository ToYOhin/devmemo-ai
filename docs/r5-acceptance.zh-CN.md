# R5 验收记录

R5 代码路径与 disposable synthetic 产品证明已经完成。真实单机运行时验收尚未完成：lifecycle dispatch 与
rebuild generation activation 尚未接线，Docker、认证浏览器、真实 Qdrant/Memos、重启和真实数据操作均需单独
授权。

## 证据矩阵

| 要求 | 状态 | 直接证据与限制 |
| --- | --- | --- |
| 未授权 context 与 citation 均为零 | 已验证（synthetic） | Go BFF/current-authority 测试覆盖调用者自有 private、其他用户 public 与其他用户 private Memo；Python durable retrieval 测试在 materialization 前求交 visibility，并拒绝泄漏 candidate。不主张真实多用户浏览器验证。 |
| 支持的 Agent 浏览器路径只访问同源 Memos BFF | 已验证（源码与组件测试） | Web 只向 `/api/ai/agent/answer` 发起 Agent 请求；Agent Compose overlay 清除 AI Service host port；未设置独立 `VITE_AI_SERVICE_URL` opt-in 时旧面板隐藏。Web 测试通过，但本切片未运行 headed browser。 |
| memory 与 durable retrieval 在文档容差内等价 | 已验证（synthetic） | disposable 产品测试证明 answer state、retrieved count、Memo UID 集合与 `memo-v1` citation version 相同。adapter-specific embedding ID、score、title、tag 被明确排除，因为 durable citation 不信任 vector/rehydration metadata。 |
| durable failure 不 fallback 到 legacy/raw-content retrieval | 已验证（synthetic） | Agent 与 internal route 测试证明 ownership 缺失及 durable failure 均返回既有安全 503，不调用 memory 或 Provider；空 evidence 保持 no-context。 |
| disabled/default 与 rollback 保持安全 | 已验证（源码与测试） | rehydration 默认关闭；disabled lifespan 不构造 durable 对象，endpoint 忽略 durable state，memory retrieval 继续被选择。rollback 为关闭 rehydration/Agent 并保留 Memos；尚未执行真实运行时 rollback。 |
| lifecycle dispatch、rebuild activation 与 restart reconciliation 可运行 | 当前源码反证 | `MemoLifecycleProcessor` 与 generation activation 只在测试中使用；没有生产 dispatcher 或 rebuild activation 入口。新启用的真实 runtime 尚无已评审的 derived generation 填充和激活路径。 |
| 真实 Qdrant/Memos 与认证浏览器行为已证明 | 受授权阻断 | 当前工作禁止 Docker、网络、Qdrant、账号、Memo、volume、secret 与浏览器操作；synthetic test 不能替代这些证据。 |
| 可以安全执行真实数据 opt-in | 未验证 | 真实数据运行必须另行授权，并先验证备份、dry run、精确 rollback target 与运行后对账；本阶段均未执行。 |

## 已通过的本地门禁

- Python R5/A4/R4 定向回归：404 passed，只有一条既有 TestClient 弃用警告。
- Go Agent/BFF/SQLite 相关 package：定向测试与 `go vet` 通过。
- Web suite：153 tests passed；Evidence Answer API/component 测试断言同源 BFF 路径与用户操作后才发请求。
- Python compile sanity、diff check、credential/local-path/source-wiring 扫描通过。

这些检查只证明代码与 synthetic integration 行为，不证明容器拓扑、浏览器认证、真实持久化或重启收敛。

## 安全回滚

1. 设置 `AI_AGENT_REHYDRATION_ENABLED=false` 并重启 disposable stack。
2. 如需关闭完整 Agent path，同时设置 `AI_AGENT_ENABLED=false`。
3. 保持 Memos 及其源数据库不变。
4. 只在备份验证后删除预先确定的可重建 AI ledger/vector state；不得删除宽泛或未解析的 volume/path。
5. 只有完成 clean rebuild 并与 Memos 对账后才重新启用。

## 真实运行时验收所需授权

授权必须明确覆盖 disposable Compose topology、临时 credential/secret、临时账号、synthetic Memo/visibility、临时
volume、本地 Qdrant、浏览器自动化、重启和清理。除非另有 Provider 授权，否则使用 deterministic Provider。

获授权的运行必须证明：

1. 浏览器登录后只调用同源 Memos BFF；
2. 自有 private Memo 与其他用户 public Memo 可以被引用，其他用户 private Memo 永不进入 context/citation；
3. 一次回答返回受控 citation，browser state 中没有 raw content；
4. update/delete 收敛且无 stale retrieval；
5. restart 后派生状态保持或安全重建；
6. 关闭 rehydration 后回到 memory/disabled path；
7. cleanup 只删除 disposable derived resources，并保留 Memos。

在 lifecycle activation 接线且上述授权运行通过之前，准确状态是：**R5 代码与 synthetic 产品路径完成；真实运行时
验收受 lifecycle wiring 缺失和运行时授权阻断。**
