# Evidence Answer Agent

> 状态：A1-A4 与 R4 的既有边界保持不变。R5-I1 至 R5-I16 已完成 durable retrieval、current-authority rehydration、认证 transport、默认关闭的 runtime ownership、verified answer selection 与 completion audit。获授权的 post-I16 切片现已连接 SQLite mutation/outbox、既有 internal AI listener、generation activation 与 Qdrant derived state；两次 disposable 认证浏览器运行完成 private/public visibility、update/delete、restart、rollback 与精确 cleanup 矩阵。R5 仅在默认关闭的单机范围内完成。

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
13. **一次性 grounded-answer Provider smoke — 已完成。** 临时、无 volume、无宿主机端口的容器使用合成 complete-Memo 证据与已有本地 Ollama Provider。第一次非 exact 结果被有界 502 fail closed；只澄清 prompt 的纯 JSON 格式后，Provider 产出 exact 结果，验证后的 answer 与服务端 citation 成功返回。同一运行证明空检索零 Provider 调用、不可用 endpoint 返回固定 502。容器已删除，未持久化运行时设置、模型配置或数据。
14. **持久化授权检索契约 — 已完成、未接线。** R5-I1 定义了有界的 Memos-authority query、无正文 candidate/ledger snapshot、第二阶段完整 Memo materialization、请求内 opaque evidence reference 与服务端 citation 投影。fake repository 证明可见性在加载正文前求交；只有当前 active generation 中，`memo-v1` 记录的序号与 hash 匹配 `applied` A4 ledger 时才符合条件。空/未知 scope、pending/failed/delete 状态、过期序号/hash、旧或未知 generation、缺失 ledger、chunk 版本、重复/冲突记录与 repository failure 全部 fail closed。证明只使用合成内存记录，不修改现有 Agent 或 retrieval runtime。
15. **一次性 repository-adapter parity proof — 已完成、未接线。** R5-I2 把 R5-I1 边界绑定到显式创建的临时 SQLite store。candidate query 下推 Memos 授权 UID 集合与 limit，service 仍在正文加载前再次执行可见性求交。active generation、无正文 candidate 与 A4 ledger state 在同一个只读事务中读取；基于 revision 的 opaque snapshot token 防止后续正文加载混合不同 store generation。reopen parity、lifecycle 拒绝、重复/不一致行与固定 repository failure 映射只使用 `tmp_path` 和合成记录。该 adapter 仅用于测试，并非生产正文持久化或 rehydration 设计。
16. **生产正文 rehydration 设计契约 — 已完成、未接线。** R5-I3 为 durable Agent 路径选择认证的 Memos 当前权威 rehydration，而不是 AI 侧持久化完整 Memo 正文或持久 hybrid cache。精确且有界的请求/响应投影绑定 eligible candidate 的 sequence、hash、version 与 R5 snapshot token；update、delete、visibility 丢失、generation/revision 切换、缺失项或响应不一致全部映射为同一个无正文错误。完整正文只存在于认证请求内存。共享 fixture 与纯测试未增加 transport、repository、route、runtime secret、database 或真实数据。
17. **认证 content-rehydration transport 证明 — 已完成、未接线。** R5-I4 把 R5-I3 精确请求绑定到 rehydration-only method/path、transport version、timestamp、nonce 和 body digest；独立 response HMAC 在精确解析前绑定 status、响应 timestamp、原请求 nonce、derived snapshot token 与 body digest。有界 process-local request/response replay store、单次调用 fake authority handler、固定签名 failure 投影与共享合成 fixture 覆盖篡改、过期、重放、timeout、部分输出和 authority mismatch。本证明只覆盖认证与完整性，没有增加 HTTP adapter、runtime secret、持久化、远程保密性主张或真实数据。
18. **跨语言 Memos transport parity — 已完成、未接线。** R5-I5 新增 provider-neutral Go request verifier 与 response-only signer/parser，共享合成 fixture 逐字节固定两套 HMAC canonical form。嵌套 exact JSON parsing 对重复、未知、部分、超限、非法 UTF-8、携带 identity、stale 或不一致 payload 统一返回无正文错误。Go 证明没有新增 route/client、replay store、authority lookup、runtime secret/configuration、持久化、网络或真实数据。
19. **Memos current-authority adapter 契约 — 已完成、未接线。** R5-I6 只接受已经验证的 `EvidenceRehydrationRequest` 与 Memos 内部 opaque 认证上下文绑定。一次调用的 reader protocol 必须返回同一个原子 snapshot，其中 authority reference、context binding、revision、authority token、当前 visibility、完整 Memo 类型、normal 行状态、current lifecycle 状态、sequence、hash 与 `memo-v1` 全部一致。纯 fake 测试证明 UID 精确一一对应、由请求拥有 selection 顺序、响应不投影 identity/visibility，并对 update/delete、部分、重复、stale、混合 snapshot 与 adapter failure 整体拒绝。没有接入真实 Store、visibility resolver、route、replay、HMAC、runtime 配置、持久化、网络或数据。
20. **真实单机 SQLite current-authority reader — 已完成、未接线。** R5-I7 只从 Memos 内部认证 context 取得 caller identity，复用共享 Memo visibility scope，并通过一个 SQLite 只读 snapshot 读取当前 normal caller、受限请求 UID、comment relation、完整正文与最新 A4 source event。最新 delete、未知 version、stale document、不合格 Memo、缺失行或读取期间任意并发提交都使整批失败。adapter 没有注册 HTTP/runtime，也不主张真实数据或多实例安全。
21. **process-local Memos authority capability — 已完成、未接线。** R5-I8 只能从 Memos 认证 context 与 Memos-owned 有界完整 Memo UID scope 签发。固定容量、短时内存 registry 把三个独立 opaque token 绑定到同一私有 caller/scope 记录，并对精确有界的 rehydration 子集最多原子消费一次。fake clock/token/scope 测试覆盖认证来源、UID 上限、过期、容量、碰撞、错配、重启失效与并发 consume。没有增加 route/client、replay 接线、runtime 配置、持久化、真实数据或多实例主张。
22. **单机 rehydration composition — 已完成、未接线。** R5-I9 用纯 Go 固定 R5-I5 验签、专用有界 request replay、R5-I8 单次 consume、server-owned auth context 恢复、一次 reader factory/reader、R5-I6 投影、exact JSON 与 R5-I5 response signing 的顺序。合成测试覆盖 nonce/capability 独立单次性、scope/binding/token 拒绝、固定签名 failure、并发 duplicate 与新 store 失效边界。没有注册 HTTP route/client，也没有增加 runtime secret/config、timer、retry、持久化、真实数据或多实例主张。
23. **disabled 单机 HTTP adapter — 已完成、未接线。** R5-I10 在 R5-I9 外增加尚未注册的标准库 handler/client。handler 只接受精确 internal POST envelope，把未验证输入投影为无正文、不可缓存的 404，并只映射 exact signed 200/503；client 固定五秒 timeout，只调用一次注入的 `RoundTripper`，关闭有界 body，并在解析前认证 exact response。测试只使用 recorder、内存 handler 与 fake transport；没有增加 route、listener、环境变量/配置字段、runtime secret source、真实 socket 或 Agent runtime 接线。
24. **独立 rehydration runtime 配置 — 已完成、未接线。** R5-I11A 增加对称的 Go/Python 环境契约，disabled 时不保留 secret，启用时必须先开启总 Agent flag。runtime 要求一个规范的无填充 base64url 32-byte current secret、可选且不同的 previous secret、与回答 delegation secret 严格隔离，以及 AI 侧单一无凭据 HTTP(S) Memos origin。纯 settings 测试没有生成 key、构造 route/client、启动 listener/timer、持久化或使用真实 secret。
25. **Memos dormant rehydration registration — 已完成、opt-in。** R5-I11B 用一份共享的 process-local capability registry 与 request replay store 构造 current 及可选 previous composition。handler 固定按 current 后 previous 验证，并只用实际匹配 request 的 key 签回 verified response。只有显式启用才在既有 Echo server 上注册 exact internal POST；disabled 时 route 不存在。runtime 不拥有 listener、goroutine、timer、transport 或 closeable resource。
26. **AI 侧 rehydration client lifespan — 已完成、未连接 answer path。** R5-I11C 只在启用的 AI Service lifespan 内构造 Python client，并在 shutdown 清空 state、确定关闭 transport。注入的 async transport 不重试；client 固定五秒 timeout、拒绝 redirect 与非精确 response envelope、有界流式读取、先验签再解析，并独占一份 process-local response replay store。对象只暴露在 `app.state`，没有 endpoint 或 `EvidenceAnswerAgent` 调用它。
27. **认证 capability delegation bridge — 已完成、未连接 client。** R5-I12 让 enabled Memos runtime 从认证 BFF path 一次读取 caller 与精确可见完整 Memo UID scope，对非空 scope 签发一个 opaque capability，并只把 ref 加入既有 signed internal answer request。空 current scope 不签发 capability，保留正常 no-context 行为。浏览器 request 与 safe response 均不包含 authority ref；disabled 模式保留原 memory delegation body。
28. **durable rehydration orchestration — 已完成、未选择 runtime。** R5-I13 只接受 verified delegation、content-free candidate repository 与 I11C client protocol。它先过滤 candidate，再调用 client 一次，重新读取 current snapshot token，只在 request memory materialize 重新验证的 documents，并复用现有 authorized result。空 scope/candidate 不调用；所有 mismatch/failure 均为 content-free 且无 fallback。
29. **无正文 durable runtime selection — 已完成、未连接回答路径。** R5-I14 让 A4 SQLite ledger 持有 active rebuild generation 与单调 snapshot revision，并在每次 lifecycle transition 的同一事务中改变 opaque token。vector adapter 把精确授权 Memo UID 集合下推到排序，只接受严格的 `memo-v1` sequence/hash/generation metadata，连接 applied ledger state，并拒绝重复、格式错误、含正文、stale、delete、quarantine 或并发变化结果。既有 rehydration opt-in 只在 memo-mode Qdrant selection 下于 lifespan state 构造 repository/orchestrator；disabled 启动不构造任何对象。`EvidenceAnswerAgent` 和 endpoint 仍未选择它。
30. **durable 回答路径选择 — 已完成、opt-in。** R5-I15 为 `EvidenceAnswerAgent` 增加一个可选 async durable retrieval dependency。internal endpoint 只在既有 rehydration flag 下，从当前 app lifespan 注入已持有的 orchestrator；ownership 缺失或任何 durable failure 均映射既有安全 503，绝不 fallback memory。disabled 保持原 memory retrieval 行为。durable evidence 只用 server-owned Memo UID、source sequence 和 `memo-v1` 生成受控 Agent citation；vector/rehydration metadata 不能提供 title、tag、visibility 或 citation 字段。临时 SQLite、内存 vector 与 fake-client 证明已到达 answered trace，未使用网络。

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

R4-I3 进一步在临时容器中使用合成证据和已有本地 Ollama Provider 验证该接入。第一次不满足
exact JSON 的响应被无细节拒绝；只增加 prompt 的 JSON-only 说明后，复跑成功返回一个验证后的
answer 和一个服务端 citation。空检索未调用 Provider，不可用 endpoint 仍返回固定 502。smoke
没有 volume 或宿主机端口，容器已删除。这只是单机、单模型兼容性证明，不代表质量或生产就绪。
保留的无正文命令摘要为：成功状态 `200`、answer 长度 `79`、一个服务端 citation、exact parser
通过、prompt 含 opaque reference 且不含身份/metadata、空检索 `200` 且 Provider 调用数为零、
不可用 endpoint 返回固定正文的 `502`。

## R5 持久化授权检索与当前权威正文 rehydration

R5-I1 是 provider-neutral、尚未接线的边界。query 必须携带由 Memos authority 提供、数量有界且
无重复的完整 Memo UID 集合；空集合不访问 repository，直接返回空结果。repository 分为两阶段：
第一阶段只返回排序后的 record identity、generation、index version、sequence/hash 与已关联的 A4
ledger state；只有通过 Memos UID 求交与全部 lifecycle 检查的记录，第二阶段才允许加载完整合成
Memo 文档。即使 adapter 声称已应用权限条件，service 仍会再次执行 UID 求交。

候选只有同时满足以下条件才 eligible：generation 等于当前 active generation，index version 严格为
`memo-v1`，且 `is_retrieval_eligible` 确认 source sequence 与 document hash 匹配最近一次
`applied` upsert，不存在 tombstone 或 failure quarantine。缺失、applying、failed、deleted、stale、
旧/未知 generation、chunk、重复或内部不一致的派生记录均不得触发正文加载或 context 组装。未知
授权 UID 不产生证据；畸形或重复 query UID 通过固定 contract error 拒绝。

eligible 文档只获得请求内 `evidence-*` reference。citation identity 必须重新锚定到 Memos-authority
query，并由 service 使用白名单字段构造，不能来自 Provider 输出或 store 的任意 metadata。安全可观测
投影只包含契约版本、结果数与 opaque reference。
repository、document 或一致性故障统一折叠为 `authorized_retrieval_unavailable`，不暴露 Memo 正文、
问题 context、payload、embedding、identity、visibility、secret、citation metadata 或原始异常。

R5-I2 增加一个可重新打开的一次性 SQLite repository protocol 实现。它只在调用方提供的临时文件中
保存合成证明数据。candidate read 会下推授权 UID 集合和请求 limit，但仍不读取正文；active
generation、candidate 字段与关联的 A4 ledger eligibility input 在同一个只读事务内读取。返回的
opaque snapshot token 把第二阶段正文加载绑定到相同 store revision 与 active generation，因此两阶段
之间发生 generation 切换或任何 adapter-owned 写入时，只能整体失败，不能返回部分结果。

测试把重新打开后的 SQLite 结果与内存 fake 对比，覆盖 opaque reference 顺序、context 顺序与服务端
citation。测试还证明：未授权正文 key 不会进入加载请求；pending、failed、quarantine、stale、
tombstone、旧/未知 generation、缺失 ledger 与 chunk 记录均零正文加载；重复或不一致的
candidate/document 行统一映射为 `authorized_retrieval_unavailable`；open、schema、query、load 与
transaction failure 不暴露原始细节。临时 schema 不保存 visibility、最终 identity、Provider citation
metadata、prompt、embedding、secret 或 runtime 配置。

该 SQLite document 表仍只是一项一次性测试 fixture，不能升级为生产存储。R5-I3 为第一条 durable
Agent 路径选择 **Memos 当前权威 rehydration**。AI 侧持久化完整 Memo 正文与持久 hybrid cache 均被
拒绝，因为二者都会重复正文 retention、delete、visibility、backup 与泄露响应责任。此决策仅约束新的
durable Agent 路径；ADR-017 描述的旧完整 Memo vector metadata 保持不变，但不能成为 R5 的生产权威。

R5 选择 eligible candidate 后，AI 侧只能创建一个有界的 `memo-evidence-rehydration-v1` 请求，其中仅有
derived snapshot token 和由 Memos 签发、仅请求内使用的 opaque `memos_authority_ref`，以及服务端生成的
selection reference、Memo UID、source sequence、document hash 和 `memo-v1`。AI 侧不能解释、持久化或记录
该 reference。未来由 Memos 持有的 handler 必须使用独立 internal path 与认证 purpose，在服务端解析该
reference 并重新确认
调用者当前 visibility 和完整 Memo eligibility，并从同一个原子 current-authority snapshot 读取全部请求
文档。响应只回显 selection reference、精确正文、sequence/hash/version、derived snapshot token 和
opaque Memos authority token。响应必须 all-or-nothing：缺失、archived、comment、blank、deleted、
unauthorized、重复、stale 或部分失败都不返回正文。

AI 侧随后必须重新校验原始授权 query、精确 eligible selection、响应映射、sequence/hash/version，且
derived snapshot token 在 materialization 前仍为当前值。Memos 观察到并发 update/delete 时，会通过
内容变更或记录缺失使旧 selection 失败；derived revision 或 rebuild-generation 切换会使 token 失效。
tombstone、pending/failed/conflict quarantine、旧 generation 与 `memo-chunk-v1` 在 rehydration 前仍然
不 eligible。derived candidate、ledger、vector payload、浏览器、Provider 或响应 metadata 均不能提供
最终 visibility、identity、正文 authority 或 citation 字段；最终 identity 仍锚定 Memos-authority query，
citation 仍由服务端构造。

authority reference 与完整正文只保留到请求结束，不得进入 AI ledger、vector payload、日志、metrics、trace、backup 或错误
正文。Memos 持有正文加密、访问控制、retention、backup、restore 与源数据恢复责任。AI 派生状态不属于
权威备份，可以丢弃并从 Memos 重建；restore 必须先验证 Memos backup，再在 activation 前完成派生状态
对账。任何 contract、认证、timeout、replay、部分响应、authority 或 adapter failure 都只映射为
`authorized_retrieval_unavailable`，不得暴露 raw Memo、question、context、payload、embedding、identity、
visibility、secret、SQL、endpoint 或原始异常。

R5-I4 在不打开网络连接的情况下证明该 transport 边界。request canonical form 包含 rehydration-only
purpose、transport version、固定 `POST` path、十进制 timestamp、nonce 和 SHA-256 body digest。
verification 执行 60 秒时效窗口、32 KiB request 上限、无重复 key 的 exact JSON，并在 authority callback
前消费一次 process-local nonce。callback 最多执行一次且必须返回原子 Memos current-authority snapshot；
timeout、authority 或 schema failure 只成为签名的 `503 authorized_retrieval_unavailable`。

response 使用独立的 response-only HMAC purpose 与 header namespace。canonical form 绑定 transport
version、method/path、响应 timestamp、原请求 nonce、derived snapshot token、status（`200` 或 `503`）和
exact body digest。AI 侧先验证签名与时效，再 exact parse，并重新核对每个 selection reference、
sequence/hash/version，最后消费独立 client-side replay entry。契约固定未来 client timeout 为五秒且不自动
重试；进程内证明只映射合成 `TimeoutError`，没有实现 HTTP timer。success/failure response 均不含
`memos_authority_ref`。

两侧 replay store 都明确有界且仅限单进程。HMAC 证明完整性和对 scoped secret 的持有，不提供正文
保密性。跨宿主或多实例继续被阻塞，直到具备加密 transport、shared replay protection、密钥轮换和独立
威胁评审。真实数据 opt-in 还必须验证 Memos backup，提供显式 dry run、rollback 和运行后
lifecycle/retrieval reconciliation。R5-I4 不改变 `EvidenceAnswerAgent`、`RetrievalService`、VectorStore
构造、A4 runtime route、Memo CRUD、dispatcher/worker、Qdrant、Compose 或真实数据。

R5-I5 在 Go 中独立完成 request 验签后 exact parsing，并且只允许在 response-only purpose 下签名 exact
success 或固定 `503`。Go parser 重新核对 snapshot token 与每个 selection reference、sequence、hash、
version，并拒绝 response identity 或 authority-reference 字段。这只是跨语言契约 parity，不是 Go replay
实现或 Memos authority adapter。HTTP route/client、process-local replay 接线、当前 visibility authority
lookup、runtime secret/configuration 和 AI runtime selection 仍是后续独立授权闸门。

R5-I6 只定义下一层 Memos-owned 边界，不实现真实 lookup。`EvidenceAuthorityContextBinding` 仅包含 opaque
authority reference 与 opaque authenticated-context token，没有 caller ID、owner 或 visibility 字段。
`EvidenceCurrentAuthorityReader` 只调用一次，并必须从同一个原子 current-authority snapshot 返回全部请求的
完整 Memo。每个文档都必须当前可见、complete、normal、非 tombstone、非空，并精确匹配请求 UID、source
sequence、document hash 与 `memo-v1`。每个文档的 revision 和 authority token seal 还必须与 snapshot 级 seal
相同，从而阻止混合两次读取的行。

响应按请求的 selection 顺序组装，并且只包含 R5-I3 字段：selection reference、正文、sequence、hash、
version、derived snapshot token 与 opaque authority token。Memo UID、caller identity、visibility、authority
reference、citation metadata 与 store metadata 均不投影。缺失、多余、重复、未知、archived、comment、blank、
deleted、tombstone、已变化、畸形或混合行全部只返回 `authorized_retrieval_unavailable`，不返回部分正文。
该证明只使用内存 fake，不证明真实 Store transaction 原子性。真实 Memos Store reader、HTTP handler/client、
replay 接线、runtime secret/config 与 AI runtime selection 均需分别授权。

R5-I7 提供第一个真实 reader 实现，但严格限制为 SQLite 且仍未接线。constructor 只从 Memos authentication
context 取得 caller ID；R5 request 与 opaque binding 不能携带或覆盖 identity/visibility。reader 复用
`ListMemos` 的认证 visibility scope，在专用 SQLite connection 上开启一个只读 transaction。该 transaction
确认 caller 仍是 normal user，并通过受限 requested-UID CTE 只选择 normal、非 comment、非空且当前可见的
Memo。每个 Memo 必须关联它最新的 outbox event；该 event 必须仍是 `memo-v1` upsert，且其 source document
等于当前 Memos 正文。最终返回正文只来自 Memos；outbox metadata 不能授权 visibility、identity 或 citation。

reader 在 transaction 前后检查 SQLite `data_version`；读取期间任何提交——包括正文 update、delete 或
visibility change——都会使整个 snapshot 失效。UID、sequence、hash、version、请求顺序与响应投影仍由
R5-I6 精确重查。临时 SQLite 测试覆盖 visibility parity、comment/archive/blank/tombstone、source 缺失或
不一致、并发变化与固定错误。R5-I7 本身只覆盖现有 SQLite schema 和单机进程，不证明 MySQL/PostgreSQL
parity，也不增加 capability issuer、route/client、HMAC/replay 接线、runtime 配置、真实数据或多实例支持。

R5-I8 补齐 process-local capability 边界，但不把它接到 R5-I7 或 transport。签发只接受 Memos
authentication context；接口没有 caller、owner、visibility、query、request 或 UID-scope 参数。一个
Memos-private scope source 必须返回同一个 current caller，以及采用 R5-I1 matcher、非空、不重复且最多
1,000 个完整 Memo UID 的集合。registry 从三个独立 token-source 值派生 authority reference、
authenticated-context token 与 authority token，并把三者绑定到同一个私有 entry。只有 authority reference
预期进入后续签名 rehydration request；caller identity、完整 UID scope 和另外两个 token 均没有 JSON 投影。

registry 的容量与 TTL 在构造时固定，TTL 上限为 60 秒。它使用注入 clock、惰性过期且没有 timer，并通过
每个 registry 单调递增的派生序号，避免回收容量后把旧 capability 错认成同一进程内的新 entry。consume
在同一把锁内完成 lookup、私有 token index 绑定检查和删除；并发调用最多一个能取得 Memos-private
resolution。该 resolution 只供未来 handler 恢复新的 server-owned auth context、原始 UID scope、未改变的
R5-I6 两字段 binding 与 authority token。任何未来 R5-I7 调用之前，selection 必须是该 scope 内唯一且
1 至 10 项的子集。unknown、expired、malformed、capacity、mismatch、duplicate、out-of-scope、clock、token、
scope-source 或 concurrency failure 均只返回 `authorized_retrieval_unavailable`，不返回 partial binding。

这是刻意限定为单进程、request-local 的证明。进程重启或新 registry 会使全部旧 entry 失效。R5-I8 不复用
R5-I4 nonce store，也不实现 HTTP、HMAC/replay runtime composition、answer runtime selection、配置、secret、
持久化、数据库、网络或真实数据。任何多实例使用前仍必须提供 shared atomic capability/replay store 与加密
transport。

R5-I9 在不注册 runtime 的前提下组合上述边界。constructor 只接受显式提供的 scoped secret、不超过 60 秒
的 request age、clock、专用固定容量 request replay store、R5-I8 registry 与 reader factory。R5-I5
HMAC/freshness/exact body verification 必须先于 nonce consume，nonce consume 先于 capability lookup；私有
resolution 在恢复新的 Memos auth context 前再次检查 exact token binding 与有界授权 UID 子集。只有该 context、
R5-I6 两字段 binding 与 authority token 能进入 reader factory；factory 和 reader 每个请求最多调用一次。

request replay store 与 capability registry 是容量和生命周期相互独立的两个 process-local 类型。同 nonce
并发请求最多一个越过 replay；更换 nonce 也不能重复使用已消费 capability。新 replay store 会遗忘旧 nonce，
新 capability registry 会拒绝旧 authority reference，这只是显式 restart 边界，不是 durability 主张。未来
client policy 仍是五秒 timeout、`auto_retry=false`，但本切片没有 client 或 timer。

未认证或 malformed request 在 replay 前只返回固定本地错误和零 response projection，因为它没有可供 response
HMAC 信任的 snapshot token。request 验证成功后，replay、capability、binding、reader 或 schema failure 只能
产生 exact signed `503 authorized_retrieval_unavailable`；response signing 自身失败时返回零 projection，绝不
发出 unsigned body。成功只允许 exact signed R5-I6 `200`。caller、完整 UID scope、authenticated-context token、
authority reference 与原始异常均无 response 或 observability 投影。

R5-I10 用 dormant 标准库 HTTP 对象包裹该 composition，但不注册 route 或打开 listener。handler 只接受精确
`POST /internal/ai/agent/evidence/rehydrate`、四个 request HMAC header 各一个值、精确
`application/json`、1 byte 至 32 KiB 的已知非 chunked body 长度与唯一 JSON value，并且在进入 R5-I9 前
必须成功关闭 request body。任何 verification 前拒绝都成为无正文、无签名且不可缓存的 404。验证后的成功或
下游失败只映射 exact body、status、四个 response HMAC header、JSON content type 与
`Cache-Control: no-store`。

dormant client 只接受 constructor 注入的 base URL、scoped secret、clock 与 `RoundTripper`。它把
`http.Client.Timeout` 固定为五秒、禁止跟随 redirect、只发送一次 POST 且不 retry、有界读取并关闭 response
body、拒绝 duplicate、cacheable、identity 或 debug response header，并在 exact parsing 前验证 freshness、
request nonce、snapshot token、status、body 与 response HMAC。client response replay 仍只属于 AI 侧 R5-I4
store；Go handler 不新增第二份 client replay store。request context 会传入恢复的 server auth context，取消时
fail closed。

R5-I10 没有 route registration、listener、环境变量、配置字段、runtime secret source、rotation/overlap policy、
port、volume、migration、持久化、真实网络访问、answer-path import、真实 Store 或真实数据。runtime secret
sourcing/rotation、shutdown ownership、Docker/浏览器端到端证明与 AI runtime selection 均需要后续明确授权。
任何多实例使用前仍必须提供加密 transport 与 shared atomic replay/capability storage。

R5-I11A 建立第三个 purpose-scoped secret domain，不复用 Memos session secret 或
`AI_AGENT_INTERNAL_SECRET`。deployment boundary 把 `AI_AGENT_REHYDRATION_SECRET_CURRENT` 与可选的
`AI_AGENT_REHYDRATION_SECRET_PREVIOUS` 分别注入两个进程；服务本身不创建、分发、保存、记录或投影这些
值。`AI_AGENT_REHYDRATION_ENABLED=false` 时两侧 contract 都丢弃已提供值；启用时还必须满足
`AI_AGENT_ENABLED=true`，malformed、duplicate 或与 delegation secret 相同的值全部在启动配置校验时失败。
AI contract 还要求 `AI_AGENT_REHYDRATION_MEMOS_URL` 是单一无凭据 HTTP(S) origin。

keyring 只在启动时固定，最多 current 加 previous，没有 timer 或动态 reload。R5-I11B 固定按 current 后
previous 验证，两份 composition 共享同一个 process-local capability registry 与 request replay store；verified
success/failure 只由实际匹配 request 的 key 签名。显式 opt-in 只在现有 Memos Echo 实例注册 exact POST，
disabled 时 route 不存在。Memos server 拥有 handler 生命周期，runtime 不增加 listener、port、goroutine、timer、
transport 或 shutdown hook。AI client 由独立 lifespan 管理。

R5-I11C 只在 rehydration flag 启用时于 FastAPI lifespan 构造 Python client；生产注入
`AsyncHTTPTransport(retries=0)`，测试注入内存 transport。每次调用只准备一次 signed POST，固定五秒 timeout，
不 redirect/retry，有界流式读取 response，要求 exact signed 200/503 headers，并在解析前验签及消费现有
process-local response replay。shutdown 始终关闭 owned client/transport 并清空 `app.state`；disabled lifespan
不创建 transport。该 client 仍未连接 answer Agent 或 durable retrieval selection。

R5-I12 为私有 Memos-to-AI delegation 增加一个可选 opaque `memos_authority_ref`。rehydration 启用时，BFF 在
一次 operation 中从同一 process-local registry 获取 Memos-authenticated current visible UID scope 与 capability，
再用既有 answer HMAC 委托该 UID 精确副本与 ref。空 scope 不委托 ref；registry/scope failure 沿用安全 BFF failure。
浏览器不能提供或接收该字段。Python 只校验其 32-64 位 opaque 形状，尚未调用 lifespan client。

R5-I13 在不选择 runtime adapter 的前提下组合既有 R5 domain contract。verified delegation 先转为 authorized
query，content-free candidates 在一次 rehydration request 前完成过滤。只有 exact success response 才继续读取
新的 repository snapshot token 并执行既有 materialization cross-check。client failure、snapshot change、partial 或
mismatch 全部映射 `authorized retrieval unavailable`，绝不读取 derived raw content。空 authorized/candidate scope
直接返回空结果且不调用 client。当前 endpoint 与 `EvidenceAnswerAgent` 均未使用该 orchestrator。

R5-I14 在不持久化 Memo 正文的前提下，把该 orchestrator 绑定到生产 vector 与 lifecycle 边界。A4 SQLite ledger
仅在既有派生状态旁保存一个 active generation 和单调 revision；reserve、complete、fail 在各自状态事务中推进
revision。repository 对问题生成 embedding，把精确授权 UID 集合下推到内存/Qdrant 排序，并把每个无正文结果
连接到 ledger。只有 current-generation `memo-v1` metadata 的 sequence/hash 与 applied upsert 匹配时才输出；
缺失、重复、越权、stale、delete、quarantine、含正文或并发变化均 fail closed。既有
`AI_AGENT_REHYDRATION_ENABLED` 只在 memo-mode Qdrant 被选择时于 FastAPI lifespan 持有 repository 和
orchestrator。memory 默认值不变，回答 Agent 继续留待 R5-I15 接线。

R5-I15 在不增加第二个 client、repository、ledger、transport、route 或配置开关的前提下连接已持有的
orchestrator。Agent 在调用可选 async retrieval dependency 前先验证 delegation。durable result 只提供请求内
context；其 server-owned citation 被映射到既有 Agent schema，title/tag 使用受控空值，identity 仅由
`memo-v1`、Memo UID 与 source sequence 生成，不读取 rehydration/vector metadata。空 durable evidence 保留
no-context 且不调用 Provider。runtime ownership 或 authority 缺失、rehydration failure、snapshot race、结果格式
错误或 projection failure 均映射既有 retrieval-unavailable 503，绝不 fallback memory。disposable product-path
proof 只使用临时 ledger、内存 vectors、合成 delegation 和 fake rehydration client，不主张真实运行时已验收。

后续获授权的单机切片把 Memos SQLite mutation 与 authoritative outbox 原子耦合，经现有 AI listener 验证独立
lifecycle HMAC，写入无正文 ledger/Qdrant state，并只在 manifest 对账后激活 exact generation。两次 disposable
运行使用 deterministic Provider、临时账号/Memo/volume/secret，证明同源 BFF、跨用户 private/public 可见性、
update/delete、restart、rollback 与 cleanup；不增加 listener、host AI port、默认启用或多实例声明。

## A4 本地 RAG 生命周期契约

本节定义只在显式单机 opt-in 下使用的 lifecycle contract。通用 Memos Webhook 路径不能作为 A4 传输：Memos 侧使用可能丢弃任务的有界进程内队列，既有 AI 侧 `webhook_events` 表只能证明消费者已接收事件，而且为旧重试流程保存了收到的 payload。A4 runtime 由 Memos 持有可靠投递记录，并要求 AI lifecycle consumer 不持久化 raw Memo 快照。

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

回滚首先关闭 lifecycle 与 rehydration，再恢复 `AI_VECTOR_STORE=memory`；也可设置 `AI_AGENT_ENABLED=false` 完全关闭 Agent。该过程不能改变 Memos 数据或可见性。随后回退 lifecycle consumer 或 provider 配置，隔离并丢弃可疑 derived generation，从 Memos 重建后才可重新启用。scope 泄漏、过期内容复活或 raw content 暴露要求立即关闭并隔离派生索引。delete 只能通过正常 Memos 备份策略恢复权威 Memo 后再 reindex，绝不能从 AI 状态复制正文回 Memos。

### 最小实现与验证计划

后续每一步在产生运行时或真实数据影响前都需要单独授权：

1. **已完成：** provider-neutral 事件/确认 fixture 与纯状态机测试已覆盖 duplicate、stale、conflict、retry、tombstone、quarantine 和脱敏；没有增加 route、数据库、transport、Compose 或默认值变更。
2. **SQLite 已完成：** dormant Memos outbox schema 和显式 adapter 使用临时数据库证明 create/update/archive/delete 原子性、单 Memo 保序、tombstone、有界 attempts 与无 worker 的显式失败记录。运行时 CRUD 接入和其他数据库 adapter 仍是独立闸门。
3. **已完成：** 增加 AI 派生生命周期 ledger 与 fake vector-store 集成测试，证明稳定 upsert、幂等 delete、reservation/vector-finalize 两个崩溃点的重放、tombstone 保护、安全错误脱敏、retrieval quarantine，以及不持久化 raw snapshot。运行时构造仍是独立闸门。
4. **已完成：** 增加独立认证的生命周期 transport 契约测试，证明严格 request/acknowledgement 投影、domain-separated HMAC、timestamp/nonce/body digest 绑定、有界 replay window 和安全失败映射，但不增加 route、dispatcher、worker 或现有 CRUD 接线。多实例 replay store 仍是后续运行时闸门。
5. **已完成：** 使用纯临时 store 完成合成、可销毁的进程级集成证明，覆盖按序 outbox-to-ledger 收敛、backlog/high-water/count/digest 投影、四个中断点、有界重试/耗尽、tombstone 防护与 rebuild generation 校验。既有默认值、端口和浏览器边界保持不变并另行复核；没有新增运行时 endpoint。
6. **已完成（disposable 单机 SQLite）：** 获授权 opt-in runtime 已连接 mutation/outbox dispatch、既有认证 listener、generation activation、完整 Memo Qdrant state、restart reconciliation、headed-browser authorization、rollback 与精确 cleanup。
7. 只有再次取得独立明确批准后，才能在真实 Memos 数据上运行 opt-in 迁移/重建；此前必须准备备份、回滚与删除后验证。

### Chunk 与 Qdrant 闸门

A4 仍不启用 chunk retrieval。R5 只在显式、默认关闭的单机 lifecycle 与 rehydration flag 下允许完整 Memo Qdrant Agent retrieval；Memos 继续持有当前 visibility 与 content authority。chunk 仍需独立 version/collection、稳定 delete/tombstone 规则、离线评估、已评审迁移闸门，以及组装 context 前相同的 Memos authority check。`search_memos` 继续只接受完整 `memo-v1` 证据。

## 后续工作不包含在本提案内

任何写工具都需要独立评审认证与 visibility mapping、显式用户确认、幂等、审计与回滚、限流及威胁建模。只读 Agent 不隐含这些能力。
