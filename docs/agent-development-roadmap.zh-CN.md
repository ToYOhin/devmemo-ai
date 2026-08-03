# DevMemo Agent 开发路线

> 状态日期：2026-08-03
>
> 产品方向：面向开发者记忆的 local-first、权限感知 RAG Agent。
>
> 当前交付状态：Agent 功能分支已完成 A0-A3、A4 生命周期设计、R1/A4-I1
> 纯生命周期契约、仅 SQLite 的 A4-I2 源端 outbox 事务证明、dormant 的
> A4-I3 派生 ledger/fake vector 崩溃恢复证明、A4-I4 认证 transport 契约，
> 以及 A4-I5 合成一次性 lifecycle 集成证明；lifecycle route、dispatcher、
> 运行时接线和可用于正式产品的回答链路尚未实现。R4-I1 已增加严格、
> provider-neutral 的 grounded-answer 结果契约，R4-I2 已用合成证据和 fake Provider
> 将其安全接入回答路径，R4-I3 已增加一次性本地 Provider 兼容性 smoke，R5-I1 已增加
> 尚未接线、经 fake 验证的持久化授权检索契约，R5-I2 已增加尚未接线的一次性 SQLite
> repository-adapter parity proof，R5-I3 已通过纯设计契约与合成 fixture 选择认证的 Memos 当前权威
> rehydration 和请求内存正文 retention，R5-I4 已增加尚未接线的进程内证明，覆盖独立 request/response
> HMAC、时效、精确解析和有界 process-local replay，R5-I5 已基于共享 fixture 增加尚未接线的 Go/Python
> canonical 与 exact payload parity，R5-I6 已增加尚未接线的纯 Go current-authority reader 契约与内存
> all-or-nothing parity proof，R5-I7 已增加尚未接线的真实单机 SQLite current-authority reader 与临时数据库
> parity proof，R5-I8 已增加尚未接线的 process-local authority capability issuer/resolver 与有界 registry
> 证明，R5-I9 已增加尚未接线的单机 transport composition 与专用 process-local request replay 证明，
> R5-I10 已增加单机 HTTP handler/client contract、严格投影、固定五秒 timeout 与 recorder/fake-transport
> 证明，R5-I11A 已增加独立 current/previous rehydration keyring 与 AI 侧单一 Memos origin 的严格默认关闭
> 配置，R5-I11B 已增加 matching-key handling 与现有 Memos listener 上的 opt-in registration，R5-I11C 已
> 增加 AI 侧 Python HTTP client 与确定性 lifespan shutdown，R5-I12 已增加 Memos-owned capability issuance
> 与 signed delegation 内的 opaque ref，R5-I13 已增加带 snapshot recheck 的 injected durable candidate/
> rehydration orchestration，R5-I14 已增加无正文 vector/lifecycle adapter、ledger-owned generation revision、
> 授权 UID 查询下推与默认关闭的 lifespan ownership，R5-I15 已在 verified answer path 无 fallback 地选择该
> owned runtime，并完成 disposable synthetic 单机流程证明；R5-I16 已完成逐项审计。获授权的 post-I16
> lifecycle/runtime 工作现已连接 dispatch、generation activation 与 Qdrant derived state，并完成 disposable
> 认证浏览器验收。R5 在默认关闭的单机范围内完成。

本文档是 Agent 产品线的交付权威。`docs/roadmap.md` 继续保存 DevMemo AI
整体项目的历史阶段记录；本文档则定义把 Agent 做成完整、可写入简历的正式项目还需要完成什么。

## 产品契约

DevMemo Agent 只能基于当前调用者本来就有权读取的 Memos 回答问题。它是受控
Agent，而不是通用自治助手：

- Memos 是 Memo 正文、身份、生命周期和可见性的唯一事实源。
- 浏览器只访问同源、已认证的 Memos BFF。
- Agent 只有一个只读工具 `search_memos`，并且只能检索通过预上下文可见性过滤的完整 `memo-v1` 记录。
- AI Service 只允许保存可丢弃、可重建的派生状态，不能成为第二套权限库或 Memo 正文库。
- 对外只返回经校验的 answer、citation、受控元数据与不含内容的 trace。
- Agent 启用、索引以及任何真实数据迁移都必须显式 opt-in，并有书面回滚路径。

因此，项目最终应讲清一个具体故事：**具备源端生命周期可靠投递、权限感知检索、
有依据回答、可量化质量和可复现恢复能力的本地安全 RAG Agent**。

## 当前优势

- Memos BFF 负责认证，并在委托前解析用户可见性。
- 短时 HMAC 委托阻止浏览器自行指定身份或检索范围。
- AI Service 在组装模型上下文前执行 UID 与 `memo-v1` 过滤。
- Agent 只有一个受限工具，并使用严格的安全响应投影。
- 显式本地覆盖层不向宿主机发布 AI Service 端口，默认 Compose 仍关闭 Agent。
- 已使用一次性环境验证 Provider 成功、空检索和安全故障映射，未持久化真实 Memo 派生数据。
- A4 已设计 Memos-owned outbox、有序幂等、tombstone、隔离、重试、重建、可观测性和回滚边界。

## 阻碍项目完善的缺口

| 优先级 | 缺口 | 当前影响 | 退出标准 |
| --- | --- | --- | --- |
| P0 | R5 证据有意限定为 single-host disposable | 运行时验收已覆盖 SQLite Memos、本地 Qdrant、deterministic Provider、认证 visibility、lifecycle 收敛、restart、rollback 与 cleanup，但不覆盖真实数据或多实例 | 保持 R5 边界；真实数据需 backup/restore 证明，多实例需 shared atomic state 与加密 transport |
| P1 | 浏览器 AI 路径分裂 | Evidence Answer 走 BFF，旧 Insights / Context Pack 仍依赖浏览器直连 AI，在 Agent 覆盖层中失败 | 将支持的读路径迁移到认证后的 Memos BFF 安全投影，或隐藏不支持的旧面板；不能通过暴露 8000 修复 |
| P1 | 评估集过小且主要是合成样例 | 检索与安全主张缺少有代表性、可重复的基准 | 发布脱敏评估集、阈值、失败类别与可复现报告 |
| P1 | 可观测性只停留在单次请求 | 运维无法安全观察延迟、重试积压、隔离记录或重建进度 | 增加无内容 metrics/span，并规定字段白名单和基数上限 |
| P1 | AI Service 路由、存储和 Agent 行为集中在大模块中，Python 质量门禁有限 | 改动更难审查和隔离 | 随功能切片提取 domain/service 边界，并增加 lint、类型、覆盖率和定向集成门禁 |
| P1 | Agent 只存在于功能分支，没有公开演示 | 审阅者无法从默认分支或 release 复现完整主张 | 评审合并、发布 tag、架构/威胁模型、评估结果和短演示 |

## 交付规则

下面每个阶段都遵循同一组规则：

1. 先实现最小 contract-first 切片，不改变安全默认值。
2. 在后续阶段明确授权真实数据迁移前，只使用临时数据库、合成记录与一次性 vector store。
3. 接入下一层运行时前，同时验证成功路径和 fail-closed 路径。
4. 每阶段记录回滚方法与不含正文的运行证据。
5. 如果里程碑要求进程重启、store 重建、认证浏览器路径或正式发布，不能只凭单元测试宣称完成。

## 里程碑

### R0 — 产品基线与权威路线

**结果：** 仓库描述一个一致的 Agent 产品、当前限制和可审查的交付顺序。

验收条件：

- 本路线与 Agent 架构契约对权威、持久化、检索和安全输出边界的描述一致。
- 保留项目历史阶段；不能因为 A0-A4 设计记录完成就暗示 Agent 已全部完成。
- 下一代码切片无需数据库、网络、Provider 或真实 Memo 即可执行。

回滚：仅文档改动；如果产品方向改变，移除路线入口即可。

### R1 — 纯生命周期契约（A4-I1）

**状态：** 已实现并通过单元测试，尚无运行时接线。

**结果：** 在引入存储与传输之前，先形成可执行的 domain 规则。

范围：

- 为 `memo.index.requested.v1`、`memo.reindex.requested.v1` 和
  `memo.delete.requested.v1` 定义 provider-neutral event 与 acknowledgement 类型。
- 严格校验事件身份、`source_sequence`、`memo-v1`、operation、reason、时间戳，以及 index/reindex 文档要求。
- 用纯状态转换覆盖新事件、duplicate、stale、同序号 conflict、中断后的 applying/failed 重试、较高序号 supersede、删除 tombstone 和 retrieval quarantine。
- acknowledgement / error 安全投影不得包含 raw Memo、document hash、prompt、context、embedding、身份、可见性或 secret。

验收条件：

- 表驱动单元测试覆盖所有转换和非法输入类别。
- 相同事件重放保持幂等；同序号内容不一致进入隔离；过期事件不能恢复旧 vector；已接受但未完成的变更不可检索。
- 测试无需 route、数据库、网络、vector adapter 或真实数据。

回滚：删除独立 domain 模块和测试即可，不影响运行时或任何已存状态。

### R2 — 可靠源端 outbox 与派生状态 ledger（A4-I2/I3/I4）

**状态：** A4-I2 已有 SQLite schema、显式 dormant adapter 与临时数据库事务证明。
A4-I3 新增了独立构造的 AI SQLite ledger，以及未接线的 processor/fake vector 测试边界，
证明了持久 reservation、duplicate/stale/conflict 决策、两个崩溃重放点、幂等 tombstone
删除、安全错误码与 retrieval quarantine。现有 Memo CRUD 和 AI route 均不调用这些 adapter。
A4-I4 新增 lifecycle-only HMAC purpose/path/header、timestamp/nonce/body digest 绑定、
有界进程内 replay store、严格 event/ack parser、安全错误映射、Go signer/ack parser，
以及 Python in-process client/handler 契约。现有 Memo CRUD 和 AI route 均不调用它们。
MySQL/PostgreSQL adapter、lifecycle route/dispatcher 与运行时接线均未开始。

**结果：** 源数据变更与派生索引意图不能静默分叉。

范围：

- Memos-owned outbox 与源生命周期变更写在同一个数据库事务中。
- 单 Memo 单调递增 `source_sequence`、删除 tombstone、有界显式重试、acknowledgement 和可审计保留策略。
- AI 侧 derived-state ledger 在 vector 变更前预留状态，且不保存 raw Memo 快照。
- 单独认证生命周期传输；不得复用浏览器权限或扩大现有 answer 委托。

验收条件：

- 临时数据库测试证明源变更/outbox 原子性以及事务回滚。
- 消费端测试证明重复投递、乱序、预留后崩溃、vector 写后崩溃、重试、supersede 和删除最终收敛。
- 已接受但失败或未完成的事件必须使对应记录退出检索。
- 日志、ack、metrics 和错误摘要通过脱敏测试。

回滚：关闭生命周期 dispatch、停止消费、丢弃派生 ledger/vector，修正后从 Memos 重建。
仅完成本阶段不代表获准接入真实数据。

### R3 — 一次性端到端生命周期与恢复证明

**状态：** 已由 A4-I5 实现并通过测试，尚无运行时接线。

**结果：** 在不触碰用户真实 Memos 或 volume 的前提下证明持久化本地 RAG 行为。

范围：

- 使用合成 Memo、临时数据库和一次性 vector collection 的 Compose 或进程级测试。
- 覆盖创建、更新、归档/不再 eligible、删除、重启、重试和全量 rebuild generation。
- 对账 Memos high-water mark、ledger 状态和 vector 数量。

验收条件：

- 重启后不丢失已确认的索引状态。
- 更新替换而非复制证据；删除在确认前即不可检索；重建只有校验成功后才切换 generation。
- 人为制造 Provider/store 故障时，只产生有界重试和可恢复状态，不泄露 payload。
- 整套证明可按文档命令完整销毁并重新运行。

回滚：停止一次性环境，只删除事先确认的临时数据库与 vector collection。

### R4 — 有依据的 Provider 回答

**状态：** R4-I1 严格解析与 R4-I2 安全运行时接入已完成。Provider 的授权上下文只使用
opaque evidence reference，验证后的 answer 只能解析为服务端 citation；空检索与 deterministic
输出不变。R4-I3 已用合成证据和一次性本地 Provider 验证 exact 输出、畸形输出 fail closed、
空检索跳过与有界 endpoint failure。这仍是单模型兼容性证明，不是质量基准。

**结果：** 已配置 Provider 可以产出有用回答，同时不削弱安全响应边界。

范围：

- 版本化结构化 answer schema，限制回答长度和 citation ID。
- 每个 citation 必须映射到已授权检索集合；Provider 元数据不能绕过服务器持有的 citation 投影。
- 确定性处理空上下文、畸形输出、未知 citation、Provider 超时/故障和疑似 context echo。
- 加入恶意 Memo / prompt injection fixture，尝试覆盖工具、身份、可见性、输出字段和系统指令。

验收条件：

- Provider 文本只有通过 schema、长度、citation 与脱敏校验后才可返回。
- 未知 citation、raw context echo 和额外字段必须 fail closed。
- 空检索不调用 Provider；安全 502/503 映射保持不变。
- 确定性测试和一次性本地 Provider smoke 覆盖成功与每类失败。

回滚：切回 deterministic finalizer 或关闭 Agent，无需修改源数据。

### R5 — 持久化授权检索与产品路径统一

**状态：** R5-I1 已实现并经 fake 验证。R5-I2 把该 protocol 绑定到显式的一次性 SQLite adapter，
证明 reopen parity、UID/limit 下推与 service 二次求交、一致的 candidate/ledger read、两阶段间 snapshot
失效、正文加载前 lifecycle 拒绝、重复/不一致行拒绝和固定 failure 映射。adapter 只保存合成的
`tmp_path` 数据，不是生产 content-persistence 设计。现有 `EvidenceAnswerAgent`、`RetrievalService`、
VectorStore 构造、Memo CRUD 和 lifecycle runtime 路径均未导入或调用它。
R5-I3 选择 Memos 当前权威、all-or-nothing rehydration，完整正文只保留在请求内存；durable Agent 路径
拒绝 AI 侧持久化完整 Memo 正文和持久 hybrid cache。精确契约与合成 fixture 将 selection 的
sequence/hash/version 绑定到 derived snapshot token，authority 或 revision 改变时整体 fail closed。
请求还携带由 Memos 签发、AI 不解释且不持久化的 request-local opaque authority reference。
R5-I4 增加独立 request/response HMAC、严格 timestamp、body digest、exact parsing、单次调用的 in-process
authority handler、固定签名 failure 与有界 process-local request/client replay store。共享 fixture 与纯测试
覆盖篡改、重放、timeout、部分输出和 selection mismatch。没有增加 HTTP adapter、route、repository、
runtime secret 或真实数据，也不把 HMAC 描述为跨宿主正文保密。
R5-I5 新增 Go request verifier 与 response signer/parser，逐字节对齐共享 Python fixture；它重新核对全部
有界 request/response 字段、拒绝重复或非法嵌套 JSON，并把所有失败投影为
`authorized_retrieval_unavailable`。本切片明确没有增加 Go replay store、authority lookup、route/client、
runtime configuration、网络、持久化或真实数据。
R5-I6 新增纯 Go current-authority reader protocol。它只接受 verified request 与 Memos 内部 opaque 认证
上下文绑定，并要求一个原子 snapshot 重新确认 UID 精确一一对应、当前 visibility、complete/normal/current
状态、sequence、hash、`memo-v1`、snapshot revision 与 authority token。内存 fake 证明由请求拥有 selection
顺序、exact R5-I3 响应投影，以及 update/delete、部分、重复、stale、混合 snapshot 和 adapter error 的
all-or-nothing failure。没有增加真实 Store、visibility resolver、HTTP、HMAC/replay 接线、runtime 配置、
持久化、网络或真实数据。
R5-I7 在不注册 route 或 runtime 的前提下，把该 protocol 绑定到真实单机 SQLite Store 边界。caller identity
只从 Memos 内部认证 context 取得；reader 在同一个只读 snapshot 内重新确认 caller 仍为 normal，并复用
`ListMemos` 的 visibility scope。受限 UID CTE 同时读取 normal、非 comment、非空 Memo 及每个 UID 最新的
A4 source event；只有 source document 等于当前 Memos 正文的 `memo-v1` upsert 才能返回，随后仍由 R5-I6
重查 sequence、hash、version、UID 一一对应与请求顺序。事务前后的 SQLite `data_version` 必须一致，读取期间
任何并发提交都使整批失败。临时 SQLite 测试覆盖 visibility parity、update/delete/visibility race、生命周期与
source mismatch、schema/transaction failure 和无正文错误。本证明只覆盖 SQLite 单机，不覆盖 MySQL/PostgreSQL、
HTTP、真实数据或多实例。
R5-I8 增加尚未接线的 process-local issuer/resolver。签发只从 Memos authentication context 派生 caller
identity，不接收 caller-controlled scope；注入的 Memos-owned source 必须返回同一个 current caller，以及采用
R5-I1 matcher、非空、不重复且最多 1,000 个完整 Memo UID 的 scope。无 timer registry 的容量在构造时固定，
TTL 最多 60 秒。三个独立来源的 opaque token 绑定同一个私有 entry，只有 authority reference 预期进入后续
签名 request。consume 原子检查私有 token index 和唯一、1 至 10 项的 request 子集后删除 entry，只返回
Memos-private auth context、精确原始 UID scope、未改变的 R5-I6 binding 与 authority token。合成测试覆盖过期、
容量、碰撞、错配、重启失效、固定 failure 投影和并发 consume 只有一个成功。没有增加 HTTP、replay-store
复用、runtime 配置、持久化、数据库、网络或真实数据；多实例仍需要加密 transport 与 shared atomic
capability/replay storage。
R5-I9 增加尚未接线的纯 Go composition。它显式注入 scoped secret、有界 request age、clock、专用固定容量
request replay store、R5-I8 registry 与 reader factory。R5-I5 verification 先于 nonce consume，nonce
consume 先于 capability resolution；私有 caller/scope/binding/token resolution 在新 server auth context 进入
单次 reader factory 和 R5-I6 projection 前再次校验。已验证请求的后续 failure 只能成为 exact R5-I5-signed
503；未验证请求与 signing failure 返回零 response projection 和同一固定本地错误。request replay 与
capability store 保持独立且 process-local，未来 client timeout 仍为五秒，automatic retry 仍关闭。合成测试
覆盖 exact signed success、verification 顺序、nonce/capability 单次性、UID scope、binding/token mismatch、
reader one-call、固定 signed failure、并发 duplicate 与新 store 失效。没有增加 HTTP route/client、runtime
secret source、timer、配置、持久化、数据库/网络访问或真实数据。
R5-I10 在该 composition 外增加尚未注册的标准库 HTTP adapter。handler 只接受精确 internal POST path、
四个 HMAC request header 各一个值、精确 JSON content type、最多 32 KiB 的已知非 chunked body、唯一 JSON
value 与成功关闭的 body。verification 前拒绝是无正文、无签名且不可缓存的 404；验证结果只映射 exact signed
200/503 status、body 与 response header。client 只使用 constructor 注入的 base URL、scoped secret、clock
与 RoundTripper，固定五秒 timeout，禁止 redirect/retry，关闭有界 response，并在 exact parsing 前认证
freshness、nonce、snapshot token、status 与 body。client replay 仍属于 AI R5-I4 边界。recorder、内存 handler
与 fake-transport 测试没有增加 registration、listener、环境变量/配置字段、runtime secret lifecycle、真实
socket、Store 访问或真实数据。
R5-I11A 增加对称的 Go/Python 默认关闭配置 contract。opt-in 要求先开启总 Agent flag、一个规范的无填充
base64url 32-byte current secret、可选且不同的 previous secret、与 answer-delegation secret 严格隔离，
以及 AI 侧单一无凭据 HTTP(S) Memos origin。disabled settings 不保留已提供的 secret 或 URL。deployment
boundary 分别向两个进程注入值；服务不创建、分发、持久化、记录或投影它们。该启动时固定的双 key contract
没有增加 route/client、timer、动态 reload、真实 secret、网络或数据。
R5-I11B 在同一份 process-local capability registry 与 request replay store 上构造 current 及可选 previous
composition。HTTP handler 固定先 current 后 previous，只用实际匹配 request 的 key 签 verified success/failure。
显式 opt-in 仅在既有 Memos Echo server 注册 exact internal POST；disabled 启动不增加 route。runtime 不创建
listener、port、goroutine、timer、transport、closeable resource 或 shutdown hook，registration 也不读取 Store。
R5-I11C 增加仅由 enabled FastAPI lifespan 构造的 async Python client。它接收注入的 zero-retry transport，固定
五秒 timeout、禁 redirect、只执行一次 exact signed POST、关闭有界流式 response，并在解析前验证 exact signed
200/503；client 独占一份 process-local response replay store。shutdown 关闭 owned client/transport 并清空
`app.state`，disabled 时完全不创建。当前没有 endpoint 或 answer Agent 使用该 client。
R5-I12 为既有 signed answer delegation 增加可选 opaque Memos authority ref。enabled BFF request 从
process-local registry 一次获取当前 authenticated UID scope 与 capability，只委托该精确 scope，且不向浏览器
投影 ref。空 scope 不创建 capability并保留 no-context 行为。Python 校验该私有字段，但尚未调用 client。
R5-I13 在 content-free candidates 与 I11C client protocol 上增加 injected async orchestrator。它在一次调用前完成
过滤，重新读取 current snapshot token，只在 request memory materialize exact reverified response documents，并
复用现有 authorized result。空 scope/candidates 不调用；所有失败均 content-free，绝不 fallback 到 derived raw
content。当前没有 endpoint 或 Agent runtime 选择它。
R5-I14 增加真实无正文 adapter 与 dormant runtime selection。A4 SQLite ledger 持有一个 active rebuild generation
与单调 snapshot revision；每次 reserve、complete 或 fail 均在同一事务中改变 token。授权 UID scope 先下推到
内存/Qdrant 排序，再把严格的 `memo-v1` sequence/hash/generation metadata 与 applied ledger state 连接。
格式错误、重复、越权、stale、delete、quarantine、含正文或并发变化结果均 fail closed。既有 rehydration opt-in
只为 memo-mode Qdrant 构造 repository/orchestrator，并在 shutdown 清空 lifespan state。memory 默认值与回答路径
保持不变。
R5-I15 只在同一 rehydration opt-in 下把该 owned orchestrator 接入 `EvidenceAnswerAgent`。delegation 仍是第一项
操作；endpoint 只注入当前 app lifespan 已持有的对象，ownership 缺失即 retrieval unavailable。durable context 与
server-owned citation 进入既有 Agent result 时，不接受 vector/rehydration 的 title、tag、visibility 或 citation
metadata。所有 durable error 均映射既有安全 503，不 fallback memory，也不调用 Provider。disabled 保留 memory
retrieval。临时 SQLite、内存 vector 与 fake-client 证明已到达完整回答 trace，未使用网络、Docker、Qdrant 或
真实 Provider。
获授权的 post-I16 切片把 SQLite mutation/outbox delivery 接到既有 AI listener，应用 generation-scoped Qdrant
transition，并只激活已对账 manifest。两次 disposable headed-browser 运行证明自有 private 与另一用户 public
可进入证据、另一用户 private 被排除、安全浏览器投影、update/delete 收敛、restart reconstruction、memory
rollback 与精确 cleanup。AI Service/Qdrant 不发布宿主端口，所有新 runtime flag 仍默认 false。

**结果：** 同一权限边界适用于持久化检索，浏览器只有一种受支持 AI 访问方式。

范围：

- 只有 R2-R4 通过后，才把 `search_memos` 接到经审查的持久化完整 Memo 索引。
- 每个 store adapter 都保留 Memos 可见性解析和 AI 侧预上下文 `memo-v1` 过滤。
- Memos 在 all-or-nothing rehydration 响应前重新确认当前 visibility 与完整 Memo eligibility；返回正文只
  保留于请求内存，并在 materialization 前重新校验 derived snapshot。
- 支持的旧 AI 读能力迁移到认证 Memos BFF；Agent 模式不支持的面板则明确隐藏。
- 写入任何真实 Memo 派生状态前，必须提供显式 opt-in、已验证备份和迁移/回滚 runbook。

验收条件：

当前证据与剩余范围限制记录在 [R5 验收记录](r5-acceptance.zh-CN.md)。

- 跨用户和 private/public 可见性测试中，未授权 citation 与未授权上下文组装均为零。
- 浏览器不请求 AI Service，且不向宿主机发布 AI 端口。
- memory store 与选定持久化 adapter 在文档容差内返回等价的授权结果。
- disposable 单机 Docker/浏览器验收证明 lifecycle activation、current-authority visibility、update/delete、
  restart、rollback 与 cleanup。
- 真实数据 opt-in 需要另行授权、备份验证、dry run、回滚命令和运行后对账。

回滚：关闭 lifecycle 与 rehydration，恢复 memory store 或完全关闭 Agent，只丢弃预先确认的可重建派生状态，
保持 Memos 不变。

### R6 — 评估、可观测性、工程门禁与发布

**结果：** 质量、安全与可运维主张可量化，项目可由他人独立复现。

**状态：** R6-I1 至 R6-I4J 与 R6-I5 已实现并通过测试。R6-I4B runtime ownership、R6-I4D retrieval timing 与 R6-I4F
Provider timing 评审已有文档；R6-I4H 已评审 source-owned Go lifecycle 候选，R6-I4I 已实现 dormant strict Go
contract/bounded adapter，R6-I4J 已在既有 lifecycle opt-in 下接线权威 delivery transition，
明确授权的首批现在记录固定 AI answer outcome/request-count sample。严格 contract、64-case 脱敏 corpus、七项
预声明 threshold、纯
deterministic runner 与 content-free report 均已具备；测试 report 只使用 synthetic result，不主张产品 benchmark
或 runtime 结果。adapter 只在既有 Agent opt-in 下由 lifespan 持有；internal answer handler 每次 invocation 发出固定
answer event/count。R6-I4E 还只在 selected memory/durable retrieval 与安全组装边界发出固定 latency metric/outcome event。
两条路径均隔离记录失败，且无 reader/exporter/persistence。R6-I4G 只在 configured `generate` 与 result-text 检查边界
发出固定 Provider latency/outcome；deterministic fallback 与 answer validation 保持在区间外。Go-owned outbox outcome/
retry/quarantine sample 已具备；outbox lag 仍缺权威 oldest-pending query，rebuild/reconciliation 还需要权威跨进程
state model。R6-I5 offline product-core baseline 实际执行 64 个 sanitized case，暴露 8 个 prompt-injection failure；
refusal accuracy 为 0.6667，未过 threshold。该失败经评审修正前，R6 不能宣称完成。
R6-I5B 已评审 Python/Go/Web 同步的 pre-retrieval fixed refusal contract，但尚未接线。

范围：

- 50-100 个脱敏问题，覆盖查找、综合、无答案、冲突证据、可见性边界、删除、过期状态和 prompt injection。
- Recall@5、MRR、citation precision、groundedness/faithfulness、拒答准确率、scope leak 数、延迟，以及适用时的 Provider/token 成本。
- request outcome、工具/Provider 延迟、outbox lag、重试数、隔离数、rebuild state 和对账状态的无内容 trace/metrics。
- Python lint/type/coverage、定向 Go/Web 检查、一次性生命周期集成测试和认证浏览器验证。
- 面向公开用户的 README、架构与威胁模型图、基准方法/结果、短演示，以及从已评审默认分支产生的 tag/release。

验收条件：

- 在执行 benchmark 前版本化阈值，并公开失败类别，不能只展示汇总高分。
- 可观测性只使用白名单低基数元数据，绝不记录 Memo/问题正文、prompt、context、embedding、secret、身份映射或完整 trace payload。
- CI 能从干净 checkout 复现 unit、integration、security 和 build 检查。
- release runbook 证明安装、显式启用、一次带引用回答、更新/删除收敛、重启恢复、关闭和清理。

回滚：关闭 Agent 与生命周期 dispatcher，保留 Memos，按 release runbook 只删除派生 collection/ledger，修正后重建。

## 可写入简历的完成定义

只有下面证据全部来自已评审代码时，才应把项目描述为完成的 Agent 项目：

- 真实本地 Provider 返回通过 schema 校验的 grounded answer，且全部 citation 都属于调用者可见证据。
- 源端 create/update/delete 经重启、重试和全量重建后仍幂等收敛，没有 stale retrieval。
- 安全测试覆盖可见性隔离、伪造委托、prompt injection、context echo、未知 citation、删除和日志/trace 脱敏。
- 版本化评估报告包含数据集方法、阈值、检索/回答/安全指标、延迟、限制和失败样例。
- 新审阅者可以按文档启动项目、运行一次性证明、使用认证浏览器链路并清理环境。
- 实现在默认分支或正式 tag 中，README 主张与发布状态一致。

在这些门槛完成前，准确表述是：**“已实现安全 Agent 边界并完成本地 RAG 生命周期设计”**，
而不是 **“生产就绪的自治 Agent”**。

## 暂缓能力

以下能力会在单 Agent 只读路径可靠之前扩大范围，因此暂缓：

- MCP、多 Agent 编排、浏览器自动化、Web 搜索、写工具、自治后台任务和 Agent 持久记忆；
- chunk-based 或 public Qdrant Agent retrieval；
- 远程多租户部署和通用插件框架；
- 模型路由、自我反思循环和无边界工具规划。

只有 R6 完成，并重新进行威胁建模、数据流审查和明确授权后，才能重新评估这些能力。

## 下一阶段

R5 已在文档定义的默认关闭单机边界内完成，详见 [R5 验收记录](r5-acceptance.zh-CN.md)。下一步进入 R6：
先建立脱敏 evaluation corpus 与版本化 threshold，再增加 content-free observability 及可复现 CI/release 证据。
R6 不自动授权真实用户数据、外部 Provider、公开 AI 端口、push/tag/release 或多实例部署。任何多实例主张前仍
必须具备加密 transport 与 shared atomic replay/capability storage。
