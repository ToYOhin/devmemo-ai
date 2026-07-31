# Evidence Answer Agent

> 状态：A1 local-first 只读后端已实现并完成本地运行时验证。它默认关闭；尚未交付 Web UI、Agent 持久化、远程部署或通用公开可用性。

## 目标

DevMemo AI 增加一条小型、可检查的 Agent 链路：它接收开发问题，先通过一个受限工具检索已索引 Memo 中的证据，再生成带引用的回答。执行轨迹说明控制流，但不暴露 Memo 原文。

该设计刻意小于通用自主 Agent，以保持项目 local-first、可审阅和低资源的默认取向。

## 已实现的 A1 边界

- Memos 认证后的 BFF `POST /api/ai/agent/answer` 只接受问题与受限 `limit`；浏览器不能提交身份、可见 Memo UID、工具名、prompt 覆盖或 Memo 内容。
- Memos 使用既有权限规则解析调用者可见的完整 Memo，再使用短时 HMAC 将 UID 能力委托给固定的 AI Service 内部路径。
- AI Service 必须先验签，才会过滤 `memo-v1` 检索结果和组装内部上下文。唯一工具是 `search_memos`；安全响应只允许 answer、citation、受控元数据与脱敏 trace。
- 只有显式的本地 `docker-compose.agent.yml` 覆盖层可以启用该功能；它不发布 AI Service 的宿主机端口。默认 Compose 路径仍保持 Agent 关闭。

定向 Go/AI 测试、Compose 校验、隔离健康检查和认证 BFF 本地验证已通过。认证验证只返回调用者可见的 citation 与两步脱敏 trace；一条已知不可见 Memo 在组装上下文前被排除。这是本机运行时证据，不是多实例或公网部署声明。

## 范围

首个版本 `evidence-answer-agent-v1` 只有一个只读工具：`search_memos(question, limit)`。

```text
question
  -> EvidenceAnswerAgent
  -> search_memos
  -> RetrievalService（完整 Memo 索引）
  -> 受限内部上下文与安全 citation
  -> 已配置 LLM provider 或 deterministic finalizer
  -> answer、citations 与脱敏 trace
```

工具调用既有 `RetrievalService`，不是 mock 或独立数据存储。该 Agent 不改变 `POST /api/ai/chat` 的行为或契约。

## 边界

- Memos 仍是 Memo、身份和权限的事实源。
- AI Service 仍只是 AI 派生状态 sidecar；Agent 不保存会话或执行轨迹。
- 只使用完整 Memo 的 `memo-v1` 检索；不使用 public chunk retrieval、chunk content 或新的 Qdrant 路径。
- 默认关闭：`AI_AGENT_ENABLED=false`。
- 不改变安全默认值：deterministic provider、memory vector store、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo` 与 `AI_PUBLIC_CHUNK_RETRIEVAL=false`。
- 没有写工具、后台 worker、递归循环、MCP、浏览器访问、队列或 Agent framework 依赖。
- HTTP 响应和 trace 不得暴露 raw Memo content、Webhook payload、embedding、prompt、secret 或 chunk content。

## 已实现的 BFF 契约

以下接口仅在显式本地 Agent 模式中启用。浏览器只访问 Memos；AI Service 对应的接口是内部接口，只接受已签名的委托请求。

```http
POST /api/ai/agent/answer
```

```json
{
  "question": "Docker 端口映射为什么失败？",
  "limit": 5
}
```

`question` 必填；`limit` 限制为 1–10，并传给唯一检索工具。接口不接受任意工具名、URL、prompt 覆盖、Memo 原文或会话历史。

```json
{
  "answer": "Compose 配置已修复端口映射问题 [1]。",
  "citations": [
    {
      "memo_id": "memo-42",
      "embedding_id": "memo-42",
      "score": 0.9,
      "metadata": {"title": "Docker ports"}
    }
  ],
  "provider": "deterministic",
  "retrieved_count": 1,
  "agent_version": "evidence-answer-agent-v1",
  "trace": {
    "terminal_state": "answered",
    "steps": [
      {"index": 1, "kind": "tool", "name": "search_memos", "status": "completed", "result_count": 1},
      {"index": 2, "kind": "final", "name": "answer_from_evidence", "status": "completed"}
    ]
  }
}
```

trace 只包含序号、动作名称、状态和结果数。空索引检索后以 `no_context` 结束，且不得调用 LLM provider。

## 交付状态

1. **契约与 feature gate — 已完成。** 严格 `AI_AGENT_ENABLED` 解析与 provider-neutral domain type 已有序列化测试。
2. **只读证据 Agent 与认证 BFF — 已完成。** `EvidenceAnswerAgent`、签名内部路由、Memos BFF、可见性过滤与定向集成测试已实现。
3. **显式实验 UI — 未开始。** 只有在再次获得明确授权后，才增加清晰标记、opt-in 的 Memo 详情页入口；它只显示安全 citation 与步骤状态，不显示内部上下文。
4. **受控 provider smoke — 未开始。** 可选地用维护者本地配置的 provider 验证同一路径；这不是默认 Compose 或 CI 要求。

## A1 验收结果

- Agent 默认关闭，且关闭时没有 Agent 行为。
- 完整 Memo 索引上的定向测试证明执行了一次 `search_memos`，并返回带引用的 deterministic answer。
- 空检索不调用 provider；检索与 provider 失败分别映射为安全的 503 与 502。
- citation 与 trace 不包含 `content`；Memos BFF 严格拒绝未知或不安全的内部响应字段。
- 既有 chat 契约未修改，相关测试通过。

## 后续工作不包含在 A1 内

任何写工具都需要独立评审认证与 visibility mapping、显式用户确认、幂等、审计与回滚、限流及威胁建模。只读 Agent 不隐含这些能力。
