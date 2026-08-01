# Evidence Answer Agent

> 状态：A1 local-first 只读后端已实现并完成本地运行时验证。A2 新增了显式的实验性 Web 入口，A3 已完成受控本地 Provider smoke，A4 现已定义本地 RAG 生命周期契约，A4-I1 已实现纯事件、确认与状态机规则，A4-I2 已增加仅 SQLite 的 dormant 源端 outbox adapter 与临时数据库事务证明，A4-I3 已增加 dormant AI 派生 ledger adapter 与 fake vector 崩溃恢复证明，A4-I4 已增加不含 route/dispatcher 的认证 lifecycle transport 契约，A4-I5 已增加覆盖重启、重试、tombstone、对账和 rebuild generation 的合成一次性 outbox-to-ledger 集成证明，R4-I1 已增加严格 provider-neutral grounded-answer 结果契约，R4-I2 已用合成证据和 fake Provider 将其安全接入非 deterministic 回答路径；功能仍默认关闭。尚未交付运行时生命周期接线、自动索引、远程部署或通用公开可用性。

交付顺序、当前缺口、验收门槛与可写入简历的完成定义维护在
[DevMemo Agent 开发路线](agent-development-roadmap.zh-CN.md) 中。本文档仍是安全与
数据流契约的权威，开发路线不得放宽这些契约。

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
3. **显式实验 UI — 已完成。** Memo 详情页入口有清晰标记，用户展开入口并提交问题前不会发出请求。它仅以 `question` 和 `limit` 调用同源 Memos BFF，然后严格解析并显示安全 answer、citation 与脱敏步骤状态；不直连 AI Service，也不持久化结果。
4. **受控 provider smoke — 已完成。** 一次可销毁的仅本地运行时验证了既有签名内部路径与显式 opt-in Provider，包括成功的证据回答、空上下文时跳过 Provider，以及安全的 502 Provider 失败映射。该验证没有发布 AI 宿主机端口、没有写入持久数据，也没有更改默认 Compose 配置。
5. **本地 RAG 生命周期契约 — 设计已完成。** 下文的 Memos-owned 事件、重试、幂等、重建、可观测性与回滚规则是后续实现的评审基线。本设计切片不授权运行时接线或持久化任何真实 Memo 派生数据。
6. **纯生命周期契约 — 已完成。** Provider-neutral 事件与确认类型、不可变重放校验、序号/幂等决策、tombstone 和 fail-closed 检索资格已有共享 fixture 与纯单元测试。没有增加 route、数据库、transport、vector adapter、Compose 改动或真实数据。
7. **Memos-owned outbox 事务证明 — SQLite 已完成。** Dormant schema 和显式 adapter 由 Memos 分配源序号，并把合成 create/update/archive/delete 变更与 index/reindex/delete 事件原子配对。临时数据库测试覆盖提交、回滚、tombstone、共享 fixture、增量 migration 和三次 attempt 上限。现有 Memo CRUD 不调用该 adapter；没有启用 transport 或自动索引，也未实现 MySQL/PostgreSQL adapter。
8. **AI 派生 ledger 恢复证明 — 已完成、未接线。** 独立构造的 SQLite adapter 只持久化 event identity、fingerprint、序号、operation/hash、tombstone、状态、有界错误码和 last-applied 元数据。fake vector processor 测试边界证明了 vector 变更前 reservation、duplicate/stale/conflict、两个崩溃重放点、稳定 upsert、幂等 delete 与 fail-closed retrieval。没有 route、transport、Provider、Qdrant adapter、worker、默认值或真实数据路径调用它。
9. **认证 lifecycle transport 契约 — 已完成、未接线。** lifecycle-only HMAC purpose、固定 path 与独立 header 绑定 method、timestamp、nonce 和 exact body digest。Python 校验有界 replay window 与严格 A4 event/acknowledgement 投影；Go 产生相同 fixture 签名并严格解析无内容 acknowledgement。in-process client/handler 对 authentication、validation、ledger 和 vector 故障做无 raw detail 的安全映射。没有增加 HTTP route/client、dispatcher、worker、运行时 secret/config、默认值或真实数据路径。
10. **合成一次性 lifecycle 集成证明 — 已完成、仅测试。** 进程内 harness 使用真实 SQLite outbox migration、合成源 mutation、临时 AI ledger/vector 数据库、lifecycle-only HMAC 与稳定 fake vector writer。测试覆盖按序 create/update/archive/delete、四个中断点、重试/耗尽、过期复活防护、无正文对账与 rebuild generation 校验。没有增加 route、dispatcher、worker、Compose 改动、Provider/Qdrant 调用、运行时默认值或真实 Memo。nonce replay store 只证明单进程契约；共享多实例 replay 存储仍是后续运行时闸门。
11. **严格 grounded-answer 结果契约 — 已完成。** 独立 domain parser 只接受版本化受限 answer 与 opaque `evidence-*` reference；拒绝畸形、重复、额外字段，未知、重复、直接或超量 reference，raw context echo，以及 Provider 提供的正文或 metadata。最终 citation 只能从服务端持有的 `AgentCitation` 映射；validation、timeout 与 availability failure 只映射为固定无正文错误码。R4-I2 仅通过下述受保护集成消费该契约。
12. **安全 grounded-answer 运行时接入 — 已完成、仅 fake 验证。** Agent 授权检索只向 Provider 提供 `evidence-*` 标签和已授权证据，不提供 Memo ID、score 或 citation metadata。非 deterministic 输出只有通过 R4-I1 parser、context echo 检查和服务端 citation 映射后才能成为回答。空检索和 deterministic 输出不变；畸形输出、timeout 与 failure 继续映射为既有有界 502。没有调用真实 Provider、生命周期 runtime、Qdrant、Compose 默认值或真实 Memo。

## A1 验收结果

- Agent 默认关闭，且关闭时没有 Agent 行为。
- 完整 Memo 索引上的定向测试证明执行了一次 `search_memos`，并返回带引用的 deterministic answer。
- 空检索不调用 provider；检索与 provider 失败分别映射为安全的 503 与 502。
- citation 与 trace 不包含 `content`；Memos BFF 严格拒绝未知或不安全的内部响应字段。
- 既有 chat 契约未修改，相关测试通过。
- 显式 Web 入口保持 opt-in：展开并提交问题前不会发出请求，只调用同源 Memos BFF，并只渲染收紧后的 answer、citation 与 trace 投影。

## R4 grounded-answer 结果契约与接入

R4-I1 是纯契约，不改变运行时行为。非可信 Provider 结果必须且只能包含 `version`、
受限 `answer` 与一到十个 opaque `citation_refs`。reference 使用服务端签发的
`evidence-*` token，不得携带 Memo ID、score、metadata、正文、可见性、身份、prompt、
embedding、secret 或 trace。

validator 把每个 reference 映射到已检索、由服务端持有的 `AgentCitation`。未知、重复、
直接 Memo 或超量 reference 均 fail closed；显式受保护 context fragment 经规范化后执行
verbatim echo 检查。契约、timeout 与 Provider failure 只能映射为
`invalid_grounded_answer`、`provider_timeout` 或 `provider_unavailable`，不包含原始异常或
Provider 文本。

R4-I2 只把本契约接入 `EvidenceAnswerAgent` 的非 deterministic 路径。授权检索在 Provider
上下文中把内部 Memo ID、score 与 metadata 替换为请求内 `evidence-*` 标签。验证后的 answer
可以返回，但每个 reference 必须重新解析为既有的服务端 `AgentCitation`；Provider 结果字段不会
直接透传。空检索仍跳过 Provider，deterministic answer 不变，validation、timeout 与 Provider
failure 继续走既有有界 502。

该接入目前只使用合成证据和 fake Provider 验证；一次性真实 Provider smoke 仍是独立闸门。

## A4 本地 RAG 生命周期契约

本节是实现契约，不是已启用功能。当前通用 Memos Webhook 路径不能作为 A4 传输：Memos 侧使用可能丢弃任务的有界进程内队列，既有 AI 侧 `webhook_events` 表只能证明消费者已接收事件，而且为旧重试流程保存了收到的 payload。A4 要求由 Memos 持有可靠投递记录，并要求 AI 生命周期消费者不持久化 raw Memo 快照。

### 权威与持久化边界

- Memos 持有 Memo 正文、身份、normal/archived/deleted 状态、评论关系和当前可见性。生命周期事件只是重建派生状态的命令，不能成为第二事实源。
- Memos 必须在源数据变更的同一个数据库事务中写入 Memos-owned 持久 outbox。删除不能在没有 tombstone 事件时提交，事件也不能描述已回滚的变更。确认完成后，经过审计的保留规则可以从 outbox 清除 raw snapshot，但必须保留有界投递元数据。
- AI Service 只能持久化可重建状态：稳定 vector ID 与 vector、`memo_uid`、`index_version`、最高已接受和最近已应用的源序号、文档 hash、操作、重建 generation、状态以及有界时间或错误摘要。不得持久化 raw Memo 快照、身份、可见性映射、prompt、context、secret 或 Agent trace。
- 完整 Memo 快照只能存在于经认证的内部请求和派生 vector 所需的短时进程内存中；不得写入 AI 生命周期 ledger、日志、指标、trace 或 ops 响应。
- 既有回答委托 HMAC、Memos 可见性解析器和 `memo-v1` 预上下文过滤保持不变。生命周期传输认证属于独立实现闸门，不得扩大或复用浏览器权限。

### 版本化事件信封

Memos 只生成三类 A4 事件：

| 事件类型 | 含义 | 快照 |
| --- | --- | --- |
| `memo.index.requested.v1` | 首次形成可索引表示 | 当前完整 `memo-v1` 文档 |
| `memo.reindex.requested.v1` | 可索引表示已改变，或运维显式请求修复 | 当前完整 `memo-v1` 文档 |
| `memo.delete.requested.v1` | Memo 已删除或变为不可索引 | 仅 tombstone，不含正文 |

每个事件都包含不透明且不可变的 `event_id`、`memo_uid`、由 Memos 生成并单调递增的 `source_sequence`、固定为 `memo-v1` 的 `index_version`、`occurred_at` 和受控 `reason`。index/reindex 还包含完整的规范化文档及其 SHA-256 `document_hash`；delete 不包含文档。可见性和用户身份永远不是事件字段。未知事件类型、字段或索引版本，以及缺失或不匹配的 hash，都必须在 embedding 之前拒绝。

`source_sequence` 在 Memos 源事务内分配，是唯一排序令牌；用户可修改的时间戳不是 revision。重试必须复用同一 event ID、序号和不可变 payload。即使文档 hash 未改变，新发起的 reindex 也必须取得新 event ID 和更高序号。

投递采用至少一次语义，并按单个 Memo 的源序号处理。Memos 事务提交后可以尝试首次投递，但 Memo 变更不得依赖 AI 可用性；失败时 outbox 行保持可重试。Memos 应按源顺序尝试 pending 事件，但旧失败事件不能阻塞较新的 reindex 或 delete；较新事件被接受后，序号守卫会把旧重试判定为 stale。首个实现只提供有上限的显式运维重试：一次初始尝试加最多两次重试；不增加后台 worker，也不启用自动索引默认值。

### AI 消费状态机与幂等

AI 消费者必须先把事件与相同 `memo_uid`、`index_version` 的持久 highest-accepted 和 last-applied 状态比较，再使用正文：

- 较小序号返回 `stale` 确认，不能改变 vector；
- 已应用事件的 event ID、序号、操作和 hash 全部相同，返回 `duplicate`；同一 `applying` 或 `failed` 事件继续执行其幂等操作；
- 同一序号对应冲突的身份、操作或 hash 时，作为硬契约错误并保持可见、可重试；
- 较大序号先持久登记为 `applying`，立即使该 Memo 的所有旧 vector 不再符合检索条件；随后执行 upsert 或幂等 delete，记录 last-applied 状态并返回 `applied`；
- embedding/store 或 finalize 失败返回 `failed`；保留已接受序号以便安全重试，不推进 last-applied 序号，保持旧 vector 不可检索，也不得返回原始异常或 Memo 数据。

完整 Memo vector ID 继续使用 `EmbeddingService` 现有的稳定 hash 派生 ID。重复 upsert 替换唯一记录；重复 delete 是成功 no-op。派生 ledger 必须先登记事件，再变更 vector，最后完成状态；两个步骤之间崩溃时可以安全重复相同稳定 upsert/delete，登记失败则不能改 vector。每个 vector 都携带已应用源序号和 document hash，只有两者与 `applied` ledger 行一致时才可检索。即使没有找到 vector，delete 也要记录派生 tombstone 序号，防止延迟到达的旧 upsert 复活内容。

内部确认响应是严格投影，只含 `event_id`、`memo_uid`、`source_sequence`、`index_version`、`status`（`applied`、`duplicate`、`stale` 或 `failed`）、`operation` 与可选的有界错误码。不得包含文档、hash、provider 输出、prompt、context、embedding、可见性、身份或 secret。

### 默认 `memo-v1` 策略

- 一条 normal、非评论且 Markdown 非空的 Memo 对应一个完整 `memo-v1` vector。稳定 Memo UID 是身份；任何 chunk 都不符合条件。
- create 生成 index；正文或已索引元数据变化生成 reindex；archived Memo 恢复为 normal 时也生成 reindex。显式修复只能由 Memos 读取最新权威快照并生成 reindex，浏览器不能提供快照。
- delete、archive、转为评论或转为空正文都生成 delete。这些规则也会在重建时清除旧评论或其他不合格记录。
- 仅可见性变化不把可见性复制到索引，也不产生检索授权。既有 Memos 解析器在每次回答时计算调用者最新的 normal 完整 Memo UID 能力，AI Service 仍在组装上下文前过滤。
- `AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、memory vector store、deterministic provider 与 `AI_AGENT_ENABLED=false` 继续保持默认值。

### 重建、恢复与删除传播

单 Memo 修复使用显式 reindex 事件。完整重建必须由运维批准并由 Memos 驱动，且带唯一 `rebuild_generation`：

1. 保持 Agent 关闭或暂停回答流量；
2. 捕获 Memos outbox 高水位序号与权威可索引 Memo 数量；
3. 创建空的派生 generation，并从 Memos 重放最新 `memo-v1` 快照，不能从旧 vector store 或 AI ledger 重放；
4. 消费到捕获的高水位，再按序应用之后排队的事件；
5. 比较可索引数量、indexed-state 数量、高水位序号，以及由 Memo UID 与 document hash 生成的 manifest digest；
6. 只有所有检查都通过才激活新 generation，再按已评审的保留策略保留或丢弃旧派生 generation。

generation 切换能清除孤儿 vector，而不把 vector-store 扫描当成权威。恢复 Memos 后必须先验证 Memos，再丢弃 AI 索引并从已恢复的事实源重建。只恢复 AI 派生状态绝不能复活已删除 Memo。A4 设计验收不包含真实 volume 删除或重建。

### 可观测性与运维闸门

Memos-owned ops 状态公开 event ID、类型、序号、状态、attempts、有界 last error、时间戳、pending/failed/exhausted 数量、最老 pending 时长以及 produced/acknowledged 高水位。AI-owned ops 状态公开 applied/duplicate/stale/failed 数量、last-applied 序号、索引版本、generation、provider/store health、indexed-state/vector 数量和有界错误。两侧通过 event ID 关联，不公开 payload 或 Memo 正文。

只有同时满足以下条件才能声明索引已同步：pending、failed 和 exhausted 均为零；确认高水位达到捕获的源高水位；store health 与 provider dimension 匹配 `memo-v1`；可索引数量与 manifest digest 一致。任何失败或耗尽事件、持续增长或超龄 backlog、数量或 digest 不一致、版本或维度错误、过期删除、ops 输出携带正文，或 citation 超出 Memos 提供的 scope，都必须阻断 rollout 并产生运维可见的 degraded 状态。

回滚首先关闭 `AI_AGENT_ENABLED` 并暂停生命周期投递，不能改变 Memos 数据或可见性。随后回退生命周期消费者或 provider 配置，隔离并丢弃可疑派生 generation，从 Memos 重建后才可重新启用。scope 泄漏、过期内容复活或 raw content 暴露要求立即关闭并隔离派生索引。delete 只能通过正常 Memos 备份策略恢复权威 Memo 后再 reindex，绝不能从 AI 状态复制正文回 Memos。

### 最小实现与验证计划

后续每一步在产生运行时或真实数据影响前都需要单独授权：

1. **已完成：** provider-neutral 事件/确认 fixture 与纯状态机测试已覆盖 duplicate、stale、conflict、retry、tombstone、quarantine 和脱敏；没有增加 route、数据库、transport、Compose 或默认值变更。
2. **SQLite 已完成：** dormant Memos outbox schema 和显式 adapter 使用临时数据库证明 create/update/archive/delete 原子性、单 Memo 保序、tombstone、有界 attempts 与无 worker 的显式失败记录。运行时 CRUD 接入和其他数据库 adapter 仍是独立闸门。
3. **已完成：** 增加 AI 派生生命周期 ledger 与 fake vector-store 集成测试，证明稳定 upsert、幂等 delete、reservation/vector-finalize 两个崩溃点的重放、tombstone 保护、安全错误脱敏、retrieval quarantine，以及不持久化 raw snapshot。运行时构造仍是独立闸门。
4. **已完成：** 增加独立认证的生命周期 transport 契约测试，证明严格 request/acknowledgement 投影、domain-separated HMAC、timestamp/nonce/body digest 绑定、有界 replay window 和安全失败映射，但不增加 route、dispatcher、worker 或现有 CRUD 接线。多实例 replay store 仍是后续运行时闸门。
5. **已完成：** 使用纯临时 store 完成合成、可销毁的进程级集成证明，覆盖按序 outbox-to-ledger 收敛、backlog/high-water/count/digest 投影、四个中断点、有界重试/耗尽、tombstone 防护与 rebuild generation 校验。既有默认值、端口和浏览器边界保持不变并另行复核；没有新增运行时 endpoint。
6. 只有取得明确批准后，才能在真实 Memos 数据上运行显式 opt-in 的本地迁移/重建；此前必须准备备份、回滚与删除后验证。

### Chunk 与 Qdrant 闸门

A4 不启用 chunk 或 Qdrant Agent 检索。只有完整 Memo 生命周期已具备 Memos-owned 可靠投递，删除/重试/重建行为已被证明，可观测性保持 scope 安全，回滚已经测试；chunk 使用独立版本和 collection，并具备稳定 delete/tombstone 规则；离线评估和双路径迁移达到已评审质量门槛；可信 Memos gateway 在组装上下文前执行最新可见性约束之后，才能考虑该路线。Agent 的 `search_memos` 继续只接受完整 `memo-v1` 证据。

## 后续工作不包含在本提案内

任何写工具都需要独立评审认证与 visibility mapping、显式用户确认、幂等、审计与回滚、限流及威胁建模。只读 Agent 不隐含这些能力。
