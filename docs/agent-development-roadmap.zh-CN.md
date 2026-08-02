# DevMemo Agent 开发路线

> 状态日期：2026-08-01
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
> canonical 与 exact payload parity。生产 HTTP rehydration adapter、lifecycle route、dispatcher、运行时接线和
> 可用于正式产品的回答链路仍未实现。

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
| P0 | 授权后的 Agent 运行时检索仍仅支持内存中的完整 Memo store | R5-I5 已证明 Go/Python transport parity，但尚无 Memos 当前 authority lookup、HTTP route/client、replay 接线、runtime secret/configuration、shared replay store 或 runtime selection，因此没有持久化回答路径 | 先定义单机 Memos authority adapter 边界，再分别授权 transport 与 AI runtime selection |
| P0 | A4 尚未接入运行时生命周期路径 | 契约、SQLite outbox、派生 ledger 恢复、认证 transport 与一次性 integration proof 已具备，但没有 lifecycle route、dispatcher 或正式 consumer 调用它们 | 单独评审并授权单机 runtime route/client/dispatcher；任何多实例主张前必须增加共享 replay 存储 |
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

**结果：** 同一权限边界适用于持久化检索，浏览器只有一种受支持 AI 访问方式。

范围：

- 只有 R2-R4 通过后，才把 `search_memos` 接到经审查的持久化完整 Memo 索引。
- 每个 store adapter 都保留 Memos 可见性解析和 AI 侧预上下文 `memo-v1` 过滤。
- Memos 在 all-or-nothing rehydration 响应前重新确认当前 visibility 与完整 Memo eligibility；返回正文只
  保留于请求内存，并在 materialization 前重新校验 derived snapshot。
- 支持的旧 AI 读能力迁移到认证 Memos BFF；Agent 模式不支持的面板则明确隐藏。
- 写入任何真实 Memo 派生状态前，必须提供显式 opt-in、已验证备份和迁移/回滚 runbook。

验收条件：

- 跨用户和 private/public 可见性测试中，未授权 citation 与未授权上下文组装均为零。
- 浏览器不请求 AI Service，且不向宿主机发布 AI 端口。
- memory store 与选定持久化 adapter 在文档容差内返回等价的授权结果。
- 真实数据 opt-in 需要另行授权、备份验证、dry run、回滚命令和运行后对账。

回滚：关闭持久化检索，回到 disabled/deterministic 路径，丢弃可重建派生状态，保持 Memos 不变。

### R6 — 评估、可观测性、工程门禁与发布

**结果：** 质量、安全与可运维主张可量化，项目可由他人独立复现。

范围：

- 50-100 个脱敏问题，覆盖查找、综合、无答案、冲突证据、可见性边界、删除、过期状态和 prompt injection。
- Recall@5、MRR、citation precision、groundedness/faithfulness、拒答准确率、scope leak 数、延迟，以及适用时的 Provider/token 成本。
- request outcome、工具/Provider 延迟、outbox lag、重试数、隔离数、rebuild generation 和对账状态的无内容 trace/metrics。
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

## 下一推荐切片

下一步实施 **R5-I6 单机 Memos authority-adapter 设计契约**。只用纯 Go 对象和合成测试定义：已经验签的
rehydration request 如何在签名前绑定到认证调用者的当前 visibility 与一个原子 current-Memo snapshot。
不新增 HTTP route/client、真实 store query、runtime secret/configuration、replay 实现、database、真实 Memo
或 runtime selection。继续保持 `EvidenceAnswerAgent`、当前 `RetrievalService`、VectorStore factory、Memo
CRUD、dispatcher/worker、Qdrant、Compose 默认值、凭据和真实数据未接线。单机 HTTP adapter 仍需后续授权；
任何多实例使用前仍必须提供加密 transport 与 shared replay storage。
