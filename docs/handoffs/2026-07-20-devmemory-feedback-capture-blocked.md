# Phase 10 route B：真实 Capture 已保存，Insight 阻塞

日期：2026-07-20

## 已完成的真实步骤

- 在稳定、已认证的本地 Memos Chrome 会话中创建并保存了一条新的非敏感测试 Bug Report；列表与详情均可见。
- 详情页已显示现有的 Context Pack 入口和当前 Memo 的显式来源选择。没有生成、复制或保存任何 Context Pack 输出。
- 状态变化前后的 `python -m scripts.devmemory_lifecycle_report` 均只返回 AI 自有 SQLite 聚合：`memo_insights=0`，且 webhook event aggregate 仍为一个 `processed`。报告不包含 Memo ID、原文、payload、secret 或 chunk。
- 定向回归 `tests/test_memo_insights.py`、Context Pack builder/golden 和 lifecycle report：`15 passed`。Compose 中仅低 CPU 的 Memos 与 AI Service 处于运行状态。

## 阻塞与未验证项

新 Capture 后没有可见或持久化的 Insight，因此按照 route-B stop condition 停止：没有创建 SQLite 记录、绕过 Memos 登录或制造 review 状态。

下列项目均**未验证**：一次 accept/reject、accepted-only Context Pack、预算截断、Markdown/JSON copy、复制后的 UI 稳定性、删除/撤销联动，以及四项人工反馈。历史 Phase 9f 剪贴板验收不能替代这些本轮反馈证据。

## 后续边界

这是真实 Capture evidence，不是 DevMemory Loop pass，也不是 gateway rollout 证据。保持 `AI_PUBLIC_CHUNK_RETRIEVAL=false`，不改 public chat、Memos 核心、collection 或 volume。下一步若继续 route B，应先以低 CPU、只读方式确认常规产品集成是否能让已保存的测试 Memo 产生 Insight；无此条件不得新增第二条测试 Memo 或伪造数据。
