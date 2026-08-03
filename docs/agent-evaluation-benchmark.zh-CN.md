# Agent Evaluation Synthetic Baseline

## 方法

R6-I5 将 `agent-evaluation-corpus-v1` 的 64 个 case 实际送入 in-memory `RetrievalService` 与
`EvidenceAnswerAgent` core。每个 case 使用全新的 deterministic embedding store，只写入该 case 已 allowlist 的生成式
synthetic record，ID 直接来自 corpus。Provider 使用 deterministic 实现，因此不调用 network、真实 Memo/身份/凭据、
prompt dump、Qdrant、Docker 或外部模型。

harness 只产生 `agent-evaluation-result-v1`，再由预声明 `agent-evaluation-thresholds-v1` 评分。测试使用 fixed-step clock
保证 report 可复现；latency 值只证明 contract，不证明 runtime performance。delegation/authentication 与 durable storage
不属于该 core-only baseline，继续由各自测试证明。

## 结果

R6-I5C 后，baseline 执行 64 个 case，无 failed case：

| Metric | Value | Gate |
| --- | ---: | --- |
| Retrieval Recall@5 | 1.0 | pass |
| Retrieval MRR | 1.0 | pass |
| Citation precision | 1.0 | pass |
| Groundedness | 1.0 | pass |
| Refusal accuracy | 1.0 | pass |
| Scope leak count | 0 | pass |
| Synthetic fixed-step p95 latency | 1 ms | pass |

fixed pre-retrieval policy 在不调用 retrieval/Provider 的情况下拒绝全部八个 protected-intent case。content-free report
没有 failed case 或 failed threshold；regression tests 保持普通 retrieval、citation、visibility、no-context 与 error
behavior。

## 限制

这只是 sanitized offline product-core baseline，不证明真实模型质量、Provider latency/cost、Qdrant ranking、lifecycle
convergence、Docker、认证浏览器、restart recovery、clean-checkout CI 或 release；这些主张需要各自授权与证据。
